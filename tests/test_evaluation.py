"""Invented offline engineering checks; mocked gates never establish human authorization."""

import copy
import json
import pickle
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import test_corpus

from pfa.annotation import pilot_store as store
from pfa.cli import main
from pfa.data import corpus, corpus_smoke
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.ml import baseline, evaluation, model_adapters, model_registry
from pfa.ml import evaluation_policy as policy

built = test_corpus.built
ROOT = Path(__file__).resolve().parents[1]
VALIDATION = {"evaluation_split": "validation"}


@pytest.fixture
def registered(built):
    root, registry, *_ = built
    run = baseline.train(
        root, registry, "synthetic_v1", "sentiment", config=baseline.BaselineConfig(c_values=[0.5])
    )
    record = model_registry.register(root, registry, run["run_id"], "lr")
    return root, registry, run, record


def test_protocol_defaults():
    assert (
        policy.Protocol.model_validate(store.read_json(ROOT / "configs/evaluation_v1.yaml"))
        == policy.Protocol()
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"role_ratios": [0.5, 0.5, 0]},
        {"role_ratios": [0.1, 0.1, 0.1]},
        {"threshold_grid": [0.8, 0.5]},
        {"threshold_grid": [float("nan")]},
        {"family_order": ["phobert", "lr", "svm"]},
        {"maximum_selective_risk": float("nan")},
        {"selection_metric": "test_accuracy"},
        {"bootstrap_replicates": 0},
    ],
)
def test_invalid_protocol(changes):
    with pytest.raises(ValueError):
        policy.Protocol(**changes)


def test_metrics_known_weighted_normalized_and_resources():
    result = policy.metrics(
        ["negative", "negative", "neutral", "positive"],
        ["negative", "positive", "negative", "positive"],
        "sentiment",
        2.0,
        123,
    )
    assert result["accuracy"] == 0.5
    assert result["precision_weighted"] == pytest.approx(3 / 8)
    assert result["recall_weighted"] == 0.5
    assert result["macro_f1"] == pytest.approx(7 / 18)
    assert result["throughput_records_per_second"] == 2
    assert result["model_size_bytes"] == 123
    assert result["normalized_confusion_matrix"] == [[0.5, 0, 0.5], [1, 0, 0], [0, 0, 1]]


def test_rare_and_absent_high():
    result = policy.metrics(["low"], ["high"], "severity")
    assert result["severity_high_recall"] is None
    assert result["per_class"]["high"]["support"] == 0
    assert result["throughput_records_per_second"] is None
    assert policy.metrics(["high"], ["low"], "severity")["severity_high_recall"] == 0


@pytest.mark.parametrize(
    "actual,predicted,task,seconds",
    [
        ([], [], "topic", 0),
        (["unknown"], ["low"], "severity", 0),
        (["low"], ["low"], "severity", -1),
        (["low"], ["low"], "severity", float("nan")),
    ],
)
def test_invalid_metrics(actual, predicted, task, seconds):
    with pytest.raises(IngestionError):
        policy.metrics(actual, predicted, task, seconds)


def test_group_roles_deterministic_disjoint():
    rows, _ = corpus_smoke.fixture(120)
    indices, manifest = policy.roles(rows, policy.Protocol())
    assert (indices, manifest) == policy.roles(rows, policy.Protocol())
    assert sorted(i for members in indices.values() for i in members) == list(range(120))
    membership = {i: name for name, members in indices.items() for i in members}
    assert all(membership[i] == membership[i + 1] for i in range(0, 120, 2))
    changed, _ = policy.roles(rows, policy.Protocol(seed=43))
    assert changed != indices
    assert all("membership_sha256" in value for value in manifest.values())
    with pytest.raises(IngestionError):
        policy.roles(rows[:2], policy.Protocol())


def test_bootstrap_reproducible_and_unsupported():
    actual = list(baseline.TASKS["sentiment"]) * 20
    groups = [f"g{i}" for i in range(60)]
    protocol = policy.Protocol(bootstrap_replicates=100)
    result = policy.bootstrap(actual, actual, "sentiment", groups, protocol)
    assert result["interval"] == [1, 1]
    assert result == policy.bootstrap(actual, actual, "sentiment", groups, protocol)
    assert (
        policy.bootstrap(actual[:2], actual[:2], "sentiment", groups[:2], protocol)["interval"]
        is None
    )
    with pytest.raises(IngestionError):
        policy.bootstrap(actual, actual, "sentiment", [], protocol)


def calibration_fixture():
    actual = list(baseline.TASKS["sentiment"]) * 6
    scores = [
        [3 if label == value else -1 for label in baseline.TASKS["sentiment"]] for value in actual
    ]
    fitted = policy.fit_calibrator(
        scores,
        actual,
        "sentiment",
        policy.Protocol(),
        {**VALIDATION, "role": "calibration", "dataset_type": "SYNTHETIC"},
    )
    return actual, scores, fitted


def test_calibration_safe_json_order_brier():
    actual, scores, fitted = calibration_fixture()
    assert fitted["labels"] == list(baseline.TASKS["sentiment"])
    assert fitted["fitting_role"] == "calibration"
    assert policy.apply_calibrator(
        json.loads(json.dumps(fitted)), scores, "sentiment"
    ) == policy.apply_calibrator(fitted, scores, "sentiment")
    perfect = np.eye(3)[[list(baseline.TASKS["sentiment"]).index(v) for v in actual]].tolist()
    report = policy.calibration_metrics(actual, perfect, "sentiment")
    assert report["multiclass_brier_sum"] == 0 and report["top_label_ece_10_bins"] == 0
    assert sum(b["count"] for b in report["reliability_bins"]) == len(actual)
    assert (
        policy.fit_calibrator(None, actual, "sentiment", policy.Protocol(), VALIDATION)["status"]
        == "UNAVAILABLE"
    )
    with pytest.raises(IngestionError):
        policy.fit_calibrator([[1, 2, 3]], ["unknown"], "severity", policy.Protocol(), VALIDATION)


@pytest.mark.parametrize("corruption", ["labels", "coefficients", "intercepts"])
def test_calibrator_corruption(corruption):
    _, scores, fitted = calibration_fixture()
    fitted[corruption] = [float("nan")]
    with pytest.raises(IngestionError):
        policy.apply_calibrator(fitted, scores, "sentiment")


@pytest.mark.parametrize(
    "values", [[[1, 0]], [[-0.1, 0.1, 1]], [[float("nan"), 0, 1]], [[1, 1, 1]]]
)
def test_invalid_probability_matrix(values):
    with pytest.raises(IngestionError):
        policy.calibration_metrics(["negative"], values, "sentiment")


def test_threshold_and_fail_closed_review():
    actual, scores, fitted = calibration_fixture()
    values = policy.apply_calibrator(fitted, scores, "sentiment")
    threshold = policy.select_threshold(
        actual, actual, values, "sentiment", policy.Protocol(), {**VALIDATION, "role": "threshold"}
    )
    decisions = policy.review(
        actual, values, "sentiment", threshold, policy.Protocol(), calibrated=True
    )
    assert all(not row["requires_review"] for row in decisions)
    report = policy.review_metrics(actual, actual, decisions, "sentiment")
    assert report["selective_risk"] == 0 and report["automated_coverage"] == 1
    for kwargs in (
        {"calibrated": False},
        {"calibrated": True, "unsupported_input": True},
        {"calibrated": True, "invalid_artifact": True},
        {"calibrated": True, "conflicts": True},
    ):
        assert all(
            r["requires_review"]
            for r in policy.review(
                actual, values, "sentiment", threshold, policy.Protocol(), **kwargs
            )
        )
    high = policy.review(
        ["high"], [[0, 0, 1]], "severity", threshold, policy.Protocol(), calibrated=True
    )
    assert high[0]["requires_review"] and not high[0]["administrative_decision_allowed"]
    wrong = policy.review(
        ["negative"], [[0, 0, 1]], "sentiment", threshold, policy.Protocol(), calibrated=True
    )
    assert "CALIBRATED_CLASS_CONFLICT" in wrong[0]["reasons"]
    assert (
        policy.select_threshold(actual, actual, None, "sentiment", policy.Protocol(), VALIDATION)[
            "status"
        ]
        == "ALL_REQUIRE_REVIEW"
    )


def test_critical_miss_and_zero_automated():
    decisions = [{"requires_review": False}, {"requires_review": True}]
    result = policy.review_metrics(["high", "low"], ["low", "low"], decisions, "severity")
    assert result["critical_miss_count"] == 1 and result["severity_high_recall"] == 0
    assert (
        policy.review_metrics(["low"], ["low"], [{"requires_review": True}], "severity")[
            "selective_risk"
        ]
        is None
    )


@pytest.mark.parametrize("split", ["test", "train", "unknown", None])
def test_calibration_and_threshold_cannot_fit_test(split):
    provenance = {"evaluation_split": split}
    with pytest.raises(IngestionBlocked):
        policy.fit_calibrator([[1, 2, 3]], ["negative"], "sentiment", policy.Protocol(), provenance)
    with pytest.raises(IngestionBlocked):
        policy.select_threshold(
            ["negative"], ["negative"], [[1, 0, 0]], "sentiment", policy.Protocol(), provenance
        )


def test_missing_score_classes_and_descriptor_mismatch(registered, monkeypatch):
    root, registry, _, record = registered
    adapter = model_adapters.Adapter(root, registry, record["model"])

    class Binary:
        classes_ = np.array(["negative", "positive"])

        def predict(self, texts):
            return np.array(["positive"] * len(texts))

        def decision_function(self, texts):
            return np.ones(len(texts))

    adapter.model = Binary()
    assert adapter.predict(["SYNTHETIC: thiếu ngữ cảnh"])["scores"] is None
    changed = copy.deepcopy(record["model"])
    changed["labels"] = list(reversed(changed["labels"]))
    monkeypatch.setattr(pickle, "load", lambda *args: pytest.fail("Mismatched model loaded"))
    with pytest.raises(IngestionError):
        model_adapters.Adapter(root, registry, changed)


def test_symlink_storage_rejected(registered):
    root, registry, _, record = registered
    alias = root / "registry_alias"
    try:
        alias.symlink_to(model_registry.base(root), target_is_directory=True)
    except OSError:
        # Windows may deny symlink creation; traversal rejection is still exercised.
        with pytest.raises(IngestionError):
            model_registry.inspect(root, registry, "../outside", True)
    else:
        with pytest.raises(IngestionError):
            store.safe_path(alias / "demo/entries" / record["run_id"], root)


@pytest.mark.parametrize("family", ["lr", "svm"])
def test_adapter_label_order_native_scores(registered, family):
    root, registry, run, _ = registered
    descriptor = model_adapters.describe(root, registry, run["run_id"], family)
    adapter = model_adapters.Adapter(root, registry, descriptor)
    prediction = adapter.predict(["SYNTHETIC: hướng dẫn thủ tục rõ ràng."])
    assert prediction["label_order"] == list(baseline.TASKS["sentiment"])
    assert prediction["score_type"] == "UNCALIBRATED_DECISION_SCORES"
    native = adapter.model.decision_function(["SYNTHETIC: hướng dẫn thủ tục rõ ràng."])[0]
    assert prediction["scores"][0] == [
        native[list(adapter.model.classes_).index(v)] for v in descriptor["labels"]
    ]
    with pytest.raises(IngestionError):
        adapter.predict([" "])


def test_untrusted_pickle_never_loaded(registered, monkeypatch):
    root, registry, _, record = registered
    descriptor = copy.deepcopy(record["model"])
    descriptor["dataset"]["dataset_type"] = "RESEARCH"
    monkeypatch.setattr(model_adapters, "describe", lambda *args: descriptor)
    monkeypatch.setattr(pickle, "load", lambda *args: pytest.fail("Untrusted pickle loaded"))
    with pytest.raises(IngestionBlocked):
        model_adapters.Adapter(root, registry, descriptor)


def test_registry_inspection_no_pickle_and_tamper(registered, monkeypatch):
    root, registry, run, record = registered
    monkeypatch.setattr(pickle, "load", lambda *args: pytest.fail("Inspection loaded pickle"))
    assert model_registry.inspect(root, registry, record["run_id"], True) == record
    (baseline.location(root, run["run_id"]) / "lr.pkl").write_bytes(b"SYNTHETIC CORRUPTION")
    with pytest.raises(IngestionError, match="checksum"):
        model_registry.inspect(root, registry, record["run_id"], True)


def test_demo_history_activation_rollback_isolation(registered):
    root, registry, run, first = registered
    second = model_registry.register(root, registry, run["run_id"], "lr", "demo_second")
    with pytest.raises(IngestionBlocked):
        model_registry.activate(root, registry, second["run_id"], demo=True, rollback=True)
    model_registry.activate(root, registry, first["run_id"], demo=True)
    model_registry.activate(root, registry, second["run_id"], demo=True)
    model_registry.activate(root, registry, first["run_id"], demo=True, rollback=True)
    assert model_registry.active(root, registry, "sentiment", True)["run_id"] == first["run_id"]
    assert len(model_registry.history(root, True)[0]) == 3
    with pytest.raises(IngestionError):
        model_registry.activate(root, registry, first["run_id"])
    with pytest.raises(IngestionError, match="Immutable"):
        model_registry.register(root, registry, run["run_id"], "lr")


def test_history_corruption(registered):
    root, registry, _, record = registered
    model_registry.activate(root, registry, record["run_id"], demo=True)
    path = model_registry.namespace(root, True) / "events/event_00000001/event.json"
    path.write_text("{}")
    with pytest.raises(IngestionError):
        model_registry.history(root, True)


@pytest.mark.parametrize(
    "field", ["dataset", "labels", "taxonomy_version", "taxonomy_checksum", "preprocessing"]
)
def test_comparison_mismatch(registered, field):
    _, _, _, record = registered
    original = record["model"]
    changed = copy.deepcopy(original)
    changed[field] = (
        {}
        if field == "dataset"
        else ["invalid"]
        if field == "labels"
        else {"normalization": "wrong"}
        if field == "preprocessing"
        else "invalid"
    )
    with pytest.raises(IngestionError):
        evaluation.compatible([original, changed], original["dataset"])


def test_comparison_and_validation_preparation_no_test(registered, monkeypatch, caplog):
    root, registry, _, record = registered
    original = corpus._read_partition

    def guarded(path):
        assert path.name != "test.parquet"
        return original(path)

    monkeypatch.setattr(corpus, "_read_partition", guarded)
    comparison = evaluation.comparison(root, registry, "synthetic_v1", demo=True)
    assert comparison["tasks"]["topic"]["ranking"] == []
    assert "phobert" in comparison["tasks"]["sentiment"]["unavailable_families"]
    experiment = evaluation.prepare(root, registry, "synthetic_v1", [record["run_id"]], demo=True)
    assert not experiment["report"]["test_labels_read"]
    assert "SYNTHETIC:" not in json.dumps(experiment) + caplog.text
    for operation in (
        lambda: evaluation.lock(root, registry, experiment["experiment_id"], "no_approval"),
        lambda: evaluation.final_evaluate(root, registry, "synthetic_v1"),
    ):
        with pytest.raises(IngestionBlocked):
            operation()


def test_registry_research_promotion_denial(registered, monkeypatch):
    root, registry, _, record = registered
    monkeypatch.setattr(model_registry, "inspect", lambda *args: record)
    with pytest.raises(IngestionBlocked, match="Research approval"):
        model_registry.activate(root, registry, record["run_id"])


@pytest.mark.parametrize(
    "reason", ["permission missing", "revoked", "taxonomy pending", "gold unavailable"]
)
def test_research_gate_precedes_test_and_model_access(built, monkeypatch, reason):
    root, registry, *_ = built

    def blocked(*args):
        raise IngestionBlocked(reason)

    monkeypatch.setattr(corpus, "_authorized_manifest", blocked)
    monkeypatch.setattr(
        corpus, "evaluation_data", lambda *args: pytest.fail("Unauthorized holdout read")
    )
    with pytest.raises(IngestionBlocked):
        evaluation.final_evaluate(root, registry, "research_v1")


def test_human_evidence_revoked_expired_and_bound(tmp_path):
    target = "a" * 64
    document = {
        "action": "FINAL_TEST",
        "target_sha256": target,
        "reviewer_id": "synthetic_reviewer",
        "reviewer_role": "student_researcher",
        "evidence_reference": "synthetic_evidence",
        "reviewed_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "decision": "REVOKED",
        "human_verified": True,
    }
    path = model_registry.base(tmp_path) / "requests/synthetic_test.json"
    path.parent.mkdir(parents=True)
    for changes in (
        {},
        {
            "decision": "APPROVED",
            "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        },
        {"decision": "APPROVED", "target_sha256": "b" * 64},
        {"decision": "APPROVED", "human_verified": False},
    ):
        path.write_text(json.dumps(document | changes))
        with pytest.raises(IngestionBlocked):
            model_registry.authorize(tmp_path, "synthetic_test", "FINAL_TEST", target)
    with pytest.raises(IngestionError):
        model_registry.authorize(tmp_path, "../escape", "FINAL_TEST", target)


def test_once_only_final_access_audit_mocked(tmp_path, monkeypatch):
    """Mock ALL research gates; verify reservation precedes test read and survives failure."""
    binding = {
        "dataset_type": "RESEARCH",
        "dataset_version": "mock_only",
        "split_sha256": {"test": "a" * 64},
        "test_membership_checksum": "b" * 64,
    }
    protocol = policy.Protocol().model_dump()
    descriptor = {"MOCK_ONLY": True, "task": "topic", "family": "lr", "validation": {"macro_f1": 0}}
    provenance = {
        **VALIDATION,
        "dataset": binding,
        "model_sha256": store.digest(descriptor),
        "protocol_sha256": store.digest(protocol),
        "roles": {},
    }
    document = {
        "dataset": binding,
        "models": {
            "mock_model": {
                "descriptor": descriptor,
                "threshold": {"provenance": provenance},
                "calibrator": {"provenance": provenance},
            }
        },
        "protocol": protocol,
        "roles": {},
        "trust_references": {},
        "selected_by_task": {"topic": "mock_model"},
    }
    checksum = store.publish(
        model_registry.base(tmp_path) / "experiments/mock_experiment", {"experiment.json": document}
    )
    store.publish(
        model_registry.base(tmp_path) / "locks/mock_experiment",
        {"lock.json": {"experiment_sha256": checksum, "approval_ref": "mock_approval"}},
    )
    monkeypatch.setattr(baseline, "development", lambda *args: ({}, binding))
    monkeypatch.setattr(model_registry, "authorize", lambda *args: {"MOCK_ONLY": True})
    monkeypatch.setattr(model_registry, "inspect", lambda *args: {"model": descriptor})
    monkeypatch.setattr(model_adapters, "Adapter", lambda *args, **kwargs: None)
    accessed = []

    def fail_read(*args):
        accessed.append(True)
        raise IngestionBlocked("MOCK holdout unavailable")

    monkeypatch.setattr(corpus, "evaluation_data", fail_read)
    with pytest.raises(IngestionBlocked):
        evaluation.final_evaluate(
            tmp_path, None, "mock_only", "mock_experiment", "mock_approval", "first_ref"
        )
    assert accessed == [True]
    with pytest.raises(IngestionError, match="Immutable"):
        evaluation.final_evaluate(
            tmp_path, None, "mock_only", "mock_experiment", "mock_approval", "new_ref"
        )
    assert accessed == [True]
    assert len(list((model_registry.base(tmp_path) / "final_failures").iterdir())) == 1


def test_cli_registry_and_missing_dataset(monkeypatch, capsys):
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(ROOT))
    assert main(["ml", "registry", "list"]) == 0
    assert json.loads(capsys.readouterr().out)["models"] == []
    for command in (
        ["ml", "compare", "--dataset", "missing"],
        ["ml", "evaluate", "--dataset", "missing", "--split", "test", "--all"],
        ["ml", "registry", "promote", "--run-id", "missing"],
    ):
        assert main(command) == 4
        assert "SYNTHETIC:" not in capsys.readouterr().out


def test_validation_selection_frozen_before_test():
    def item(task, family, score):
        return {"descriptor": {"task": task, "family": family, "validation": {"macro_f1": score}}}

    models = {
        "svc": item("topic", "svm", 0.5),
        "lr": item("topic", "lr", 0.5),
        "transformer": item("sentiment", "phobert", 0.4),
    }
    assert evaluation.selection(models, policy.Protocol()) == {
        "topic": "lr",
        "sentiment": "transformer",
    }


def test_research_selection_and_promotion_bind_evaluation_mocked(registered, monkeypatch):
    """Synthetic record with mocked research gates, never actual approval evidence."""
    root, registry, _, record = registered
    monkeypatch.setattr(model_registry, "inspect", lambda *args: record)
    calls = []

    def authorization(*args):
        calls.append((args[2], args[3]))
        return {"reference": "mock_ref", "MOCK_ONLY": True}

    monkeypatch.setattr(model_registry, "authorize", authorization)
    report = {
        "dataset_type": "RESEARCH",
        "status": "COMPLETED",
        "selected_by_task": {},
        "models": {
            record["run_id"]: {
                "descriptor_sha256": store.digest(record["model"]),
                "metrics": {"MOCK_ONLY": True},
            }
        },
    }
    store.publish(model_registry.base(root) / "final_results/mock_loser", {"report.json": report})
    with pytest.raises(IngestionBlocked):
        model_registry.research_approve(root, registry, record["run_id"], "mock_loser", "mock_ref")
    assert calls == []
    report["selected_by_task"] = {"sentiment": record["run_id"]}
    checksum = store.publish(
        model_registry.base(root) / "final_results/mock_selected", {"report.json": report}
    )
    model_registry.research_approve(root, registry, record["run_id"], "mock_selected", "mock_ref")
    model_registry.activate(root, registry, record["run_id"], approval_ref="mock_ref")
    assert model_registry.active(root, registry, "sentiment")["run_id"] == record["run_id"]
    target = store.digest({"record": store.digest(record), "evaluation": checksum})
    assert ("RESEARCH_APPROVAL", target) in calls and ("PRODUCTION_PROMOTION", target) in calls


def test_smoke_and_tiny_adapter(monkeypatch, capsys):
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(ROOT))
    original = corpus._read_partition

    def guarded(path):
        assert path.name != "test.parquet"
        return original(path)

    monkeypatch.setattr(corpus, "_read_partition", guarded)
    assert main(["ml", "evaluation-smoke"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "EVALUATION_SMOKE_PASS_SYNTHETIC"
    assert result["temporary_storage_cleaned"] and result["demo_rollback_verified"]
    assert result["test_access_blocked"] and not result["test_labels_read"]
    assert result["transformer_kind"] == "SYNTHETIC_TINY_MODEL"
    assert result["registered_models"] == 7
    assert "SYNTHETIC:" not in json.dumps(result)
