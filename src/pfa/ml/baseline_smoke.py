"""Isolated invented labels exercise software only, never human gold or research metrics."""

from pathlib import Path
from tempfile import TemporaryDirectory

from pfa.annotation import pilot_store as store
from pfa.annotation.agreement import TASKS
from pfa.data import corpus, corpus_smoke
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.registry import Registry
from pfa.data.splitting import SplitConfig
from pfa.ml import baseline


def smoke(registry: Registry) -> dict:
    with TemporaryDirectory(prefix="pfa-baseline-synthetic-") as temporary:
        root = Path(temporary)
        with store.synthetic_session(root):
            rows, provenance = corpus_smoke.fixture()
            built = corpus._publish(
                root, "synthetic_baseline_v1", rows, provenance, SplitConfig(), 42
            )
            try:
                corpus.model_selection(root, registry, "synthetic_baseline_v1", "test")
            except IngestionBlocked:
                pass
            else:
                raise IngestionError("Synthetic model-selection holdout restriction failed")
            tasks = {}
            for task in TASKS:
                run = baseline.train(root, registry, "synthetic_baseline_v1", task)
                partitions, _ = baseline.development(root, registry, "synthetic_baseline_v1")
                text, labels, _ = baseline.select(partitions["validation"], task)
                for model in baseline.MODELS:
                    loaded = baseline.load_model(root, registry, run["run_id"], model)
                    actual = baseline.metrics(labels, loaded.predict(text).tolist(), task)
                    if actual != run["selected"][model]["validation"]:
                        raise IngestionError("Synthetic serialized model predictions changed")
                tasks[task] = {
                    "dataset_type": "SYNTHETIC",
                    "selected": run["selected"],
                    "task_exclusions": run["task_exclusions"],
                    "warnings": run["warnings"],
                    "artifacts_verified": run["artifact_checksums_verified"],
                    "comparison_entries": len(
                        baseline.compare(root, registry, "synthetic_baseline_v1", task)["ranking"]
                    ),
                }
            result = {
                "status": "BASELINE_SMOKE_PASS_SYNTHETIC",
                "dataset_type": "SYNTHETIC",
                "human_gold": False,
                "research_training_completed": False,
                "record_count": len(rows),
                "split_counts": built["report"]["counts"],
                "tasks": tasks,
                "test_access_blocked": True,
                "test_labels_read": False,
                "model_artifacts_verified": True,
            }
    result["temporary_storage_cleaned"] = not root.exists()
    return result
