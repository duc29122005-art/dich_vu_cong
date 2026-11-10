"""Governed classical baselines. No test reader, external model loader or label inference."""

import os
import pickle
import platform
import secrets
import warnings
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version as package_version
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from pfa.annotation import pilot_store as store
from pfa.annotation.agreement import TASKS
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.data import corpus, official, preprocessing
from pfa.data.official_io import IngestionBlocked, IngestionError, protect_directory, safe_path
from pfa.data.registry import Metadata, Registry
from pfa.data.splitting import CorpusRow, group_rows

if TYPE_CHECKING:
    from sklearn.pipeline import Pipeline

MODELS = ("lr", "svm")
Task = Literal["topic", "sentiment", "severity"]


def vectorizer_text(text: str) -> str:
    return preprocessing.normalize_text(text).lower()


def implementation() -> dict[str, str]:
    return {
        "baseline": store.file_checksum(Path(__file__)),
        "preprocessing": store.file_checksum(Path(preprocessing.__file__)),
    }


class BaselineConfig(Metadata):
    version: Literal["baseline-config-1"] = "baseline-config-1"
    features: Literal["word", "char", "word_char"] = "word_char"
    word_ngram_range: list[int] = Field(default_factory=lambda: [1, 2], min_length=2, max_length=2)
    char_ngram_range: list[int] = Field(default_factory=lambda: [3, 5], min_length=2, max_length=2)
    max_features: int = Field(default=20000, ge=1, le=100000)
    min_df: int = Field(default=1, ge=1, le=5000)
    c_values: list[float] = Field(default_factory=lambda: [0.5, 1.0], min_length=1, max_length=8)
    class_weight: Literal["balanced"] | None = "balanced"
    max_iter: int = Field(default=2000, ge=1, le=100000)
    tolerance: float = Field(default=0.0001, gt=0, le=0.1, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid(self) -> "BaselineConfig":
        for low, high in (self.word_ngram_range, self.char_ngram_range):
            if not 1 <= low <= high <= 8:
                raise ValueError("Ordered ngram ranges from 1 through 8 required")
        if any(not 0 < value <= 1000 for value in self.c_values) or len(set(self.c_values)) != len(
            self.c_values
        ):
            raise ValueError("Unique finite positive C values required")
        return self


def dependencies() -> dict[str, str]:
    try:
        return {
            name: package_version(name)
            for name in ("scikit-learn", "numpy", "scipy", "joblib", "threadpoolctl")
        }
    except ModuleNotFoundError:
        raise IngestionError("Install the existing scikit-learn ML dependency") from None


def pipeline(config: BaselineConfig, model: str, c_value: float, seed: int) -> "Pipeline":
    """Feature vocabularies are fitted only by Pipeline.fit on the training partition."""
    if model not in MODELS or not 0 <= seed < 2**32:
        raise IngestionError("Invalid baseline model or seed")
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.svm import LinearSVC

    common = dict(
        preprocessor=vectorizer_text,
        strip_accents=None,
        sublinear_tf=True,
        max_features=config.max_features,
        min_df=config.min_df,
    )
    features = []
    if config.features in {"word", "word_char"}:
        features.append(
            (
                "word",
                TfidfVectorizer(
                    analyzer="word",
                    ngram_range=tuple(config.word_ngram_range),
                    token_pattern=r"(?u)\b\w+\b",
                    **common,
                ),
            )
        )
    if config.features in {"char", "word_char"}:
        features.append(
            (
                "char",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=tuple(config.char_ngram_range),
                    **common,
                ),
            )
        )
    parameters = dict(
        C=c_value,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        tol=config.tolerance,
        random_state=seed,
    )
    estimator = (
        LogisticRegression(solver="lbfgs", **parameters)
        if model == "lr"
        else LinearSVC(dual="auto", **parameters)
    )
    return Pipeline([("tfidf", FeatureUnion(features)), ("classifier", estimator)])


def metrics(actual: list[str], predicted: list[str], task: Task) -> dict:
    if task not in TASKS or not actual or len(actual) != len(predicted):
        raise IngestionError("Nonempty matched labels and known task required")
    labels = list(TASKS[task])
    if any(label not in labels for label in actual + predicted):
        raise IngestionError("Invalid supervised label; unknown severity is excluded")
    from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

    precision, recall, f1, support = precision_recall_fscore_support(
        actual, predicted, labels=labels, zero_division=0
    )
    weighted = sum(float(score) * int(count) for score, count in zip(f1, support)) / len(actual)
    return {
        "accuracy": float(accuracy_score(actual, predicted)),
        "precision_macro": float(precision.mean()),
        "recall_macro": float(recall.mean()),
        "macro_f1": float(f1.mean()),
        "weighted_f1": weighted,
        "record_count": len(actual),
        "label_order": labels,
        "confusion_matrix": confusion_matrix(actual, predicted, labels=labels).tolist(),
        "per_class": {
            label: {"precision": float(p), "recall": float(r), "f1": float(f), "support": int(n)}
            for label, p, r, f, n in zip(labels, precision, recall, f1, support)
        },
        "zero_division_policy": "0; absent taxonomy classes remain in macro denominators",
    }


def development(root: Path, registry: Registry, dataset: str) -> tuple[dict, dict]:
    """Current governance precedes partition reads; never deserialize the test partition."""
    path, manifest = corpus._authorized_manifest(root, registry, dataset)
    partitions = {
        split: corpus.model_selection(root, registry, dataset, split)
        for split in ("train", "validation")
    }
    rows = partitions["train"] + partitions["validation"]
    if any(
        row.dataset_type != manifest["dataset_type"] or row.taxonomy_checksum != CHECKSUM
        for row in rows
    ):
        raise IngestionBlocked("Development provenance or taxonomy mismatch")
    key = secrets.token_bytes(32)  # Ephemeral keyed grouping; fingerprints are never exported.
    grouped = group_rows(rows, lambda value: official.fingerprint(key, "ml-development-1", value))
    boundary = len(partitions["train"])
    if {row.group_id for row in grouped[:boundary]} & {row.group_id for row in grouped[boundary:]}:
        raise IngestionError("Cross-partition duplicate, case or thread leakage")
    if not all(partitions.values()):
        raise IngestionError("NOT_AVAILABLE: train and validation must be nonempty")
    checksums = store.read_json(path / "checksums.json")
    return partitions, {
        "dataset_version": dataset,
        "dataset_type": manifest["dataset_type"],
        "manifest_sha256": store.file_checksum(path / "manifest.json"),
        "split_sha256": {split: checksums[split + ".parquet"] for split in corpus.SPLITS},
        "test_membership_checksum": manifest["test_membership_checksum"],
        "source_manifest_checksum": manifest["provenance"]["source_manifest_checksum"],
        "construction_checksum": manifest["construction_checksum"],
        "test_labels_read": False,
    }


def select(rows: list[CorpusRow], task: Task) -> tuple[list[str], list[str], dict]:
    if task not in TASKS:
        raise IngestionError("Unknown classification task")
    checked = [CorpusRow.model_validate(row.model_dump()) for row in rows]
    eligible = [row for row in checked if row.eligible[task]]
    return (
        [row.content for row in eligible],
        [row.labels[task] for row in eligible],
        dict(Counter(row.exclusion_reasons[task] for row in checked if not row.eligible[task])),
    )


def location(root: Path, run_id: str) -> Path:
    return safe_path(root / "data/private/ml_runs" / store.identifier(run_id), root)


def train(
    root: Path,
    registry: Registry,
    dataset: str,
    task: Task,
    seed: int = 42,
    config: BaselineConfig | None = None,
) -> dict:
    partitions, binding = development(root, registry, dataset)
    config = BaselineConfig.model_validate((config or BaselineConfig()).model_dump())
    if not 0 <= seed < 2**32:
        raise IngestionError("Seed must be an unsigned 32-bit integer")
    train_text, train_labels, train_exclusions = select(partitions["train"], task)
    valid_text, valid_labels, valid_exclusions = select(partitions["validation"], task)
    if len(set(train_labels)) < 2 or not valid_labels:
        raise IngestionError(
            "At least two training classes and eligible validation records required"
        )
    versions = dependencies()
    from sklearn.exceptions import ConvergenceWarning
    from threadpoolctl import threadpool_limits

    notes = []
    distributions = {
        "train": dict(Counter(train_labels)),
        "validation": dict(Counter(valid_labels)),
    }
    for split, counts in distributions.items():
        if set(counts) != set(TASKS[task]):
            notes.append(split.upper() + "_MISSING_TAXONOMY_CLASSES")
        if min(counts.values()) < 2:
            notes.append(split.upper() + "_RARE_CLASS")
    if set(valid_labels) - set(train_labels):
        notes.append("VALIDATION_CLASSES_ABSENT_FROM_TRAIN")
    started = datetime.now(UTC).isoformat()
    selected, candidates, fitted = {}, [], {}
    for model in MODELS:
        best = None
        for c_value in sorted(config.c_values):
            estimator = pipeline(config, model, c_value, seed)
            try:
                with warnings.catch_warnings(), threadpool_limits(limits=1):
                    warnings.simplefilter("error", ConvergenceWarning)
                    clock = perf_counter()
                    estimator.fit(train_text, train_labels)
                    training_seconds = perf_counter() - clock
                clock = perf_counter()
                predicted = estimator.predict(valid_text).tolist()
                inference_seconds = perf_counter() - clock
            except (ValueError, ConvergenceWarning):
                raise IngestionError(
                    "Baseline fitting failed; check classes, vocabulary and iteration limit"
                ) from None
            result = {
                "model": model,
                "C": c_value,
                "validation": metrics(valid_labels, predicted, task),
                "training_seconds": training_seconds,
                "inference_seconds": inference_seconds,
                "inference_seconds_per_record": inference_seconds / len(valid_labels),
            }
            candidates.append(result)
            if best is None or result["validation"]["macro_f1"] > best["validation"]["macro_f1"]:
                best, fitted[model] = result, estimator
        selected[model] = best
    winner = max(MODELS, key=lambda model: selected[model]["validation"]["macro_f1"])
    run_id = "baseline_" + uuid4().hex
    metadata = {
        "format_version": "baseline-run-1",
        "run_id": run_id,
        "dataset": binding,
        "task": task,
        "taxonomy_version": VERSION,
        "taxonomy_checksum": CHECKSUM,
        "label_mapping": list(TASKS[task]),
        "seed": seed,
        "config": config.model_dump(),
        "configuration_sha256": store.digest(config.model_dump()),
        "dependencies": versions,
        "dependency_snapshot_sha256": store.digest(versions),
        "python": platform.python_version(),
        "implementation_sha256": implementation(),
        "transformation_version": preprocessing.TRANSFORMATION_VERSION + "+baseline-lowercase-1",
        "started_at": started,
        "completed_at": datetime.now(UTC).isoformat(),
        "selection_partition": "validation",
        "selection_metric": "macro_f1",
        "tie_break": "smaller C, then lr",
        "selected_model": winner,
        "class_distributions": distributions,
        "task_exclusions": {"train": train_exclusions, "validation": valid_exclusions},
        "warnings": notes,
        "candidates": candidates,
        "selected": selected,
        "research_validity_claimed": False,
        "score_semantics": "LinearSVC margins are not probabilities; predictions are label codes",
    }
    # Revalidate rights and frozen data after fitting, before publishing private artifacts.
    if development(root, registry, dataset)[1] != binding:
        raise IngestionBlocked("Dataset changed during training")
    _save(root, run_id, metadata, fitted)
    return inspect(root, registry, run_id)


def _save(root: Path, run_id: str, metadata: dict, fitted: dict) -> None:
    target = location(root, run_id)
    store.private_directory(target.parent)
    lock = target.parent / ".writer.lock"
    try:
        handle = lock.open("x")
    except FileExistsError:
        raise IngestionError("Model artifact writer busy") from None
    try:
        with handle:
            if target.exists():
                raise IngestionError("Immutable model run already exists")
            with TemporaryDirectory(prefix=".baseline-", dir=target.parent) as temporary:
                work = Path(temporary)
                protect_directory(work)
                for model in MODELS:
                    with (work / (model + ".pkl")).open("xb") as stream:
                        if os.name != "nt":
                            (work / (model + ".pkl")).chmod(0o600)
                        pickle.dump(fitted[model], stream, protocol=5)
                        stream.flush()
                        os.fsync(stream.fileno())
                official.write_json(work / "run.json", metadata)
                official.write_json(
                    work / "checksums.json",
                    {
                        name: store.file_checksum(work / name)
                        for name in ("run.json", "lr.pkl", "svm.pkl")
                    },
                )
                work.rename(target)
    finally:
        lock.unlink()


def inspect(root: Path, registry: Registry, run_id: str) -> dict:
    """Verify bytes and current governance without deserializing executable pickle artifacts."""
    path = location(root, run_id)
    metadata = store.read_json(path / "run.json")
    required = {
        "format_version",
        "run_id",
        "dataset",
        "config",
        "taxonomy_checksum",
        "taxonomy_version",
        "task",
        "label_mapping",
        "configuration_sha256",
        "dependencies",
        "dependency_snapshot_sha256",
        "implementation_sha256",
        "python",
    }
    if (
        not isinstance(metadata, dict)
        or not required <= metadata.keys()
        or metadata.get("format_version") != "baseline-run-1"
        or metadata.get("run_id") != run_id
        or not isinstance(metadata["dataset"], dict)
        or not isinstance(metadata["dataset"].get("dataset_version"), str)
        or not isinstance(metadata["task"], str)
        or not isinstance(metadata["dependencies"], dict)
    ):
        raise IngestionError("Invalid baseline run identity")
    _, current = development(root, registry, metadata["dataset"]["dataset_version"])
    if current != metadata["dataset"]:
        raise IngestionBlocked("Model dataset provenance changed")
    config = BaselineConfig.model_validate(metadata["config"])
    if (
        metadata["taxonomy_checksum"] != CHECKSUM
        or metadata["taxonomy_version"] != VERSION
        or metadata["task"] not in TASKS
        or metadata["label_mapping"] != list(TASKS[metadata["task"]])
        or store.digest(config.model_dump()) != metadata["configuration_sha256"]
        or store.digest(metadata["dependencies"]) != metadata["dependency_snapshot_sha256"]
    ):
        raise IngestionError("Model configuration or taxonomy binding changed")
    inventory = store.read_json(path / "checksums.json")
    expected = {"run.json", "lr.pkl", "svm.pkl"}
    if (
        not isinstance(inventory, dict)
        or set(inventory) != expected
        or {item.name for item in path.iterdir()} != expected | {"checksums.json"}
    ):
        raise IngestionError("Model artifact inventory mismatch")
    for name in expected:
        if store.file_checksum(safe_path(path / name, root)) != inventory[name]:
            raise IngestionError("Model artifact checksum mismatch")
    return {"status": "VERIFIED", "artifact_checksums_verified": True, **metadata}


def load_model(root: Path, registry: Registry, run_id: str, model: str) -> "Pipeline":
    """Trusted application-created local runs only; never load user-supplied pickle files."""
    if model not in MODELS:
        raise IngestionError("Unknown baseline model")
    metadata = inspect(root, registry, run_id)
    if (
        metadata["dependencies"] != dependencies()
        or metadata["python"] != platform.python_version()
        or metadata["implementation_sha256"] != implementation()
    ):
        raise IngestionError("Model loading requires recorded code, Python and dependency versions")
    with safe_path(location(root, run_id) / (model + ".pkl"), root).open("rb") as stream:
        return pickle.load(stream)


def compare(root: Path, registry: Registry, dataset: str, task: Task) -> dict:
    development(root, registry, dataset)  # Gate even when no experiments exist.
    if task not in TASKS:
        raise IngestionError("Unknown classification task")
    directory = safe_path(root / "data/private/ml_runs", root)
    runs = []
    if directory.exists():
        for path in sorted(directory.iterdir()):
            if path.name.startswith("baseline_"):
                identity = store.read_json(safe_path(path / "run.json", root))
                if (
                    identity.get("dataset", {}).get("dataset_version") != dataset
                    or identity.get("task") != task
                ):
                    continue
                result = inspect(root, registry, path.name)
                if result["dataset"]["dataset_version"] == dataset and result["task"] == task:
                    runs.append(result)
    if not runs:
        raise IngestionError("NOT_AVAILABLE: no verified baseline runs for this dataset and task")
    scores = [
        {"run_id": run["run_id"], "model": model, **run["selected"][model]}
        for run in runs
        for model in MODELS
    ]
    scores.sort(key=lambda item: (-item["validation"]["macro_f1"], item["run_id"], item["model"]))
    return {
        "dataset_type": runs[0]["dataset"]["dataset_type"],
        "dataset_version": dataset,
        "task": task,
        "selection_partition": "validation",
        "ranking": scores,
        "research_validity_claimed": False,
    }
