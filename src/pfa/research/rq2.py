"""Read STEP 11 evaluation manifests, never evaluate, train, tune or read holdout labels."""

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.ml import evaluation, evaluation_policy, model_registry


def final_summary(root, registry, evaluation_id, binding):
    if not evaluation_id:
        return {
            "status": "BLOCKED_ON_RESEARCH_DATA",
            "models": [],
            "reason": "EXISTING_AUTHORIZED_STEP11_FINAL_REPORT_REQUIRED",
        }
    documents, checksum = store.bundle(
        model_registry.base(root) / "final_results" / store.identifier(evaluation_id)
    )
    report = documents["report.json"]
    if (
        report["dataset_type"] != "RESEARCH"
        or report["status"] != "COMPLETED"
        or report["dataset"] != binding
    ):
        raise IngestionBlocked("RQ2 research dataset/final-report provenance mismatch")
    experiment_id = store.identifier(report["experiment_id"])
    experiment_docs, experiment_checksum = store.bundle(
        model_registry.base(root) / "experiments" / experiment_id
    )
    experiment = experiment_docs["experiment.json"]
    if experiment["dataset"] != binding:
        raise IngestionBlocked("RQ2 locked experiment dataset mismatch")
    locks, _ = store.bundle(model_registry.base(root) / "locks" / experiment_id)
    locked = locks["lock.json"]
    if (
        experiment_checksum != report["experiment_sha256"]
        or locked["experiment_sha256"] != experiment_checksum
    ):
        raise IngestionBlocked("RQ2 locked STEP11 protocol mismatch")
    model_registry.authorize(root, locked["approval_ref"], "LOCK_PROTOCOL", experiment_checksum)
    evidence = model_registry.authorize(
        root,
        report["authorization"]["reference"],
        "FINAL_TEST",
        store.digest({"dataset": binding, "experiment_sha256": experiment_checksum}),
    )
    if evidence != report["authorization"]:
        raise IngestionBlocked("RQ2 final authorization changed")
    protocol = evaluation_policy.Protocol.model_validate(experiment["protocol"])
    if report["selected_by_task"] != evaluation.selection(experiment["models"], protocol):
        raise IngestionBlocked("RQ2 validation selection changed")
    records, comparable = [], {}
    if set(report["models"]) != set(experiment["models"]):
        raise IngestionError("RQ2 incomplete final evaluation manifest")
    for identity, result in report["models"].items():
        descriptor = model_registry.inspect(root, registry, identity)["model"]
        if descriptor["taxonomy_version"] != VERSION or descriptor["taxonomy_checksum"] != CHECKSUM:
            raise IngestionBlocked("RQ2 frozen taxonomy mismatch")
        if (
            descriptor != experiment["models"][identity]["descriptor"]
            or store.digest(descriptor) != result["descriptor_sha256"]
        ):
            raise IngestionBlocked("RQ2 model provenance mismatch")
        evaluation.compatible([descriptor], binding)
        if descriptor["family"] == "phobert" and descriptor["model_kind"] != "PRETRAINED_PHOBERT":
            raise IngestionBlocked("Tiny random Transformer is not genuine pretrained PhoBERT")
        if "metrics" not in result:
            records.append(
                {
                    "family": descriptor["family"],
                    "task": descriptor["task"],
                    "status": "INSUFFICIENT_EVIDENCE",
                }
            )
            continue
        sample = {
            "supports": {
                label: v["support"] for label, v in result["metrics"]["per_class"].items()
            },
            "exclusions": result["exclusions"],
        }
        if descriptor["task"] in comparable and comparable[descriptor["task"]] != sample:
            raise IngestionBlocked("RQ2 task-eligible samples are not comparable")
        comparable[descriptor["task"]] = sample
        records.append(
            {
                "family": descriptor["family"],
                "task": descriptor["task"],
                "model_kind": descriptor["model_kind"],
                "metrics": result["metrics"],
                "review": result["review"],
                "evaluation_split": "test",
                "selection_split": "validation",
                "status": "EXISTING_FINAL_REPORT",
            }
        )
    return {
        "status": "AVAILABLE" if any("metrics" in r for r in records) else "INSUFFICIENT_EVIDENCE",
        "evaluation_sha256": checksum,
        "models": records,
        "unavailable": [
            {"task": task, "family": family}
            for task in ("topic", "sentiment", "severity")
            for family in ("lr", "svm", "phobert")
            if not any(
                r["task"] == task and r["family"] == family and "metrics" in r for r in records
            )
        ],
        "test_labels_read": False,
        "ranking_changed": False,
        "limitations": [
            "Existing aggregate results only; no new final-test access or model selection"
        ],
    }
