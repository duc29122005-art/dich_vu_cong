"""Validation-only preparation and explicit, one-shot governed final evaluation."""

from pfa.annotation import pilot_store as store
from pfa.data import corpus
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.ml import baseline
from pfa.ml import evaluation_policy as policy
from pfa.ml import model_adapters as adapters
from pfa.ml import model_registry as registry_store


def compatible(descriptors: list[dict], binding: dict) -> None:
    if not descriptors:
        raise IngestionError("NOT_AVAILABLE: no registered compatible experiments")
    for item in descriptors:
        if (
            item["dataset"] != binding
            or item["task"] not in baseline.TASKS
            or item["labels"] != list(baseline.TASKS[item["task"]])
            or item["taxonomy_checksum"] != descriptors[0]["taxonomy_checksum"]
            or item["taxonomy_version"] != descriptors[0]["taxonomy_version"]
            or item["preprocessing"].get("normalization") != policy.Protocol().normalization
        ):
            raise IngestionError("Dataset, taxonomy or preprocessing incompatible with protocol")
        if binding["dataset_type"] == "RESEARCH" and item["model_kind"] == "SYNTHETIC_TINY_MODEL":
            raise IngestionBlocked(
                "Random synthetic Transformer cannot substitute for pretrained research model"
            )
    # Different feature families are allowed; within a family freeze the same preprocessing.
    for task in baseline.TASKS:
        for family in ("lr", "svm", "phobert"):
            settings = {
                store.digest(i["preprocessing"])
                for i in descriptors
                if i["task"] == task and i["family"] == family
            }
            if len(settings) > 1:
                raise IngestionError("Within-family preprocessing mismatch")


def selection(models: dict, protocol: policy.Protocol) -> dict:
    """Freeze winners from validation before test access, including deterministic tie breaks."""
    result = {}
    for task in baseline.TASKS:
        candidates = [
            identity for identity, model in models.items() if model["descriptor"]["task"] == task
        ]
        if candidates:
            result[task] = min(
                candidates,
                key=lambda identity: (
                    -models[identity]["descriptor"]["validation"]["macro_f1"],
                    protocol.family_order.index(models[identity]["descriptor"]["family"]),
                    identity,
                ),
            )
    return result


def comparison(root, registry, dataset, *, demo=False, protocol=None) -> dict:
    protocol = protocol or policy.Protocol()
    _, binding = baseline.development(root, registry, dataset)
    records = [
        r
        for r in registry_store.entries(root, registry, demo)
        if r["model"]["dataset"]["dataset_version"] == dataset
    ]
    compatible([r["model"] for r in records], binding)
    tasks = {}
    for task in baseline.TASKS:
        available = [r for r in records if r["model"]["task"] == task]
        ranked = sorted(
            available,
            key=lambda r: (
                -r["model"]["validation"]["macro_f1"],
                protocol.family_order.index(r["model"]["family"]),
                r["run_id"],
            ),
        )
        tasks[task] = {
            "ranking": [
                {
                    "run_id": r["run_id"],
                    "family": r["model"]["family"],
                    "model_kind": r["model"]["model_kind"],
                    "validation_macro_f1": r["model"]["validation"]["macro_f1"],
                }
                for r in ranked
            ],
            "unavailable_families": [
                f
                for f in protocol.family_order
                if not any(r["model"]["family"] == f for r in ranked)
            ],
        }
    result = {
        "report_version": "comparison-1",
        "dataset": binding,
        "dataset_type": binding["dataset_type"],
        "evaluation_split": "validation",
        "protocol": protocol.model_dump(),
        "tasks": tasks,
        "research_validity_claimed": False,
        "limitations": [
            "Selected validation results are optimistic; no final holdout accessed",
            "Missing families remain unavailable; synthetic tiny model is not pretrained PhoBERT",
        ],
    }
    identity = registry_store.unique_id("comparison")
    store.publish(registry_store.base(root) / "comparisons" / identity, {"report.json": result})
    # Markdown contains aggregate scores only. JSON bundle is authoritative and immutable.
    from pfa.data.official_io import safe_path

    path = safe_path(root / "reports/models" / (identity + ".md"), root)
    store.private_directory(path.parent)
    lines = [
        f"# {binding['dataset_type']} validation comparison",
        "",
        "No research validity claimed.",
        "",
        "| Task | Family | Macro-F1 |",
        "|---|---|---:|",
    ]
    for task, value in tasks.items():
        lines.extend(
            f"| {task} | {r['family']} | {r['validation_macro_f1']:.6f} |" for r in value["ranking"]
        )
    with path.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    return {"comparison_id": identity, **result}


def segmentation(configs, identity):
    if identity not in configs:
        return None
    from pfa.ml.segmentation import SegmentationConfig

    return SegmentationConfig.model_validate(configs[identity])


def prepare(
    root,
    registry,
    dataset,
    entry_ids,
    *,
    demo=False,
    protocol=None,
    trust_refs=None,
    segmenter_configs=None,
):
    protocol, trust_refs, segmenter_configs = (
        protocol or policy.Protocol(),
        trust_refs or {},
        segmenter_configs or {},
    )
    partitions, binding = baseline.development(root, registry, dataset)
    if len(set(entry_ids)) != len(entry_ids):
        raise IngestionError("Duplicate eligible model entries")
    records = [registry_store.inspect(root, registry, identity, demo) for identity in entry_ids]
    compatible([r["model"] for r in records], binding)
    indices, membership = policy.roles(partitions["validation"], protocol)
    results = {}
    for record in records:
        identity, descriptor = record["run_id"], record["model"]
        adapter = adapters.Adapter(
            root,
            registry,
            descriptor,
            trust_ref=trust_refs.get(identity),
            segmenter_config=segmentation(segmenter_configs, identity),
        )
        observations = {}
        for name, members in indices.items():
            rows = [partitions["validation"][i] for i in members]
            eligible = [r for r in rows if r.eligible[descriptor["task"]]]
            texts, actual, excluded = baseline.select(rows, descriptor["task"])
            prediction = adapter.predict(texts) if texts else None
            observations[name] = (actual, prediction, excluded, eligible)
        provenance = {
            "evaluation_split": "validation",
            "dataset": binding,
            "model_sha256": store.digest(descriptor),
            "protocol_sha256": store.digest(protocol.model_dump()),
            "roles": membership,
        }
        actual, predicted, _, _ = observations["calibration"]
        calibrator = policy.fit_calibrator(
            predicted["scores"] if predicted else None,
            actual,
            descriptor["task"],
            protocol,
            provenance,
        )
        actual, predicted, _, _ = observations["threshold"]
        values = policy.apply_calibrator(
            calibrator, predicted["scores"] if predicted else None, descriptor["task"]
        )
        threshold = policy.select_threshold(
            actual,
            predicted["labels"] if predicted else [],
            values,
            descriptor["task"],
            protocol,
            provenance,
        )
        actual, predicted, exclusions, eligible = observations["assessment"]
        assessment = {"status": "INSUFFICIENT_SUPPORT", "metrics": None}
        if actual:
            values = policy.apply_calibrator(calibrator, predicted["scores"], descriptor["task"])
            decisions = policy.review(
                predicted["labels"],
                values,
                descriptor["task"],
                threshold,
                protocol,
                calibrated=values is not None,
            )
            assessment = {
                "status": "DESCRIPTIVE_POST_SELECTION_VALIDATION",
                "metrics": policy.metrics(
                    actual,
                    predicted["labels"],
                    descriptor["task"],
                    predicted["batch_latency_seconds"],
                    descriptor["model_size_bytes"],
                ),
                "review": policy.review_metrics(
                    actual, predicted["labels"], decisions, descriptor["task"]
                ),
                "calibration": policy.calibration_metrics(actual, values, descriptor["task"])
                if values
                else None,
                "confidence_interval": policy.bootstrap(
                    actual,
                    predicted["labels"],
                    descriptor["task"],
                    [r.group_id for r in eligible],
                    protocol,
                ),
                "exclusions": exclusions,
            }
        results[identity] = {
            "descriptor": descriptor,
            "calibrator": calibrator,
            "threshold": threshold,
            "assessment": assessment,
            "role_exclusions": {k: v[2] for k, v in observations.items()},
        }
    report = {
        "experiment_version": "evaluation-1",
        "dataset": binding,
        "protocol": protocol.model_dump(),
        "roles": membership,
        "models": results,
        "selected_by_task": selection(results, protocol),
        "test_labels_read": False,
        "trust_references": trust_refs,
        "limitation": "Post-selection validation assessment; not independent final performance",
    }
    identity = registry_store.unique_id("experiment")
    checksum = store.publish(
        registry_store.base(root) / "experiments" / identity, {"experiment.json": report}
    )
    return {"experiment_id": identity, "sha256": checksum, "report": report}


def lock(root, registry, experiment_id, approval_ref):
    documents, checksum = store.bundle(
        registry_store.base(root) / "experiments" / store.identifier(experiment_id)
    )
    experiment = documents["experiment.json"]
    if experiment["dataset"]["dataset_type"] != "RESEARCH":
        raise IngestionBlocked("Synthetic protocol cannot authorize research holdout")
    _, binding = baseline.development(root, registry, experiment["dataset"]["dataset_version"])
    if binding != experiment["dataset"]:
        raise IngestionBlocked("Frozen dataset changed")
    evidence = registry_store.authorize(root, approval_ref, "LOCK_PROTOCOL", checksum)
    result = {
        "experiment_id": experiment_id,
        "experiment_sha256": checksum,
        "authorization": evidence,
        "approval_ref": approval_ref,
    }
    store.publish(registry_store.base(root) / "locks" / experiment_id, {"lock.json": result})
    return result


def final_evaluate(
    root,
    registry,
    dataset,
    experiment_id=None,
    approval_ref=None,
    evaluation_ref=None,
    segmenter_configs=None,
):
    # Governed reader validates permission, human taxonomy/gold/pilot approvals before all access.
    _, binding = baseline.development(root, registry, dataset)
    if binding["dataset_type"] != "RESEARCH" or not all(
        (experiment_id, approval_ref, evaluation_ref)
    ):
        raise IngestionBlocked(
            "Locked research protocol and explicit final-test human authorization required"
        )
    documents, checksum = store.bundle(
        registry_store.base(root) / "experiments" / store.identifier(experiment_id)
    )
    experiment = documents["experiment.json"]
    locked, _ = store.bundle(registry_store.base(root) / "locks" / experiment_id)
    if not experiment["models"]:
        raise IngestionBlocked("Registered eligible models required for final evaluation")
    if locked["lock.json"]["experiment_sha256"] != checksum or experiment["dataset"] != binding:
        raise IngestionBlocked("Locked experiment or dataset binding changed")
    registry_store.authorize(root, locked["lock.json"]["approval_ref"], "LOCK_PROTOCOL", checksum)
    target = store.digest({"dataset": binding, "experiment_sha256": checksum})
    evidence = registry_store.authorize(root, approval_ref, "FINAL_TEST", target)
    protocol, loaded = policy.Protocol.model_validate(experiment["protocol"]), {}
    if experiment.get("selected_by_task") != selection(experiment["models"], protocol):
        raise IngestionBlocked("Locked validation model selection changed")
    for identity, model in experiment["models"].items():
        record = registry_store.inspect(root, registry, identity)
        if record["model"] != model["descriptor"]:
            raise IngestionBlocked("Registered eligible model changed")
        provenance = {
            "evaluation_split": "validation",
            "dataset": binding,
            "model_sha256": store.digest(record["model"]),
            "protocol_sha256": store.digest(protocol.model_dump()),
            "roles": experiment["roles"],
        }
        if any(model[key]["provenance"] != provenance for key in ("threshold", "calibrator")):
            raise IngestionBlocked("Calibration or threshold provenance mismatch")
        loaded[identity] = adapters.Adapter(
            root,
            registry,
            record["model"],
            trust_ref=experiment["trust_references"].get(identity),
            segmenter_config=segmentation(segmenter_configs or {}, identity),
        )
    # Reserve by immutable test content AND membership, not a renewable authorization reference.
    reservation = "holdout_" + store.digest(
        {"test": binding["split_sha256"]["test"], "membership": binding["test_membership_checksum"]}
    )
    store.publish(
        registry_store.base(root) / "final_access" / reservation,
        {
            "access.json": {
                "experiment_id": experiment_id,
                "authorization": evidence,
                "evaluation_ref": store.identifier(evaluation_ref),
                "status": "RESERVED_NO_RETRY",
            }
        },
    )
    result_id = registry_store.unique_id("final")
    try:
        rows = corpus.evaluation_data(root, registry, dataset, evaluation_ref)
        results = {}
        for identity, adapter in loaded.items():
            task = adapter.descriptor["task"]
            texts, actual, excluded = baseline.select(rows, task)
            if not actual:
                results[identity] = {
                    "status": "INSUFFICIENT_SUPPORT",
                    "descriptor_sha256": store.digest(adapter.descriptor),
                    "exclusions": excluded,
                }
                continue
            prediction = adapter.predict(texts)
            model = experiment["models"][identity]
            values = policy.apply_calibrator(model["calibrator"], prediction["scores"], task)
            decisions = policy.review(
                prediction["labels"],
                values,
                task,
                model["threshold"],
                protocol,
                calibrated=values is not None,
            )
            results[identity] = {
                "descriptor_sha256": store.digest(adapter.descriptor),
                "metrics": policy.metrics(
                    actual,
                    prediction["labels"],
                    task,
                    prediction["batch_latency_seconds"],
                    adapter.descriptor["model_size_bytes"],
                ),
                "review": policy.review_metrics(actual, prediction["labels"], decisions, task),
                "calibration": policy.calibration_metrics(actual, values, task) if values else None,
                "exclusions": excluded,
            }
        report = {
            "dataset_type": "RESEARCH",
            "dataset": binding,
            "experiment_sha256": checksum,
            "experiment_id": experiment_id,
            "selected_by_task": experiment["selected_by_task"],
            "authorization": evidence,
            "models": results,
            "status": "COMPLETED",
        }
        store.publish(
            registry_store.base(root) / "final_results" / result_id, {"report.json": report}
        )
    except Exception:
        store.publish(
            registry_store.base(root) / "final_failures" / result_id,
            {"failure.json": {"status": "FAILED_NO_RETRY", "reservation": reservation}},
        )
        raise
    return {"evaluation_id": result_id, **report}
