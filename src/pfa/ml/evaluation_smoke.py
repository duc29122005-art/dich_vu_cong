"""Isolated invented engineering experiment; no human agreement or research results."""

from pathlib import Path
from tempfile import TemporaryDirectory

from pfa.annotation import pilot_store as store
from pfa.data import corpus, corpus_smoke
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.splitting import SplitConfig
from pfa.ml import baseline, evaluation, model_registry
from pfa.ml import evaluation_policy as policy


def smoke(registry):
    with TemporaryDirectory(prefix="pfa-evaluation-synthetic-") as temporary:
        root = Path(temporary)
        with store.synthetic_session(root):
            rows, provenance = corpus_smoke.fixture(240)
            built = corpus._publish(
                root, "synthetic_evaluation_v1", rows, provenance, SplitConfig(), 42
            )
            entry_ids, segmenters = [], {}
            partitions, _ = baseline.development(root, registry, "synthetic_evaluation_v1")
            for task in baseline.TASKS:
                run = baseline.train(
                    root,
                    registry,
                    "synthetic_evaluation_v1",
                    task,
                    config=baseline.BaselineConfig(c_values=[0.5]),
                )
                for family in baseline.MODELS:
                    record = model_registry.register(root, registry, run["run_id"], family)
                    entry_ids.append(record["run_id"])
            # Exercise safe tiny Transformer adapter; never substitute it for pretrained PhoBERT.
            from pfa.ml import phobert, phobert_smoke

            model, tokenizer, segmenter, checkpoint = phobert_smoke.tiny(
                root, [r.content for r in partitions["train"]], "sentiment"
            )
            run = phobert.fit(
                root,
                registry,
                "synthetic_evaluation_v1",
                "sentiment",
                42,
                phobert_smoke.config(),
                model,
                tokenizer,
                segmenter,
                checkpoint,
            )
            record = model_registry.register(root, registry, run["run_id"], "phobert")
            entry_ids.append(record["run_id"])
            segmenters[record["run_id"]] = phobert_smoke.config().segmenter.model_dump()
            experiment = evaluation.prepare(
                root,
                registry,
                "synthetic_evaluation_v1",
                entry_ids,
                demo=True,
                segmenter_configs=segmenters,
            )
            comparison = evaluation.comparison(root, registry, "synthetic_evaluation_v1", demo=True)
            # Known invented scores exercise calibration even with rare role classes.
            labels = list(baseline.TASKS["sentiment"])
            truth = labels * 6
            scores = [[3.0 if label == actual else -1.0 for label in labels] for actual in truth]
            fitted = policy.fit_calibrator(
                scores,
                truth,
                "sentiment",
                policy.Protocol(),
                {
                    "dataset_type": "SYNTHETIC",
                    "role": "calibration",
                    "evaluation_split": "validation",
                },
            )
            values = policy.apply_calibrator(fitted, scores, "sentiment")
            assert values is not None
            calibration = policy.calibration_metrics(truth, values, "sentiment")
            calibration["role"] = "IN_SAMPLE_METHOD_SELF_CHECK_NOT_PERFORMANCE_ESTIMATE"
            first = entry_ids[0]
            model_registry.activate(root, registry, first, demo=True)
            second = model_registry.register(
                root,
                registry,
                model_registry.inspect(root, registry, first, True)["model"]["artifact_run_id"],
                "lr",
                "demo_second",
            )
            model_registry.activate(root, registry, second["run_id"], demo=True)
            model_registry.activate(root, registry, first, demo=True, rollback=True)
            assert model_registry.active(root, registry, "topic", True)["run_id"] == first
            for operation in (
                lambda: corpus.model_selection(root, registry, "synthetic_evaluation_v1", "test"),
                lambda: evaluation.final_evaluate(root, registry, "synthetic_evaluation_v1"),
                lambda: evaluation.lock(root, registry, experiment["experiment_id"], "no_approval"),
                lambda: model_registry.activate(root, registry, first),
            ):
                try:
                    operation()
                except (IngestionBlocked, IngestionError):
                    pass
                else:
                    raise IngestionError("Synthetic isolation or test holdout failed")
            summary = {
                "status": "EVALUATION_SMOKE_PASS_SYNTHETIC",
                "dataset_type": "SYNTHETIC",
                "record_count": len(rows),
                "split_counts": built["report"]["counts"],
                "registered_models": len(entry_ids),
                "tasks": comparison["tasks"],
                "assessment": {
                    key: value["assessment"]
                    for key, value in experiment["report"]["models"].items()
                },
                "known_synthetic_calibration": calibration,
                "artifact_integrity_verified": True,
                "demo_rollback_verified": True,
                "test_labels_read": False,
                "test_access_blocked": True,
                "pretrained_checkpoint": "NOT_VERIFIED",
                "transformer_kind": "SYNTHETIC_TINY_MODEL",
                "research_validity_claimed": False,
            }
    return {**summary, "temporary_storage_cleaned": not root.exists()}
