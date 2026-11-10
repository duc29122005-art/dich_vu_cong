"""Validated local artifacts, frozen taxonomy order and explicit native score semantics."""

from pathlib import Path
from time import perf_counter

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.ml import baseline


def describe(root: Path, registry, run_id: str, family: str) -> dict:
    if family in baseline.MODELS:
        run = baseline.inspect(root, registry, run_id)
        path = baseline.location(root, run_id)
        labels = run["label_mapping"]
        preprocessing = {
            "normalization": "conservative-1",
            "features": run["config"],
            "implementation": run["implementation_sha256"],
        }
        validation = run["selected"][family]["validation"]
        kind = family
    elif family == "phobert":
        from pfa.ml import phobert

        run = phobert.inspect(root, registry, run_id)
        path = phobert.location(root, run_id)
        labels = list(run["label2id"])
        labels.sort(key=run["label2id"].get)
        preprocessing = {
            "normalization": "conservative-1",
            "segmentation": run["segmentation"],
            "max_length": run["config"]["max_length"],
            "implementation": run["implementation_sha256"],
        }
        validation = run["history"][run["best_epoch"] - 1]["validation"]
        kind = (
            "SYNTHETIC_TINY_MODEL"
            if run["checkpoint"]["kind"] == "TINY_RANDOM_TRANSFORMER"
            else "PRETRAINED_PHOBERT"
        )
    else:
        raise IngestionError("Unsupported model family")
    if (
        labels != list(baseline.TASKS[run["task"]])
        or run["taxonomy_checksum"] != CHECKSUM
        or run["taxonomy_version"] != VERSION
    ):
        raise IngestionError("Adapter taxonomy label order mismatch")
    inventory = store.read_json(path / "checksums.json")
    return {
        "adapter_version": "model-adapter-1",
        "artifact_run_id": run_id,
        "family": family,
        "model_kind": kind,
        "task": run["task"],
        "labels": labels,
        "taxonomy_version": VERSION,
        "taxonomy_checksum": CHECKSUM,
        "dataset": run["dataset"],
        "preprocessing": preprocessing,
        "artifact_sha256": store.digest(inventory),
        "packages": run["dependencies"],
        "model_size_bytes": sum(
            store.safe_path(path / name, root).stat().st_size for name in inventory
        ),
        "validation": validation,
        "calibration_status": "UNCALIBRATED",
    }


class Adapter:
    """Construct only after artifact trust review; inspection never deserializes pickle."""

    def __init__(self, root, registry, descriptor, *, trust_ref=None, segmenter_config=None):
        current = describe(root, registry, descriptor["artifact_run_id"], descriptor["family"])
        if current != descriptor:
            raise IngestionError("Adapter artifact or preprocessing changed")
        self.descriptor = descriptor
        self.root = root
        if descriptor["family"] in baseline.MODELS:
            if descriptor["dataset"]["dataset_type"] == "SYNTHETIC":
                store.require_synthetic(root)
            else:
                from pfa.ml.model_registry import authorize

                authorize(root, trust_ref, "TRUST_ARTIFACT", store.digest(descriptor))
            self.model = baseline.load_model(
                root, registry, descriptor["artifact_run_id"], descriptor["family"]
            )
            if not set(self.model.classes_) <= set(descriptor["labels"]):
                raise IngestionError("Classifier classes incompatible")
        else:
            from pfa.ml import phobert

            if segmenter_config is None:
                raise IngestionBlocked("Explicit frozen segmentation configuration required")
            self.model, self.tokenizer, self.segmenter, self.run = phobert.load(
                root, registry, descriptor["artifact_run_id"], segmenter_config
            )

    def predict(self, texts: list[str]) -> dict:
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise IngestionError("Nonempty supported text batch required")
        import numpy as np

        started = perf_counter()
        family, labels = self.descriptor["family"], self.descriptor["labels"]
        if family in baseline.MODELS:
            predicted = self.model.predict(texts).tolist()
            native = np.asarray(self.model.decision_function(texts))
            classes = list(self.model.classes_)
            if native.ndim == 1:
                native = np.column_stack((-native, native))
            scores = (
                native[:, [classes.index(label) for label in labels]].tolist()
                if set(classes) == set(labels)
                else None
            )
            semantics = "UNCALIBRATED_DECISION_SCORES"
        else:
            import torch
            from transformers import DataCollatorWithPadding

            from pfa.ml import phobert

            features, _ = phobert.prepare(
                texts,
                None,
                self.descriptor["task"],
                self.tokenizer,
                self.segmenter,
                self.run["config"]["max_length"],
            )
            collator = DataCollatorWithPadding(self.tokenizer, return_tensors="pt")
            logits = []
            self.model.to("cpu").eval()
            with torch.no_grad():
                for start in range(0, len(features), 16):
                    batch = collator(features[start : start + 16])
                    logits.extend(self.model(**batch).logits.tolist())
            scores = logits
            predicted = [labels[int(np.argmax(row))] for row in logits]
            semantics = "UNCALIBRATED_LOGITS_NOT_CALIBRATED_PROBABILITIES"
        return {
            "labels": predicted,
            "scores": scores,
            "score_type": semantics,
            "label_order": labels,
            "batch_latency_seconds": perf_counter() - started,
        }
