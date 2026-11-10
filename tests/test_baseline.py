"""Predetermined SYNTHETIC software fixtures; no real data, human labels or network."""

import json
import pickle
import subprocess
from pathlib import Path

import pytest
import test_corpus

from pfa.annotation import pilot_store as store
from pfa.annotation.agreement import TASKS
from pfa.annotation.taxonomy import CHECKSUM
from pfa.cli import main
from pfa.data import corpus, corpus_smoke
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.splitting import CorpusRow
from pfa.ml import baseline

built = test_corpus.built
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def trained(built):
    root, registry, *_ = built
    result = baseline.train(
        root, registry, "synthetic_v1", "sentiment", config=baseline.BaselineConfig(c_values=[0.5])
    )
    return root, registry, result


@pytest.mark.parametrize("task", list(TASKS))
def test_train_all_tasks_and_artifact_roundtrip(built, task):
    root, registry, *_ = built
    config = baseline.BaselineConfig(c_values=[0.5])
    result = baseline.train(root, registry, "synthetic_v1", task, config=config)
    assert (
        result["artifact_checksums_verified"] and result["dataset"]["dataset_type"] == "SYNTHETIC"
    )
    assert result["taxonomy_checksum"] == CHECKSUM
    partitions, _ = baseline.development(root, registry, "synthetic_v1")
    texts, labels, _ = baseline.select(partitions["validation"], task)
    for model in baseline.MODELS:
        loaded = baseline.load_model(root, registry, result["run_id"], model)
        predicted = loaded.predict(texts).tolist()
        assert baseline.metrics(labels, predicted, task) == result["selected"][model]["validation"]
        assert set(loaded.classes_) <= set(TASKS[task])
        assert result["selected"][model]["training_seconds"] >= 0
        if model == "svm":
            assert not hasattr(loaded, "predict_proba")
    if task == "severity":
        assert (
            sum(
                result["task_exclusions"][split].get("UNKNOWN_SEVERITY_SYNTHETIC", 0)
                for split in ("train", "validation")
            )
            > 0
        )
        assert "unknown" not in result["label_mapping"]


@pytest.mark.parametrize("features", ["word", "char", "word_char"])
def test_tfidf_features_train_only_unicode_and_negation(features):
    config = baseline.BaselineConfig(features=features, c_values=[1.0])
    estimator = baseline.pipeline(config, "lr", 1.0, 42)
    estimator.fit(
        ["SYNTHETIC Không hài lòng, chưa rõ.", "SYNTHETIC Rất hài lòng!"], ["negative", "positive"]
    )
    transformers = dict(estimator.named_steps["tfidf"].transformer_list)
    before = {name: dict(vectorizer.vocabulary_) for name, vectorizer in transformers.items()}
    estimator.predict(["validationonlysentinel chưa từng rõ"])
    assert before == {
        name: dict(vectorizer.vocabulary_) for name, vectorizer in transformers.items()
    }
    assert all("validationonlysentinel" not in values for values in before.values())
    if "word" in before:
        assert {"không", "chưa", "rõ"} <= set(before["word"])
    assert baseline.vectorizer_text("  KHÔNG\u00a0chưa!  ") == "không chưa!"


def test_known_metrics():
    result = baseline.metrics(
        ["negative", "negative", "neutral", "positive"],
        ["negative", "positive", "negative", "positive"],
        "sentiment",
    )
    assert result["accuracy"] == 0.5
    assert result["precision_macro"] == pytest.approx(1 / 3)
    assert result["recall_macro"] == 0.5
    assert result["macro_f1"] == pytest.approx(7 / 18)
    assert result["weighted_f1"] == pytest.approx(5 / 12)
    assert result["confusion_matrix"] == [[1, 0, 1], [1, 0, 0], [0, 0, 1]]
    assert result["per_class"]["neutral"]["support"] == 1


@pytest.mark.parametrize(
    "actual,predicted,task",
    [
        ([], [], "topic"),
        (["negative"], [], "sentiment"),
        (["unknown"], ["low"], "severity"),
        (["fake"], ["other"], "topic"),
        (["low"], ["low"], "invalid"),
    ],
)
def test_invalid_metrics(actual, predicted, task):
    with pytest.raises(IngestionError):
        baseline.metrics(actual, predicted, task)


@pytest.mark.parametrize(
    "changes",
    [
        {"features": "test"},
        {"c_values": [0.0]},
        {"c_values": [float("nan")]},
        {"c_values": [1.0, 1.0]},
        {"word_ngram_range": [2, 1]},
        {"max_features": 0},
        {"class_weight": "automatic"},
        {"min_df": 0},
        {"tolerance": float("inf")},
    ],
)
def test_invalid_configuration(changes):
    with pytest.raises(ValueError):
        baseline.BaselineConfig(**changes)


def test_config_file_matches_defaults():
    value = store.read_json(ROOT / "configs/baseline_v1.yaml")
    assert baseline.BaselineConfig.model_validate(value) == baseline.BaselineConfig()


def test_unknown_severity_mask_and_invalid_labels():
    rows, _ = corpus_smoke.fixture(20)
    _, labels, exclusions = baseline.select(rows, "severity")
    assert len(labels) == 18 and sum(exclusions.values()) == 2
    malformed = rows[0].model_copy(deep=True)
    malformed.labels["severity"] = "unknown"
    with pytest.raises(ValueError):
        baseline.select([malformed], "severity")
    malformed.labels["severity"] = "low"
    with pytest.raises(ValueError):
        CorpusRow.model_validate(malformed.model_dump())


def test_no_test_partition_reads_and_train_only_fit(built, monkeypatch):
    root, registry, *_ = built
    original = corpus._read_partition
    accessed = []

    def guard(path):
        assert path.name != "test.parquet", "Model training deserialized test labels"
        accessed.append(path.name)
        return original(path)

    monkeypatch.setattr(corpus, "_read_partition", guard)
    partitions, _ = baseline.development(root, registry, "synthetic_v1")
    train_text, _, _ = baseline.select(partitions["train"], "sentiment")
    from sklearn.pipeline import Pipeline

    original_fit = Pipeline.fit

    def fit_only_train(estimator, text, labels, **kwargs):
        assert text == train_text
        return original_fit(estimator, text, labels, **kwargs)

    monkeypatch.setattr(Pipeline, "fit", fit_only_train)
    result = baseline.train(root, registry, "synthetic_v1", "sentiment")
    assert len(result["candidates"]) == 4
    assert not result["dataset"]["test_labels_read"] and accessed
    with pytest.raises(IngestionBlocked):
        corpus.model_selection(root, registry, "synthetic_v1", "test")


def test_cross_partition_duplicates_rejected(built, monkeypatch):
    root, registry, *_ = built
    original = corpus.model_selection
    training = original(root, registry, "synthetic_v1", "train")

    def overlap(root, registry, dataset, split):
        return training if split == "validation" else original(root, registry, dataset, split)

    monkeypatch.setattr(corpus, "model_selection", overlap)
    with pytest.raises(IngestionError):
        baseline.train(root, registry, "synthetic_v1", "topic")


def test_imbalance_missing_classes_and_single_class(built, monkeypatch):
    root, registry, *_ = built
    partitions, binding = baseline.development(root, registry, "synthetic_v1")
    for index, row in enumerate(partitions["train"]):
        row.labels["sentiment"] = "positive" if index == 0 else "negative"
    monkeypatch.setattr(baseline, "development", lambda *args: (partitions, binding))
    result = baseline.train(
        root, registry, "synthetic_v1", "sentiment", config=baseline.BaselineConfig(c_values=[1.0])
    )
    assert "TRAIN_RARE_CLASS" in result["warnings"]
    assert "TRAIN_MISSING_TAXONOMY_CLASSES" in result["warnings"]
    assert result["config"]["class_weight"] == "balanced"
    for row in partitions["train"]:
        row.labels["sentiment"] = "negative"
    with pytest.raises(IngestionError, match="two training classes"):
        baseline.train(root, registry, "synthetic_v1", "sentiment")


def test_artifact_checksum_before_deserialization(trained, monkeypatch):
    root, registry, run = trained
    artifact = baseline.location(root, run["run_id"]) / "lr.pkl"
    artifact.write_bytes(b"SYNTHETIC corrupted model")
    monkeypatch.setattr(pickle, "load", lambda *args: pytest.fail("Corrupt pickle loaded"))
    with pytest.raises(IngestionError, match="checksum"):
        baseline.load_model(root, registry, run["run_id"], "lr")


def test_metadata_corruption_and_inventory(trained):
    root, registry, run = trained
    directory = baseline.location(root, run["run_id"])
    (directory / "run.json").write_text("{}")
    with pytest.raises(IngestionError):
        baseline.inspect(root, registry, run["run_id"])


def test_serialization_failure_atomic_cleanup(built, monkeypatch):
    root, registry, *_ = built

    def fail(*args, **kwargs):
        raise OSError("Simulated synthetic write failure")

    monkeypatch.setattr(pickle, "dump", fail)
    with pytest.raises(OSError):
        baseline.train(
            root,
            registry,
            "synthetic_v1",
            "sentiment",
            config=baseline.BaselineConfig(c_values=[1.0]),
        )
    assert list((root / "data/private/ml_runs").iterdir()) == []


def test_immutable_artifacts_and_repeatability(trained):
    root, registry, first = trained
    second = baseline.train(
        root, registry, "synthetic_v1", "sentiment", config=baseline.BaselineConfig(c_values=[0.5])
    )
    assert first["run_id"] != second["run_id"]
    for model in baseline.MODELS:
        assert first["selected"][model]["validation"] == second["selected"][model]["validation"]
    with pytest.raises(IngestionError, match="Immutable"):
        baseline._save(root, first["run_id"], {}, {})
    ranking = baseline.compare(root, registry, "synthetic_v1", "sentiment")
    assert len(ranking["ranking"]) == 4 and ranking["selection_partition"] == "validation"


def test_missing_dataset_and_no_synthetic_promotion(built, monkeypatch):
    root, registry, *_ = built
    with pytest.raises(IngestionError, match="NOT_AVAILABLE"):
        baseline.train(root, registry, "missing", "topic")
    monkeypatch.setattr(store, "is_synthetic", lambda *args: False)
    with pytest.raises(IngestionBlocked):
        baseline.train(root, registry, "synthetic_v1", "topic")


@pytest.mark.parametrize("reason", ["missing permission", "revoked", "unapproved taxonomy"])
def test_governance_failure_before_training(built, monkeypatch, reason):
    root, registry, *_ = built

    def blocked(*args, **kwargs):
        raise IngestionBlocked(reason)

    monkeypatch.setattr(corpus, "_authorized_manifest", blocked)
    monkeypatch.setattr(
        baseline, "pipeline", lambda *args: pytest.fail("Unauthorized model training")
    )
    with pytest.raises(IngestionBlocked):
        baseline.train(root, registry, "synthetic_v1", "topic")


def test_actual_research_governance_before_partition_read(built, monkeypatch):
    root, registry, *_ = built
    (root / "configs").mkdir(exist_ok=True)
    (root / "configs/taxonomy_v1.yaml").write_bytes(
        (ROOT / "configs/taxonomy_v1.yaml").read_bytes()
    )
    manifest = corpus.directory(root, "synthetic_v1") / "manifest.json"
    value = json.loads(manifest.read_text())
    value["dataset_type"] = value["provenance"]["dataset_type"] = "RESEARCH"
    manifest.write_text(json.dumps(value))
    monkeypatch.setattr(corpus, "_read_partition", lambda *args: pytest.fail("Unauthorized read"))
    with pytest.raises(IngestionBlocked):
        baseline.train(root, registry, "synthetic_v1", "topic")


def test_reports_no_raw_text_and_cli(trained, monkeypatch, capsys, caplog):
    root, registry, run = trained
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(root))
    (root / "configs").mkdir(exist_ok=True)
    (root / "configs/dataset_sources.yaml").write_bytes(
        (ROOT / "configs/dataset_sources.yaml").read_bytes()
    )
    for command in (
        ["ml", "inspect", "--run-id", run["run_id"]],
        ["ml", "compare", "--dataset", "synthetic_v1", "--task", "sentiment"],
    ):
        assert main(command) == 0
        output = capsys.readouterr().out
        assert "SYNTHETIC" in output and "SYNTHETIC:" not in output
        assert "feedback_id" not in output and "data/private" not in output
    assert not caplog.text
    assert main(["ml", "inspect", "--run-id", "missing"]) == 4
    assert main(["annotation", "taxonomy", "show"]) != 0  # No taxonomy file in isolated root.


def test_synthetic_smoke_and_cli(monkeypatch, capsys):
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(ROOT))
    assert main(["ml", "baseline-smoke"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BASELINE_SMOKE_PASS_SYNTHETIC"
    assert result["temporary_storage_cleaned"] and result["test_access_blocked"]
    assert not result["test_labels_read"] and not result["human_gold"]
    assert set(result["tasks"]) == set(TASKS)
    assert all(result["tasks"][task]["artifacts_verified"] for task in TASKS)


def test_model_storage_git_exclusion():
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "check-ignore",
            "data/private/ml_runs/baseline_synthetic/lr.pkl",
            "data/private/ml_runs/baseline_synthetic/run.json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and len(result.stdout.splitlines()) == 2


def test_train_cli_with_synthetic_capability_only(built, monkeypatch, capsys):
    root, _, *_ = built
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(root))
    (root / "configs").mkdir(exist_ok=True)
    (root / "configs/dataset_sources.yaml").write_bytes(
        (ROOT / "configs/dataset_sources.yaml").read_bytes()
    )
    assert (
        main(
            [
                "ml",
                "train-baselines",
                "--dataset",
                "synthetic_v1",
                "--task",
                "severity",
                "--seed",
                "42",
            ]
        )
        == 0
    )
    run = json.loads(capsys.readouterr().out)
    assert run["status"] == "VERIFIED" and run["dataset"]["dataset_type"] == "SYNTHETIC"
    assert len(run["candidates"]) == 4 and not run["dataset"]["test_labels_read"]


def test_bad_vocabulary_fails_without_sensitive_diagnostics(built, capsys, caplog):
    root, registry, *_ = built
    with pytest.raises(IngestionError, match="Baseline fitting failed") as error:
        baseline.train(
            root,
            registry,
            "synthetic_v1",
            "topic",
            config=baseline.BaselineConfig(features="word", min_df=5000),
        )
    assert "SYNTHETIC:" not in str(error.value)
    assert not capsys.readouterr().out and not caplog.text
    assert not (root / "data/private/ml_runs").exists()


def test_revoked_model_load_does_not_unpickle(trained, monkeypatch):
    root, registry, run = trained

    def revoked(*args, **kwargs):
        raise IngestionBlocked("Revoked source training scope")

    monkeypatch.setattr(corpus, "_authorized_manifest", revoked)
    monkeypatch.setattr(pickle, "load", lambda *args: pytest.fail("Revoked model loaded"))
    with pytest.raises(IngestionBlocked):
        baseline.load_model(root, registry, run["run_id"], "lr")
