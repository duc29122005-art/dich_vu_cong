"""Governance failures and simulated trusted interfaces, using invented temporary data only."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import test_official
import test_pilot_governance

from pfa.annotation import approval
from pfa.annotation import pilot_store as store
from pfa.annotation.schema import Annotation
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.cli import main
from pfa.data import corpus
from pfa.data.official_io import IngestionBlocked, IngestionError, rows, write_json
from pfa.data.official_schema import Feedback, ImportOptions
from pfa.data.permissions import current_decision
from pfa.data.registry import Registry
from pfa.data.splitting import SplitConfig

workspace = test_official.workspace
authorized = test_official.authorized


def plan(root, registry, **changes):
    test_pilot_governance.copy_instrument(root)
    test_pilot_governance.decision(root)
    approval.record_taxonomy(root, "test_taxonomy_approval")
    value = dict(
        version="service_feedback_v1",
        source_id=test_official.SOURCE,
        dataset_version="of_" + "1" * 32,
        research_pilot="research_test",
        gold_pilots=["gold_test"],
        config_checksum=store.digest(SplitConfig().model_dump()),
        seed=42,
        relations={},
        pilot_holdout_approved_ids=[],
        unknown_severity_approved_ids=[],
        reviewer_id="synthetic_test_reviewer",
        evidence_reference="synthetic_test_evidence",
        reviewed_at=datetime.now(UTC).isoformat(),
        human_verified=True,
    )
    value.update(changes)
    write_json(approval.requests(root, "build_service_feedback_v1"), value)
    return value


def training_rights(root, registry):
    values = registry.model_dump()
    source = next(
        source for source in values["sources"] if source["source_id"] == test_official.SOURCE
    )
    source.update(
        allowed_training=True, allowed_processing=["internal_analysis", "publication", "training"]
    )
    registry = Registry.model_validate(values)
    test_official.decision(
        root,
        registry,
        reference="test_training",
        allowed_scope=["internal_analysis", "publication", "training"],
    )
    return registry


def test_taxonomy_before_any_data_access(workspace, monkeypatch, capsys):
    root, registry = workspace
    test_pilot_governance.copy_instrument(root)
    monkeypatch.setattr(
        corpus.pilot, "verify_pilot", lambda *args: pytest.fail("Unauthorized access")
    )
    with pytest.raises(IngestionBlocked, match="TAXONOMY"):
        corpus.build(root, registry, "service_feedback_v1")
    assert main(["dataset", "build", "--version", "service_feedback_v1"]) == 3
    assert "BLOCKED_TAXONOMY" in capsys.readouterr().out


def test_missing_permission_before_pilot_or_source_reads(workspace, monkeypatch):
    root, registry = workspace
    plan(root, registry)
    monkeypatch.setattr(
        corpus.pilot, "verify_pilot", lambda *args: pytest.fail("Unauthorized access")
    )
    with pytest.raises(IngestionBlocked, match="PERMISSION"):
        corpus.build(root, registry, "service_feedback_v1")


def test_revoked_permission_blocks_build(authorized, monkeypatch):
    root, registry, _ = authorized
    plan(root, registry)
    test_official.decision(
        root, registry, reference="test_revocation", decision="REVOKED", allowed_scope=[]
    )
    monkeypatch.setattr(
        corpus.pilot, "verify_pilot", lambda *args: pytest.fail("Revoked data access")
    )
    with pytest.raises(IngestionBlocked):
        corpus.build(root, registry, "service_feedback_v1")


def test_missing_training_scope_blocks_before_pilot(authorized, monkeypatch):
    root, registry, _ = authorized
    plan(root, registry)
    monkeypatch.setattr(
        corpus.pilot, "verify_pilot", lambda *args: pytest.fail("No training authorization")
    )
    with pytest.raises(PermissionError):
        corpus.build(root, registry, "service_feedback_v1")


def test_missing_or_incomplete_real_pilot(authorized, monkeypatch):
    root, registry, _ = authorized
    plan(root, registry)
    registry = training_rights(root, registry)
    with pytest.raises(IngestionBlocked, match="BLOCKED_PILOT"):
        corpus.build(root, registry, "service_feedback_v1")
    monkeypatch.setattr(
        corpus.pilot,
        "verify_pilot",
        lambda *args: {"research_pilot_complete": False, "dataset_type": "RESEARCH"},
    )
    with pytest.raises(IngestionBlocked, match="BLOCKED_PILOT"):
        corpus.build(root, registry, "service_feedback_v1")


def test_configuration_and_raw_group_identifiers_rejected(workspace):
    root, registry = workspace
    values = plan(root, registry)
    values["relations"] = {"f_" + "a" * 32: ["case:RAW_SENSITIVE_SENTINEL"]}
    with pytest.raises(ValueError):
        corpus.BuildPlan.model_validate(values)
    with pytest.raises(IngestionBlocked, match="configuration"):
        corpus.build(root, registry, "service_feedback_v1", seed=43)


@pytest.fixture
def trusted_batches(authorized, monkeypatch):
    """Simulate prior verified batch interfaces. No genuine review or research is represented."""
    root, registry, source_file = authorized
    registry = training_rights(root, registry)
    report = corpus.official.ingest(
        root, registry, test_official.SOURCE, source_file, "test_training", test_official.KEY
    )
    test_official.review(root, report, permission_reference="test_training")
    built = corpus.official.ingest(
        root,
        registry,
        test_official.SOURCE,
        source_file,
        "test_training",
        test_official.KEY,
        mode="commit",
        review_ref="test_review",
    )
    file = root / "data/processed" / built["dataset_version"] / "feedback.jsonl"
    with file.open("rb") as stream:
        records = {
            item.feedback_id: item
            for _, value in rows(stream, ".jsonl", ImportOptions())
            for item in [Feedback.model_validate(value)]
        }
    identifiers = sorted(records)
    values = plan(
        root,
        registry,
        dataset_version=built["dataset_version"],
        relations={identifier: [] for identifier in identifiers},
    )
    annotations = []
    for identifier in identifiers:
        annotations.append(
            Annotation(
                feedback_id=identifier,
                dataset_version=built["dataset_version"],
                taxonomy_version=VERSION,
                taxonomy_checksum=CHECKSUM,
                annotator_id="ann_" + "a" * 16,
                source_id=test_official.SOURCE,
                dataset_type="RESEARCH",
                topic_label="other",
                sentiment_label="neutral",
                severity_label="low",
                multiple_issues=False,
                annotation_status="SUBMITTED",
                topic_justification="SYNTHETIC test reason",
                sentiment_justification="SYNTHETIC test reason",
                severity_justification="SYNTHETIC test reason",
                annotated_at=datetime.now(UTC),
            ).model_dump(mode="json")
        )
    manifest = SimpleNamespace(
        source_id=test_official.SOURCE,
        dataset_version=built["dataset_version"],
        dataset_type="RESEARCH",
        selected_ids=identifiers,
        duplicate_groups={identifier: "g_" + str(i) for i, identifier in enumerate(identifiers)},
    )
    monkeypatch.setattr(
        corpus.pilot,
        "verify_pilot",
        lambda *args: {"research_pilot_complete": True, "dataset_type": "RESEARCH"},
    )
    monkeypatch.setattr(
        corpus.pilot, "load_pilot", lambda *args: (manifest, "definition_test_checksum")
    )
    monkeypatch.setattr(corpus.pilot, "_records", lambda *args: records)
    original = store.bundle

    def bundle(path):
        if path.name == "adjudicated":
            return {
                "decision.json": {"final_records": annotations},
                "manifest.json": {"agreement_version": "synthetic_test_agreement"},
            }, "test_adjudication_checksum"
        return original(path)

    monkeypatch.setattr(store, "bundle", bundle)
    return root, registry, values, annotations


def test_unknown_severity_task_exception_and_exclusions(trusted_batches):
    root, registry, values, annotations = trusted_batches
    annotations[0].update(
        severity_label="unknown",
        annotation_status="REQUIRES_REVIEW",
        review_reason="SYNTHETIC insufficient evidence",
    )
    with pytest.raises(IngestionBlocked, match="Unresolved"):
        corpus.gather(root, registry, "service_feedback_v1", SplitConfig(), 42, test_official.KEY)
    values["unknown_severity_approved_ids"] = [annotations[0]["feedback_id"]]
    path = approval.requests(root, "build_service_feedback_v1")
    path.write_text(json.dumps(values))
    records, provenance = corpus.gather(
        root, registry, "service_feedback_v1", SplitConfig(), 42, test_official.KEY
    )
    row = next(row for row in records if row.feedback_id == annotations[0]["feedback_id"])
    assert row.eligible == {"topic": True, "sentiment": True, "severity": False}
    assert row.labels["severity"] is None and not row.holdout_eligible
    annotations[0].update(
        annotation_status="OUT_OF_SCOPE",
        topic_label=None,
        sentiment_label=None,
        severity_label=None,
        topic_justification=None,
        sentiment_justification=None,
        severity_justification=None,
    )
    records, provenance = corpus.gather(
        root, registry, "service_feedback_v1", SplitConfig(), 42, test_official.KEY
    )
    assert provenance["excluded_records"] == {"OUT_OF_SCOPE": 1}
    assert annotations[0]["feedback_id"] not in {row.feedback_id for row in records}


def test_gold_provenance_missing_source_and_missing_final_approval(trusted_batches):
    root, registry, values, annotations = trusted_batches
    annotations[0]["taxonomy_checksum"] = "0" * 64
    with pytest.raises(ValueError):
        corpus.gather(root, registry, "service_feedback_v1", SplitConfig(), 42, test_official.KEY)
    annotations[0]["taxonomy_checksum"] = CHECKSUM
    annotations[0]["dataset_type"] = "SYNTHETIC"
    # A batch verifier is a trusted interface, but builder must still validate every final row.
    with pytest.raises((ValueError, IngestionBlocked)):
        corpus.gather(root, registry, "service_feedback_v1", SplitConfig(), 42, test_official.KEY)
    annotations[0]["dataset_type"] = "RESEARCH"
    (root / "data/processed" / values["dataset_version"] / "feedback.jsonl").unlink()
    with pytest.raises((IngestionError, OSError)):
        corpus.gather(root, registry, "service_feedback_v1", SplitConfig(), 42, test_official.KEY)


def test_preview_and_missing_final_dataset_approval(tmp_path, monkeypatch):
    from pfa.data.corpus_smoke import fixture

    records, provenance = fixture()
    # Simulate the trusted upstream interface; no actual approvals or research corpus.
    monkeypatch.setattr(corpus, "gather", lambda *args: (records, provenance))
    preview = corpus.build(tmp_path, None, "service_feedback_v1", preview=True)
    assert preview["published"] is False and "card_checksum" in preview
    with pytest.raises(IngestionBlocked, match="human dataset"):
        corpus.build(tmp_path, None, "service_feedback_v1")
    assert not corpus.directory(tmp_path, "service_feedback_v1").exists()


def test_final_approval_and_evidence_change_prevent_publication(tmp_path):
    from pfa.data.corpus_smoke import fixture

    records, provenance = fixture()
    with pytest.raises(IngestionBlocked, match="human"):
        corpus._publish(
            tmp_path,
            "service_feedback_v1",
            records,
            provenance | {"dataset_type": "RESEARCH"},
            SplitConfig(),
            42,
        )
    # Even internally supplied approval cannot turn synthetic rows into research rows.
    with pytest.raises(IngestionError, match="mismatch"):
        corpus._publish(
            tmp_path,
            "service_feedback_v1",
            records,
            provenance | {"dataset_type": "RESEARCH"},
            SplitConfig(),
            42,
            {"human_verified": True},
            lambda: None,
        )


def test_current_source_decision_fixture_is_not_project_approval(authorized):
    root, registry, _ = authorized
    assert (
        current_decision(root, registry, test_official.SOURCE).evidence_reference
        == "synthetic_test_document"
    )
    assert root != test_official.ROOT
