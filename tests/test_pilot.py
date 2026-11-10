"""Predetermined synthetic software labels only; never real human agreement or gold data."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pfa.annotation import agreement, pilot, pilot_smoke
from pfa.annotation import pilot_store as store
from pfa.cli import main
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.official_schema import Feedback
from pfa.data.profiling import SYNTHETIC_KEY
from pfa.data.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def synthetic(tmp_path):
    registry = load_registry(ROOT / "configs/dataset_sources.yaml")
    with store.synthetic_session(tmp_path):
        manifest = pilot_smoke.create_synthetic(tmp_path, ROOT)
        yield tmp_path, registry, manifest


def submit(synthetic, actor, **options):
    root, registry, manifest = synthetic
    path, reference, records = pilot_smoke.synthetic_submission(
        root, registry, manifest, actor, **options
    )
    pilot.import_submission(
        root, registry, manifest.pilot_id, actor, path, reference, options.get("revision", 1)
    )
    return path, reference, records


def both(synthetic):
    root, registry, manifest = synthetic
    records = []
    for actor in ("A", "B"):
        pilot.export_assignment(root, registry, manifest.pilot_id, actor)
        records.append(submit(synthetic, actor)[2])
    return records


def test_sampling_determinism_and_coverage():
    records = [
        Feedback(
            feedback_id="f_" + f"{i:032x}",
            content=f"SYNTHETIC: phản ánh mục {i}",
            created_at="2026-01-01T10:00:00+07:00",
            source_id="synthetic_demo",
            domain="SYNTHETIC_A" if i % 2 else "SYNTHETIC_B",
        )
        for i in range(250)
    ]
    first = pilot.sample_records(records, 200, 42, SYNTHETIC_KEY)
    assert first == pilot.sample_records(list(reversed(records)), 200, 42, SYNTHETIC_KEY)
    assert first[0] != pilot.sample_records(records, 200, 43, SYNTHETIC_KEY)[0]
    assert len(first[0]) == len(set(first[0])) == 200
    assert sorted(item["selected"] for item in first[1]["strata"].values()) == [100, 100]
    assert "SYNTHETIC_A" not in json.dumps(first[1])


def test_exact_duplicates_and_near_group_trace():
    records = [
        Feedback(
            feedback_id="f_" + f"{i:032x}",
            content=f"SYNTHETIC mục {i}",
            created_at=None,
            source_id="synthetic_demo",
        )
        for i in range(4)
    ]
    records[3].content = records[0].content
    groups = {item.feedback_id: "same_candidate_group" for item in records}
    selected, stats, lineage = pilot.sample_records(records, 3, 42, SYNTHETIC_KEY, groups)
    assert len(selected) == 3 and stats["exact_duplicate_count"] == 1
    assert set(lineage.values()) == {"same_candidate_group"}
    with pytest.raises(IngestionError, match="Insufficient"):
        pilot.sample_records(records, 4, 42, SYNTHETIC_KEY)


def test_assignment_no_labels_and_separate_deliveries(synthetic):
    root, registry, manifest = synthetic
    for actor in ("A", "B"):
        pilot.export_assignment(root, registry, manifest.pilot_id, actor)
    a = pilot.delivery(root, manifest.pilot_id, "A")
    b = pilot.delivery(root, manifest.pilot_id, "B")
    assert a != b
    assert json.loads((a / "context.json").read_text()) == json.loads(
        (b / "context.json").read_text()
    )
    for actor, directory in (("A", a), ("B", b)):
        rows = list(pilot.annotation_rows(directory / "annotation.csv"))
        assert [row["feedback_id"] for _, row in rows] == manifest.selected_ids
        assert all(
            row["topic_label"] is None
            and row["severity_label"] is None
            and row["sentiment_label"] is None
            for _, row in rows
        )
        assert all(
            row["annotator_id"] == manifest.plan.annotators[actor].annotator_id for _, row in rows
        )
    submit(synthetic, "A")
    assert all(row["topic_label"] is None for _, row in pilot.annotation_rows(b / "annotation.csv"))
    with pytest.raises(IngestionError, match="already exported"):
        pilot.export_assignment(root, registry, manifest.pilot_id, "A")


@pytest.mark.parametrize(
    "changes",
    [
        {"topic_label": None, "topic_justification": None},
        {"severity_label": "requires_review"},
        {"annotator_id": "ann_" + "b" * 16},
        {"annotation_status": "DRAFT"},
        {"feedback_id": "f_" + "0" * 32},
        {"annotated_at": "2026-01-01T00:00:00"},
        {"topic_justification": "PRIVATE_SENTINEL person@example.invalid"},
        {"taxonomy_checksum": "0" * 64},
        {"dataset_type": "RESEARCH"},
    ],
)
def test_invalid_import(synthetic, changes):
    root, registry, manifest = synthetic
    pilot.export_assignment(root, registry, manifest.pilot_id, "A")
    path, reference, _ = pilot_smoke.synthetic_submission(
        root, registry, manifest, "A", modifications={0: changes}
    )
    with pytest.raises((IngestionError, IngestionBlocked)):
        pilot.import_submission(root, registry, manifest.pilot_id, "A", path, reference)
    assert not pilot.submissions(root, manifest.pilot_id, "A")


def test_corrections_preserve_original_and_duplicate_rejected(synthetic):
    root, registry, manifest = synthetic
    pilot.export_assignment(root, registry, manifest.pilot_id, "A")
    path, reference, _ = submit(synthetic, "A")
    first = pilot.submissions(root, manifest.pilot_id, "A")[0]
    with pytest.raises(IngestionBlocked):
        pilot.import_submission(root, registry, manifest.pilot_id, "A", path, reference)
    submit(synthetic, "A", revision=2, modifications={0: {"topic_label": "fees"}})
    history = pilot.submissions(root, manifest.pilot_id, "A")
    assert len(history) == 2 and history[0] == first
    assert history[1][0]["receipt.json"]["previous_submission_checksum"] == first[1]


def test_modified_input_and_context_rejected(synthetic):
    root, registry, manifest = synthetic
    pilot.export_assignment(root, registry, manifest.pilot_id, "A")
    path, reference, _ = pilot_smoke.synthetic_submission(root, registry, manifest, "A")
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    with pytest.raises(IngestionBlocked, match="checksum"):
        pilot.import_submission(root, registry, manifest.pilot_id, "A", path, reference)
    path.write_bytes(original)
    context = pilot.delivery(root, manifest.pilot_id, "A") / "context.json"
    context.write_text("{}")
    with pytest.raises(IngestionBlocked, match="context was modified"):
        pilot.import_submission(root, registry, manifest.pilot_id, "A", path, reference)


def test_unknown_and_exclusions_are_explicit(synthetic):
    root, registry, manifest = synthetic
    for actor in ("A", "B"):
        pilot.export_assignment(root, registry, manifest.pilot_id, actor)
    unknown = {
        "annotation_status": "REQUIRES_REVIEW",
        "severity_label": "unknown",
        "review_reason": "SYNTHETIC: thiếu bằng chứng về tác động.",
    }
    excluded = {
        "annotation_status": "OUT_OF_SCOPE",
        "topic_label": None,
        "sentiment_label": None,
        "severity_label": None,
        "topic_justification": None,
        "sentiment_justification": None,
        "severity_justification": None,
        "review_reason": "SYNTHETIC: ngoài phạm vi dịch vụ công.",
    }
    submit(synthetic, "A", modifications={0: unknown, 1: excluded})
    submit(synthetic, "B")
    report, _ = pilot.agreement_report(root, registry, manifest.pilot_id)
    assert report["tasks"]["topic"]["comparable_pairs"] == 7
    assert report["tasks"]["severity"]["comparable_pairs"] == 6
    assert report["tasks"]["severity"]["not_comparable"]["unknown_or_missing_label"] == 1
    assert report["workflow_disagreement_count"] == 2


@pytest.mark.parametrize(
    "pairs,kappa,raw",
    [
        ([("a", "a"), ("b", "b")], 1, 100),
        ([("a", "b"), ("b", "a")], -1, 0),
        ([("a", "a"), ("a", "b"), ("b", "b"), ("b", "a")], 0, 50),
        ([("a", "a")] * 9 + [("b", "a")], 0, 90),
        ([("a", "a")], None, 100),
        ([], None, None),
    ],
)
def test_known_cohen_examples(pairs, kappa, raw):
    metric = agreement.cohen(pairs, ("a", "b"))
    assert metric["kappa"] == kappa and metric["raw_agreement_percent"] == raw
    assert sum(map(sum, metric["confusion_matrix"])) == len(pairs)


def test_missing_annotations_and_known_smoke_metrics(synthetic):
    root, registry, manifest = synthetic
    report, _ = pilot.agreement_report(root, registry, manifest.pilot_id)
    assert report["status"] == "NOT_AVAILABLE" and report["matched_pairs"] == 0
    assert report["tasks"]["topic"]["kappa"] is None
    records = both(synthetic)
    before = [store.digest(side) for side in records]
    report, _ = pilot.agreement_report(root, registry, manifest.pilot_id)
    assert report["tasks"]["topic"]["kappa"] == 0.5
    assert report["tasks"]["sentiment"]["kappa"] == 0.6
    assert report["tasks"]["severity"]["kappa"] == 0.6
    assert all(metric["raw_agreement_percent"] == 75 for metric in report["tasks"].values())
    assert len(report["disagreements"]) == 6
    assert [store.digest(side) for side in records] == before
    assert not report["human_agreement_measured"]
    assert all(row["status"] == "REQUIRES_HUMAN_ADJUDICATION" for row in report["disagreements"])


def test_no_text_or_pii_in_agreement_or_logs(synthetic, caplog):
    root, registry, manifest = synthetic
    both(synthetic)
    report, _ = pilot.agreement_report(root, registry, manifest.pilot_id)
    output = json.dumps(report) + caplog.text
    assert "Thủ tục" not in output and "topic_justification" not in output
    assert "SYNTHETIC:" not in output
    assert "windows_sid" not in output


def test_adjudication_preserves_originals_and_locks(synthetic):
    root, registry, manifest = synthetic
    sets = both(synthetic)
    original = [pilot.submissions(root, manifest.pilot_id, actor) for actor in ("A", "B")]
    pilot.export_review(root, registry, manifest.pilot_id)
    ref = pilot_smoke.synthetic_decision(root, registry, manifest, sets[0])
    summary = pilot.adjudicate(root, registry, manifest.pilot_id, ref)
    assert summary["human_gold"] is False and summary["gold_count"] == 0
    assert summary["synthetic_resolved_count"] == 8
    assert pilot.verify_pilot(root, registry, manifest.pilot_id)["status"] == "VERIFIED_SYNTHETIC"
    assert [pilot.submissions(root, manifest.pilot_id, actor) for actor in ("A", "B")] == original
    with pytest.raises(IngestionError, match="already exists"):
        pilot.adjudicate(root, registry, manifest.pilot_id, ref)


def test_unknown_final_never_becomes_gold(synthetic):
    root, registry, manifest = synthetic
    sets = both(synthetic)
    sets[0][0].update(
        annotation_status="REQUIRES_REVIEW",
        severity_label="unknown",
        review_reason="SYNTHETIC: chưa đủ thông tin.",
    )
    ref = pilot_smoke.synthetic_decision(root, registry, manifest, sets[0])
    summary = pilot.adjudicate(root, registry, manifest.pilot_id, ref)
    assert summary["unresolved_count"] == 1 and summary["synthetic_resolved_count"] == 7
    assert not pilot.verify_pilot(root, registry, manifest.pilot_id)["research_pilot_complete"]


@pytest.mark.parametrize("change", ["missing_record", "fake_human", "wrong_adjudicator"])
def test_gold_requires_explicit_review_of_all_records(synthetic, change):
    root, registry, manifest = synthetic
    sets = both(synthetic)
    ref = pilot_smoke.synthetic_decision(root, registry, manifest, sets[0])
    path = pilot.requests(root, ref)
    value = json.loads(path.read_text())
    if change == "missing_record":
        value["final_records"].pop()  # Even agreeing records require explicit approval.
    elif change == "fake_human":
        value["human_verified"] = True
    else:
        value["adjudicator_id"] = manifest.plan.annotators["A"].annotator_id
    path.write_text(json.dumps(value))
    with pytest.raises((IngestionBlocked, IngestionError)):
        pilot.adjudicate(root, registry, manifest.pilot_id, ref)


def test_synthetic_cannot_escape_temporary_capability(synthetic):
    root, registry, manifest = synthetic
    store._SYNTHETIC_ROOTS.remove(root.resolve())
    try:
        with pytest.raises(IngestionBlocked, match="Synthetic"):
            pilot.load_pilot(root, registry, manifest.pilot_id)
    finally:
        store._SYNTHETIC_ROOTS.add(root.resolve())


def test_manifest_checksum_corruption(synthetic):
    root, registry, manifest = synthetic
    file = pilot.location(root, manifest.pilot_id) / "definition/manifest.json"
    file.write_text("{}")
    with pytest.raises(IngestionError, match="checksum"):
        pilot.load_pilot(root, registry, manifest.pilot_id)


def test_actor_acl_rules_and_failure(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "is_synthetic", lambda root: False)
    monkeypatch.setattr(
        pilot.subprocess,
        "run",
        lambda args, **kwargs: calls.append(args) or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(pilot, "protect_directory", lambda path: None)
    pilot._grant_actor(tmp_path, tmp_path, "S-1-5-21-1001")
    assert calls[0] == ["icacls", str(tmp_path), "/grant:r", "*S-1-5-21-1001:(OI)(CI)M"]
    monkeypatch.setattr(
        pilot.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1)
    )
    with pytest.raises(IngestionBlocked):
        pilot._grant_actor(tmp_path, tmp_path, "S-1-5-21-1001")


def test_smoke_and_cli_no_real_artifacts(monkeypatch, capsys):
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(ROOT))
    monkeypatch.setenv("PFA_ENVIRONMENT", "test")
    monkeypatch.setenv("PFA_LOG_LEVEL", "INFO")
    before = (ROOT / "configs/permission_evidence.json").read_bytes()
    assert main(["annotation", "pilot-smoke"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PILOT_SMOKE_PASS_SYNTHETIC"
    assert output["temporary_storage_cleaned"] and not output["human_gold"]
    assert before == (ROOT / "configs/permission_evidence.json").read_bytes()
