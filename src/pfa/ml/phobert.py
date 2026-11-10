"""Offline-first PhoBERT integration and synthetic architecture tests, never test tuning."""

import os
import platform
import random
import re
from datetime import UTC, datetime
from importlib.metadata import version
from itertools import islice
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from pfa.annotation import pilot_store as store
from pfa.annotation.approval import reviewed_time
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.data.official_io import (
    IngestionBlocked,
    IngestionError,
    protect_directory,
    safe_path,
    write_json,
)
from pfa.data.registry import Identifier, Metadata, Registry, Text
from pfa.ml import baseline
from pfa.ml.segmentation import SegmentationConfig, Segmenter

MAX_ARTIFACT_BYTES = 2 * 1024**3


class PhobertConfig(Metadata):
    version: Literal["phobert-config-1"] = "phobert-config-1"
    checkpoint: Literal["vinai/phobert-base"] = "vinai/phobert-base"
    checkpoint_directory: str | None = None
    checkpoint_evidence_ref: Identifier | None = None
    segmenter: SegmentationConfig = Field(default_factory=SegmentationConfig)
    max_length: int = Field(default=256, ge=4, le=512)
    epochs: int = Field(default=3, ge=1, le=100)
    learning_rate: float = Field(default=0.00002, gt=0, le=0.1, allow_inf_nan=False)
    weight_decay: float = Field(default=0.01, ge=0, le=1, allow_inf_nan=False)
    batch_size: int = Field(default=8, ge=1, le=128)
    gradient_accumulation: int = Field(default=1, ge=1, le=64)
    eval_every_epochs: int = Field(default=1, ge=1, le=100)
    patience: int = Field(default=2, ge=1, le=100)
    min_delta: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)
    device: Literal["cpu", "cuda", "auto"] = "auto"
    cpu_threads: int = Field(default=1, ge=1, le=16)


class CheckpointEvidence(Metadata):
    checkpoint: Literal["vinai/phobert-base"]
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    license_name: Text
    license_evidence_ref: Identifier
    reviewer_id: Identifier
    evidence_reference: Identifier
    reviewed_at: str
    human_verified: Literal[True]
    decision: Literal["APPROVED"]
    files: dict[str, str] = Field(min_length=4, max_length=32)

    @model_validator(mode="after")
    def reviewed(self) -> "CheckpointEvidence":
        reviewed_time(self.reviewed_at)
        if self.license_name.upper() in {"UNKNOWN", "PENDING"}:
            raise ValueError("Actual reviewed checkpoint license required")
        if any(
            value.upper() in {"UNKNOWN", "PENDING"}
            for value in (self.license_evidence_ref, self.reviewer_id, self.evidence_reference)
        ):
            raise ValueError("Actual human checkpoint review references required")
        for name, checksum in self.files.items():
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name) or not re.fullmatch(
                r"[a-f0-9]{64}", checksum
            ):
                raise ValueError("Flat checkpoint files with SHA256 required")
        return self


class Run(Metadata):
    format_version: Literal["phobert-run-1"]
    run_id: Identifier
    task: baseline.Task
    dataset: dict
    taxonomy_version: Literal[VERSION]
    taxonomy_checksum: Literal[CHECKSUM]
    label2id: dict[str, int]
    config: PhobertConfig
    configuration_sha256: str
    seed: int = Field(ge=0, lt=2**32)
    checkpoint: dict
    segmentation: dict
    dependencies: dict[str, str]
    implementation_sha256: dict[str, str]
    python: str
    device: str
    completed_epochs: int = Field(ge=1)
    optimizer_steps: int = Field(ge=1)
    best_epoch: int = Field(ge=1)
    stale_evaluations: int = Field(ge=0)
    history: list[dict] = Field(min_length=1)
    task_exclusions: dict
    truncation: dict
    warnings: list[str]
    previous_run: str | None
    finite_backward_verified: Literal[True]
    started_at: str
    completed_at: str
    training_seconds: float = Field(ge=0, allow_inf_nan=False)
    selection_partition: Literal["validation"] = "validation"
    score_semantics: Literal["UNCALIBRATED_SOFTMAX_NOT_CONFIDENCE"] = (
        "UNCALIBRATED_SOFTMAX_NOT_CONFIDENCE"
    )


def public_config(config: PhobertConfig) -> dict:
    value = config.model_dump()
    value["checkpoint_directory"] = None
    value["segmenter"]["model_directory"] = None
    return value


def mapping(task: baseline.Task) -> dict[str, int]:
    if task not in baseline.TASKS:
        raise IngestionError("Unknown PhoBERT classification task")
    return {label: index for index, label in enumerate(baseline.TASKS[task])}


def dependencies() -> dict[str, str]:
    try:
        return {
            name: version(name)
            for name in (
                "torch",
                "transformers",
                "safetensors",
                "tokenizers",
                "numpy",
                "scikit-learn",
            )
        }
    except ModuleNotFoundError:
        raise IngestionError(
            "Install optional project dependencies: pip install -e .[phobert]"
        ) from None


def implementation() -> dict[str, str]:
    from pfa.ml import segmentation

    return {
        "phobert": store.file_checksum(Path(__file__)),
        "segmentation": store.file_checksum(Path(segmentation.__file__)),
        **baseline.implementation(),
    }


def device_for(config: PhobertConfig) -> str:
    import torch

    if config.device == "cuda" and not torch.cuda.is_available():
        raise IngestionBlocked(
            "CUDA_NOT_AVAILABLE: install a compatible CUDA wheel/driver or use CPU"
        )
    return "cuda" if config.device != "cpu" and torch.cuda.is_available() else "cpu"


def seed_all(seed: int) -> None:
    import numpy as np
    import torch

    if not 0 <= seed < 2**32:
        raise IngestionError("Seed must be an unsigned 32-bit integer")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def approved_checkpoint(root: Path, config: PhobertConfig) -> tuple[Path, dict]:
    if not config.checkpoint_directory or not config.checkpoint_evidence_ref:
        raise IngestionBlocked(
            "CHECKPOINT_NOT_READY: approved local checkpoint and evidence required"
        )
    evidence_path = safe_path(
        root / "data/private/phobert_requests" / (config.checkpoint_evidence_ref + ".json"), root
    )
    evidence = CheckpointEvidence.model_validate(store.read_json(evidence_path))
    path = safe_path(Path(config.checkpoint_directory))
    required = {"config.json", "model.safetensors", "vocab.txt", "bpe.codes"}
    if not required <= evidence.files.keys() or not path.is_dir():
        raise IngestionBlocked(
            "CHECKPOINT_NOT_READY: local safe weights and PhoBERT BPE files required"
        )
    if {item.name for item in path.iterdir()} != set(evidence.files):
        raise IngestionError("Approved checkpoint inventory mismatch")
    for name, checksum in evidence.files.items():
        if store.file_checksum(safe_path(path / name, path), MAX_ARTIFACT_BYTES) != checksum:
            raise IngestionError("Approved checkpoint checksum mismatch")
    return path, {
        "kind": "PRETRAINED_PHOBERT",
        "repository": evidence.checkpoint,
        "revision": evidence.revision,
        "license": evidence.license_name,
        "license_evidence_ref": evidence.license_evidence_ref,
        "approval_ref": config.checkpoint_evidence_ref,
        "evidence_sha256": store.digest(evidence.model_dump()),
        "files": evidence.files,
        "origin_verification": "HUMAN_EVIDENCE_BOUND_NOT_INDEPENDENT_LEGAL_AUTHORIZATION",
    }


def pretrained(path: Path, task: baseline.Task):
    from transformers import PhobertTokenizer, RobertaConfig, RobertaForSequenceClassification

    raw_config = store.read_json(path / "config.json")
    if not isinstance(raw_config, dict) or raw_config.get("model_type") != "roberta":
        raise IngestionError("Unsupported pretrained model type")

    config = RobertaConfig.from_pretrained(path, local_files_only=True)
    if config.model_type != "roberta" or config.vocab_size < 1000:
        raise IngestionError("Unsupported pretrained PhoBERT model configuration")
    labels = mapping(task)
    config.num_labels = len(labels)
    config.label2id, config.id2label = labels, {index: label for label, index in labels.items()}
    config.problem_type = "single_label_classification"
    tokenizer = PhobertTokenizer.from_pretrained(path, local_files_only=True)
    if (
        len(tokenizer) > config.vocab_size
        or tokenizer.pad_token_id != config.pad_token_id
        or tokenizer.bos_token_id != config.bos_token_id
        or tokenizer.eos_token_id != config.eos_token_id
    ):
        raise IngestionError("Pretrained tokenizer and encoder configuration are incompatible")
    model, info = RobertaForSequenceClassification.from_pretrained(
        path,
        config=config,
        local_files_only=True,
        use_safetensors=True,
        output_loading_info=True,
    )
    if any(not key.startswith("classifier.") for key in info.get("missing_keys", [])):
        raise IngestionError("Pretrained encoder weights are incomplete")
    if info.get("mismatched_keys") or info.get("error_msgs"):
        raise IngestionError("Pretrained checkpoint loading failed")
    return model, tokenizer


def maximum_length(model, tokenizer, requested: int) -> int:
    # RoBERTa reserves position indices through padding_idx; input includes special tokens.
    limit = min(
        model.config.max_position_embeddings - model.config.pad_token_id - 1,
        tokenizer.model_max_length,
    )
    if requested > limit:
        raise IngestionError("Requested sequence length exceeds model/tokenizer supported limit")
    return requested


def prepare(
    texts: list[str],
    labels: list[str] | None,
    task: baseline.Task,
    tokenizer,
    segmenter: Segmenter,
    max_length: int,
) -> tuple[list[dict], dict]:
    label_ids = mapping(task)
    if not texts or (
        labels is not None
        and (len(texts) != len(labels) or any(label not in label_ids for label in labels))
    ):
        raise IngestionError("Nonempty texts and matching supervised labels required")
    encoded, lengths = [], []
    for index, text in enumerate(texts):
        segmented = segmenter.segment(text)
        full = tokenizer(segmented, truncation=False, return_attention_mask=True)
        lengths.append(len(full["input_ids"]))
        item = tokenizer(
            segmented,
            truncation=True,
            max_length=max_length,
            return_attention_mask=True,
            return_token_type_ids=False,
        )
        if labels is not None:
            item["labels"] = label_ids[labels[index]]
        encoded.append(dict(item))
    return encoded, {
        "records": len(texts),
        "truncated_records": sum(length > max_length for length in lengths),
        "maximum_untruncated_tokens": max(lengths),
        "mean_untruncated_tokens": sum(lengths) / len(lengths),
        "max_length": max_length,
        "padding": "DYNAMIC_PER_BATCH",
    }


def evaluate(
    model, tokenizer, features: list[dict], task: baseline.Task, device: str, batch_size: int
) -> tuple[dict, float]:
    import torch
    from torch.utils.data import DataLoader
    from transformers import DataCollatorWithPadding

    predictions, actual = [], []
    labels = list(mapping(task))
    clock = perf_counter()
    model.eval()
    with torch.inference_mode():
        for batch in DataLoader(
            features, batch_size=batch_size, collate_fn=DataCollatorWithPadding(tokenizer)
        ):
            actual.extend(labels[index] for index in batch.pop("labels").tolist())
            logits = model(**{name: value.to(device) for name, value in batch.items()}).logits
            if not torch.isfinite(logits).all():
                raise IngestionError("Nonfinite validation logits")
            predictions.extend(labels[index] for index in logits.argmax(-1).cpu().tolist())
    if device == "cuda":
        torch.cuda.synchronize()
    return baseline.metrics(actual, predictions, task), perf_counter() - clock


def location(root: Path, run_id: str) -> Path:
    return safe_path(root / "data/private/phobert_runs" / store.identifier(run_id), root)


def inventory(path: Path) -> dict[str, str]:
    result = {}
    for item in sorted(path.rglob("*")):
        item = safe_path(item, path)
        if item.is_file() and item != path / "checksums.json":
            result[item.relative_to(path).as_posix()] = store.file_checksum(
                item, MAX_ARTIFACT_BYTES
            )
    return result


def save(root: Path, metadata: dict, model, best_state: dict, tokenizer, optimizer) -> None:
    import torch
    from safetensors.torch import save_file

    target = location(root, metadata["run_id"])
    store.private_directory(target.parent)
    lock = target.parent / ".writer.lock"
    try:
        handle = lock.open("x")
    except FileExistsError:
        raise IngestionError("PhoBERT artifact writer busy") from None
    try:
        with handle:
            if target.exists():
                raise IngestionError("Immutable PhoBERT run exists; never overwrite")
            with TemporaryDirectory(prefix=".phobert-", dir=target.parent) as temporary:
                work = Path(temporary)
                protect_directory(work)
                # Transformers 5 consumes the supplied dictionary while writing shards.
                model.save_pretrained(
                    work / "best", state_dict=best_state.copy(), safe_serialization=True
                )
                model.save_pretrained(work / "resume", safe_serialization=True)
                tokenizer.save_pretrained(work / "tokenizer")
                state = optimizer.state_dict()
                tensors = {
                    f"{parameter}.{key}": value.detach().cpu().contiguous()
                    for parameter, values in state["state"].items()
                    for key, value in values.items()
                }
                tensors["rng_cpu"] = torch.get_rng_state()
                if metadata["device"] == "cuda":
                    for index, value in enumerate(torch.cuda.get_rng_state_all()):
                        tensors[f"rng_cuda_{index}"] = value
                save_file(tensors, work / "optimizer.safetensors")
                write_json(
                    work / "optimizer.json",
                    {
                        "param_groups": state["param_groups"],
                        "state_keys": {
                            str(key): list(value) for key, value in state["state"].items()
                        },
                        "cuda_rng_count": len(torch.cuda.get_rng_state_all())
                        if metadata["device"] == "cuda"
                        else 0,
                    },
                )
                write_json(work / "run.json", metadata)
                write_json(work / "checksums.json", inventory(work))
                work.rename(target)
    finally:
        lock.unlink()


def inspect(root: Path, registry: Registry, run_id: str) -> dict:
    path = location(root, run_id)
    run = Run.model_validate(store.read_json(path / "run.json"))
    _, current = baseline.development(root, registry, run.dataset.get("dataset_version", ""))
    if run.run_id != run_id or current != run.dataset:
        raise IngestionBlocked("PhoBERT dataset version or provenance mismatch")
    if (
        run.label2id != mapping(run.task)
        or store.digest(run.config.model_dump()) != run.configuration_sha256
    ):
        raise IngestionError("PhoBERT label mapping or configuration mismatch")
    if run.dataset["dataset_type"] == "SYNTHETIC":
        store.require_synthetic(root)
        if run.checkpoint.get("kind") != "TINY_RANDOM_TRANSFORMER":
            raise IngestionBlocked("Synthetic models cannot be represented as pretrained research")
    elif run.checkpoint.get("kind") != "PRETRAINED_PHOBERT":
        raise IngestionBlocked("Random synthetic architecture cannot become research PhoBERT")
    else:
        reference = store.identifier(run.checkpoint.get("approval_ref", ""))
        evidence = CheckpointEvidence.model_validate(
            store.read_json(
                safe_path(root / "data/private/phobert_requests" / (reference + ".json"), root)
            )
        )
        if store.digest(evidence.model_dump()) != run.checkpoint.get("evidence_sha256"):
            raise IngestionBlocked("Pretrained checkpoint review evidence changed")
    expected = store.read_json(path / "checksums.json")
    required = {
        "run.json",
        "optimizer.json",
        "optimizer.safetensors",
        "best/config.json",
        "best/model.safetensors",
        "resume/config.json",
        "resume/model.safetensors",
    }
    if (
        not isinstance(expected, dict)
        or not required <= expected.keys()
        or inventory(path) != expected
    ):
        raise IngestionError("PhoBERT artifact inventory or checksum mismatch")
    for folder in ("best", "resume"):
        config = store.read_json(path / folder / "config.json")
        if (
            not isinstance(config, dict)
            or config.get("model_type") != "roberta"
            or config.get("label2id") != run.label2id
            or config.get("id2label")
            != {str(index): label for label, index in run.label2id.items()}
        ):
            raise IngestionError("Saved model configuration or labels unsupported")
    return {"status": "VERIFIED", "artifact_checksums_verified": True, **run.model_dump()}


def load(
    root: Path,
    registry: Registry,
    run_id: str,
    segmenter_config: SegmentationConfig,
    *,
    resume: bool = False,
):
    run = inspect(root, registry, run_id)
    if (
        run["dependencies"] != dependencies()
        or run["python"] != platform.python_version()
        or run["implementation_sha256"] != implementation()
    ):
        raise IngestionError("PhoBERT reload requires recorded runtime and implementation")
    segmenter = Segmenter(root, segmenter_config)
    if segmenter.metadata != run["segmentation"]:
        raise IngestionError("Training/inference segmentation differs")
    from transformers import (
        PhobertTokenizer,
        PreTrainedTokenizerFast,
        RobertaForSequenceClassification,
    )

    path = location(root, run_id)
    model = RobertaForSequenceClassification.from_pretrained(
        path / ("resume" if resume else "best"),
        local_files_only=True,
        use_safetensors=True,
    )
    tokenizer_class = (
        PreTrainedTokenizerFast
        if run["dataset"]["dataset_type"] == "SYNTHETIC"
        else PhobertTokenizer
    )
    tokenizer = tokenizer_class.from_pretrained(path / "tokenizer", local_files_only=True)
    maximum_length(model, tokenizer, run["config"]["max_length"])
    return model, tokenizer, segmenter, run


def restore_optimizer(root: Path, run_id: str, optimizer, device: str) -> None:
    import torch
    from safetensors.torch import load_file

    path = location(root, run_id)
    document = store.read_json(path / "optimizer.json")
    tensors = load_file(path / "optimizer.safetensors", device="cpu")
    state = {
        int(parameter): {key: tensors[f"{parameter}.{key}"] for key in keys}
        for parameter, keys in document["state_keys"].items()
    }
    optimizer.load_state_dict({"state": state, "param_groups": document["param_groups"]})
    torch.set_rng_state(tensors["rng_cpu"])
    if device == "cuda":
        if document["cuda_rng_count"] != torch.cuda.device_count():
            raise IngestionError("CUDA resume device topology changed")
        torch.cuda.set_rng_state_all(
            [tensors[f"rng_cuda_{index}"] for index in range(document["cuda_rng_count"])]
        )


def fit(
    root: Path,
    registry: Registry,
    dataset: str,
    task: baseline.Task,
    seed: int,
    config: PhobertConfig,
    model,
    tokenizer,
    segmenter: Segmenter,
    checkpoint: dict,
    resume_run: str | None = None,
) -> dict:
    """Internal engine; public research entry never accepts a synthetic source/model."""
    partitions, binding = baseline.development(root, registry, dataset)
    synthetic = binding["dataset_type"] == "SYNTHETIC"
    if synthetic:
        store.require_synthetic(root)
    if synthetic != (checkpoint.get("kind") == "TINY_RANDOM_TRANSFORMER") or synthetic != (
        segmenter.config.backend == "synthetic_fixture"
    ):
        raise IngestionBlocked("Synthetic and research model/segmenter provenance cannot mix")
    config = PhobertConfig.model_validate(config.model_dump())
    previous = None
    if resume_run:
        model, tokenizer, segmenter, previous = load(
            root, registry, resume_run, config.segmenter, resume=True
        )
    maximum_length(model, tokenizer, config.max_length)
    if model.config.label2id != mapping(task):
        raise IngestionError("Model head labels differ from taxonomy order")
    runtime = dependencies()
    import torch
    from torch.utils.data import DataLoader
    from transformers import DataCollatorWithPadding

    device = device_for(config)
    seed_all(seed)
    torch.set_num_threads(config.cpu_threads)
    if device == "cuda" and not os.environ.get("CUBLAS_WORKSPACE_CONFIG"):
        raise IngestionBlocked("Set CUBLAS_WORKSPACE_CONFIG=:4096:8 before CUDA process launch")
    torch.use_deterministic_algorithms(True)
    if device == "cuda":
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
    inputs, exclusions, truncation = {}, {}, {}
    notes = []
    for split, rows in partitions.items():
        texts, labels, exclusions[split] = baseline.select(rows, task)
        if split == "train" and len(set(labels)) < 2:
            raise IngestionError("At least two eligible training classes required")
        if set(labels) != set(mapping(task)):
            notes.append(split.upper() + "_MISSING_TAXONOMY_CLASSES")
        inputs[split], truncation[split] = prepare(
            texts, labels, task, tokenizer, segmenter, config.max_length
        )
    history, best_state, best_score, best_epoch, stale, completed, steps = (
        [],
        None,
        -1.0,
        0,
        0,
        0,
        0,
    )
    if resume_run:
        before, after = previous["config"].copy(), public_config(config)
        before.pop("epochs")
        after.pop("epochs")
        if (
            previous["dataset"] != binding
            or previous["task"] != task
            or previous["seed"] != seed
            or previous["checkpoint"] != checkpoint
            or before != after
            or previous["device"] != device
            or previous["completed_epochs"] >= config.epochs
        ):
            raise IngestionError(
                "Resume configuration, epoch, task or dataset binding incompatible"
            )
        history, completed, steps = (
            previous["history"],
            previous["completed_epochs"],
            previous["optimizer_steps"],
        )
        best_epoch, stale = previous["best_epoch"], previous["stale_evaluations"]
        best_score = max(item["validation"]["macro_f1"] for item in history)
        from safetensors.torch import load_file

        best_state = load_file(location(root, resume_run) / "best/model.safetensors")
    model.to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    if resume_run:
        restore_optimizer(root, resume_run, optimizer, device)
    started, clock = datetime.now(UTC).isoformat(), perf_counter()
    current_run = resume_run
    if stale >= config.patience:
        raise IngestionBlocked("Resume checkpoint already met early-stopping policy")
    for epoch in range(completed, config.epochs):
        generator = torch.Generator().manual_seed(seed + epoch)
        loader = DataLoader(
            inputs["train"],
            batch_size=config.batch_size,
            shuffle=True,
            generator=generator,
            collate_fn=DataCollatorWithPadding(tokenizer),
        )
        iterator, loss_sum, seen = iter(loader), 0.0, 0
        model.train()
        while batches := list(islice(iterator, config.gradient_accumulation)):
            optimizer.zero_grad(set_to_none=True)
            count = sum(len(batch["labels"]) for batch in batches)
            for batch in batches:
                size = len(batch["labels"])
                loss = model(**{name: value.to(device) for name, value in batch.items()}).loss
                if not torch.isfinite(loss):
                    raise IngestionError("Nonfinite training loss")
                (loss * size / count).backward()
                loss_sum += loss.item() * size
                seen += size
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
            if not torch.isfinite(norm) or norm.item() == 0:
                raise IngestionError("No finite nonzero training gradient")
            optimizer.step()
            steps += 1
        if (epoch + 1) % config.eval_every_epochs and epoch + 1 != config.epochs:
            continue
        scores, elapsed = evaluate(
            model, tokenizer, inputs["validation"], task, device, config.batch_size
        )
        history.append(
            {
                "epoch": epoch + 1,
                "training_loss": loss_sum / seen,
                "validation": scores,
                "inference_seconds": elapsed,
                "inference_seconds_per_record": elapsed / len(inputs["validation"]),
            }
        )
        significant = best_state is None or scores["macro_f1"] > best_score + config.min_delta
        if best_state is None or scores["macro_f1"] > best_score:
            best_score, best_epoch = scores["macro_f1"], epoch + 1
            best_state = {
                name: value.detach().cpu().clone() for name, value in model.state_dict().items()
            }
        stale = 0 if significant else stale + 1
        if baseline.development(root, registry, dataset)[1] != binding:
            raise IngestionBlocked("Governed dataset changed during Transformer training")
        parent_run, current_run = current_run, "phobert_" + uuid4().hex
        metadata = Run(
            format_version="phobert-run-1",
            run_id=current_run,
            task=task,
            dataset=binding,
            taxonomy_version=VERSION,
            taxonomy_checksum=CHECKSUM,
            label2id=mapping(task),
            config=PhobertConfig.model_validate(public_config(config)),
            configuration_sha256=store.digest(public_config(config)),
            seed=seed,
            checkpoint=checkpoint,
            segmentation=segmenter.metadata,
            dependencies=runtime,
            implementation_sha256=implementation(),
            python=platform.python_version(),
            device=device,
            completed_epochs=epoch + 1,
            optimizer_steps=steps,
            best_epoch=best_epoch,
            stale_evaluations=stale,
            history=history,
            task_exclusions=exclusions,
            truncation=truncation,
            warnings=notes,
            previous_run=parent_run,
            finite_backward_verified=True,
            started_at=started,
            completed_at=datetime.now(UTC).isoformat(),
            training_seconds=perf_counter() - clock,
        ).model_dump()
        save(root, metadata, model, best_state, tokenizer, optimizer)
        if stale >= config.patience:
            break
    return inspect(root, registry, current_run)


def train(
    root: Path,
    registry: Registry,
    dataset: str,
    task: baseline.Task,
    seed: int = 42,
    config: PhobertConfig | None = None,
    resume_run: str | None = None,
) -> dict:
    _, binding = baseline.development(root, registry, dataset)
    if binding["dataset_type"] != "RESEARCH":
        raise IngestionBlocked("Public research training cannot promote synthetic data")
    config = config or PhobertConfig()
    if config.segmenter.backend != "vncorenlp":
        raise IngestionBlocked("Research PhoBERT requires the real reviewed Vietnamese segmenter")
    dependencies()
    path, checkpoint = approved_checkpoint(root, config)
    segmenter = Segmenter(root, config.segmenter)
    seed_all(seed)
    # Resume loads the saved encoder in fit; avoid allocating a second base encoder.
    model, tokenizer = (None, None) if resume_run else pretrained(path, task)
    return fit(
        root,
        registry,
        dataset,
        task,
        seed,
        config,
        model,
        tokenizer,
        segmenter,
        checkpoint,
        resume_run,
    )


def predict(
    root: Path,
    registry: Registry,
    run_id: str,
    texts: list[str],
    segmenter_config: SegmentationConfig,
    batch_size: int = 8,
) -> dict:
    if not 1 <= batch_size <= 128 or len(texts) > 5000:
        raise IngestionError("Inference batch/input size exceeds bounds")
    model, tokenizer, segmenter, run = load(root, registry, run_id, segmenter_config)
    features, statistics = prepare(
        texts, None, run["task"], tokenizer, segmenter, run["config"]["max_length"]
    )
    import torch
    from torch.utils.data import DataLoader
    from transformers import DataCollatorWithPadding

    model.eval()
    labels, results = list(mapping(run["task"])), []
    with torch.inference_mode():
        for batch in DataLoader(
            features, batch_size=batch_size, collate_fn=DataCollatorWithPadding(tokenizer)
        ):
            scores = model(**batch).logits.softmax(-1)
            if not torch.isfinite(scores).all():
                raise IngestionError("Nonfinite inference logits")
            for row in scores.tolist():
                index = max(range(len(row)), key=row.__getitem__)
                results.append(
                    {"label": labels[index], "label_id": index, "uncalibrated_softmax_scores": row}
                )
    return {
        "dataset_type": run["dataset"]["dataset_type"],
        "predictions": results,
        "score_semantics": run["score_semantics"],
        "truncation": statistics,
    }


def readiness(root: Path, config: PhobertConfig, task: baseline.Task = "topic") -> dict:
    """Explicit local-only probe. Never calls a hub download or reads research records."""
    hardware = {"cpu_runtime_available": False, "cuda_available": False}
    try:
        runtime = dependencies()
        import torch

        hardware = {"cpu_runtime_available": True, "cuda_available": torch.cuda.is_available()}
        device_for(config)
        path, checkpoint = approved_checkpoint(root, config)
        segmenter = Segmenter(root, config.segmenter)
        model, tokenizer = pretrained(path, task)
        maximum_length(model, tokenizer, config.max_length)
        features, _ = prepare(
            ["SYNTHETIC: Ví dụ kỹ thuật tổng hợp về thủ tục."],
            None,
            task,
            tokenizer,
            segmenter,
            config.max_length,
        )
        from transformers import DataCollatorWithPadding

        with torch.inference_mode():
            if not torch.isfinite(
                model(**DataCollatorWithPadding(tokenizer)(features)).logits
            ).all():
                raise IngestionError("Checkpoint forward probe is nonfinite")
        return {
            "status": "PASS",
            "pretrained_checkpoint": "VERIFIED",
            "checkpoint": checkpoint,
            "segmentation": segmenter.metadata,
            "dependencies": runtime,
            "cpu_ready": True,
            **hardware,
        }
    except (IngestionBlocked, IngestionError) as error:
        return {
            "status": "BLOCKED",
            "pretrained_checkpoint": "NOT_VERIFIED",
            "blocker": str(error),
            "weights_downloaded": False,
            "dataset_read": False,
            **hardware,
        }
    except (ValueError, OSError):
        return {
            "status": "BLOCKED",
            "pretrained_checkpoint": "NOT_VERIFIED",
            "blocker": "Checkpoint or segmenter metadata invalid/unavailable",
            "weights_downloaded": False,
            "dataset_read": False,
            **hardware,
        }
