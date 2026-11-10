"""Invented offline corpus only. No source, reviewer or label is real research evidence."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pfa.annotation import pilot_store as store
from pfa.cli import main
from pfa.data import corpus, corpus_smoke, official
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.profiling import SYNTHETIC_KEY
from pfa.data.registry import load_registry
from pfa.data.splitting import SPLITS, CorpusRow, SplitConfig, group_rows, leakage, split_rows

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def built(tmp_path):
    registry = load_registry(ROOT / "configs/dataset_sources.yaml")
    with store.synthetic_session(tmp_path):
        records, provenance = corpus_smoke.fixture()
        result = corpus._publish(tmp_path, "synthetic_v1", records, provenance, SplitConfig(), 42)
        yield tmp_path, registry, records, provenance, result


def test_synthetic_build_verify_and_task_masks(built):
    root, registry, rows, _, result = built
    actual = corpus.verify(root, registry, "synthetic_v1")
    assert actual["leakage"]["critical_count"] == 0
    assert sum(actual["counts"].values()) == 120
    assert not result["human_gold"]
    assert sum(not row.eligible["severity"] for row in rows) == 7
    assert all(row.labels["severity"] is None for row in rows if not row.eligible["severity"])
    assert all(row.eligible["topic"] and row.eligible["sentiment"] for row in rows)
    path = corpus.directory(root, "synthetic_v1")
    card = (path / "DATASET_CARD.md").read_text()
    assert "SYNTHETIC SOFTWARE" in card and "NO HUMAN GOLD" in card
    assert "SYNTHETIC:" not in card and "feedback_id" not in card
    assert "ann_" not in card and "windows_sid" not in card


def test_split_deterministic_and_seed_changes():
    rows, _ = corpus_smoke.fixture()
    first = split_rows(rows, SplitConfig(), 42)
    assert first == split_rows(list(reversed(rows)), SplitConfig(), 42)
    assert first[0] != split_rows(rows, SplitConfig(), 43)[0]
    memberships = [{row.group_id for row in first[0][split]} for split in SPLITS]
    assert all(not memberships[a] & memberships[b] for a, b in ((0, 1), (0, 2), (1, 2)))


def test_transitive_groups_case_thread_and_exact_content():
    rows, _ = corpus_smoke.fixture(8)
    rows[0].relations = ["case:" + "a" * 64]
    rows[2].relations = ["case:" + "a" * 64, "thread:" + "b" * 64]
    rows[4].relations = ["thread:" + "b" * 64]
    merged = group_rows(rows, lambda value: official.fingerprint(SYNTHETIC_KEY, "test", value))
    assert len({merged[i].group_id for i in (0, 1, 2, 3, 4, 5)}) == 1


@pytest.mark.parametrize(
    "kind", ["record", "group", "case", "thread", "text", "taxonomy", "source"]
)
def test_critical_leakage(kind):
    rows, _ = corpus_smoke.fixture()
    splits, _ = split_rows(rows, SplitConfig(), 42)
    a, b = splits["train"][0], splits["test"][0]
    if kind == "record":
        b.feedback_id = a.feedback_id
    elif kind == "group":
        b.group_id = a.group_id
    elif kind in {"case", "thread"}:
        a.relations = b.relations = [kind + ":" + "f" * 64]
    elif kind == "text":
        b.content = "  " + a.content.upper() + "  "
    elif kind == "taxonomy":
        b.taxonomy_checksum = "0" * 64
    else:
        b.source_version = "different"
    report = leakage(splits, SplitConfig())
    assert report["critical_count"] > 0 and report["status"] == "FAIL"
    assert a.content not in json.dumps(report)


def test_near_duplicate_candidates_warn_without_merging():
    rows, _ = corpus_smoke.fixture()
    splits, _ = split_rows(rows, SplitConfig(), 42)
    a, b = splits["train"][0], splits["test"][0]
    a.content = "SYNTHETIC thủ tục chưa được hướng dẫn rõ ràng khi nộp hồ sơ"
    b.content = a.content + " trực tuyến"
    before = [row.feedback_id for row in splits["test"]]
    report = leakage(splits, SplitConfig(near_threshold=0.8))
    assert report["warnings"]["POTENTIAL_NEAR_DUPLICATE"] > 0
    assert before == [row.feedback_id for row in splits["test"]]
    with pytest.raises(IngestionError, match="capacity"):
        leakage(splits, SplitConfig(max_candidate_pairs=1))


@pytest.mark.parametrize("n", [0, 1, 2, 4])
def test_empty_small_or_impossible(n):
    rows, _ = corpus_smoke.fixture(n)
    with pytest.raises(IngestionError):
        split_rows(rows, SplitConfig(), 42)


@pytest.mark.parametrize(
    "options",
    [
        {"ratios": [0.7, 0.2, 0.2]},
        {"ratios": [1.0, 0.0, 0.0]},
        {"ratios": [0.5, 0.5]},
        {"primary_task": "agency"},
        {"near_threshold": 0.1},
    ],
)
def test_invalid_split_configuration(options):
    with pytest.raises(ValueError):
        SplitConfig(**options)


def test_class_imbalance_rare_classes_and_strict_policy():
    rows, _ = corpus_smoke.fixture()
    for row in rows:
        row.labels["topic"] = "other"
    _, report = split_rows(rows, SplitConfig(), 42)
    assert "CLASS_COVERAGE_TRAIN_TOPIC" in report["warnings"]
    with pytest.raises(IngestionError, match="class coverage"):
        split_rows(rows, SplitConfig(class_policy="fail"), 42)


def test_temporal_group_boundaries_missing_and_ambiguous_dates():
    rows, _ = corpus_smoke.fixture()
    splits, report = split_rows(rows, SplitConfig(strategy="temporal"), 42)
    assert report["strategy"] == "temporal"
    assert max(row.event_time for row in splits["train"]) < min(
        row.event_time for row in splits["validation"]
    )
    rows[0].event_time = None
    with pytest.raises(IngestionError, match="event dates"):
        split_rows(rows, SplitConfig(strategy="temporal"), 42)
    splits, report = split_rows(
        rows, SplitConfig(strategy="temporal", missing_time="train_only"), 42
    )
    assert (
        rows[0] in splits["train"] and "UNKNOWN_EVENT_TIME_GROUPS_TRAIN_ONLY" in report["warnings"]
    )
    rows[0].event_time = datetime(2025, 1, 1)
    with pytest.raises(IngestionError):
        split_rows(rows, SplitConfig(strategy="temporal"), 42)


def test_temporal_spanning_groups_report_overlap():
    rows, _ = corpus_smoke.fixture()
    splits, _ = split_rows(rows, SplitConfig(strategy="temporal"), 42)
    splits["test"][0].event_time = datetime(2024, 1, 1, tzinfo=UTC)
    report = leakage(splits, SplitConfig(strategy="temporal"))
    assert report["warnings"]["TEMPORAL_INTERVAL_OVERLAP"] > 0


def test_pilot_holdout_requires_explicit_review():
    rows, _ = corpus_smoke.fixture()
    for row in rows[:8]:
        row.holdout_eligible = False
    splits, _ = split_rows(rows, SplitConfig(), 42)
    assert all(row in splits["train"] for row in rows[:8])
    splits["test"][0].holdout_eligible = False
    assert leakage(splits, SplitConfig())["failures"]["UNAPPROVED_HOLDOUT_MEMBERSHIP"] == 1


def test_missing_labels_and_inconsistent_masks():
    row = corpus_smoke.fixture()[0][1].model_dump(mode="json")
    row["labels"]["topic"] = None
    with pytest.raises(ValueError):
        CorpusRow.model_validate(row)


def test_duplicate_record_ids_rejected():
    rows, _ = corpus_smoke.fixture()
    rows[1].feedback_id = rows[0].feedback_id
    with pytest.raises(IngestionError, match="Duplicate"):
        group_rows(rows, lambda value: value)


@pytest.mark.parametrize(
    "name", ["manifest.json", "test.parquet", "train.parquet", "checksums.json"]
)
def test_corrupted_frozen_files_fail(built, name):
    root, registry, _, _, _ = built
    (corpus.directory(root, "synthetic_v1") / name).write_bytes(b"corrupt")
    with pytest.raises((IngestionError, ValueError)):
        corpus.verify(root, registry, "synthetic_v1")


def test_missing_dataset_and_missing_partition(built):
    root, registry, _, _, _ = built
    with pytest.raises(IngestionError, match="NOT_AVAILABLE"):
        corpus.verify(root, registry, "missing")
    (corpus.directory(root, "synthetic_v1") / "test.parquet").unlink()
    with pytest.raises(IngestionError):
        corpus.verify(root, registry, "synthetic_v1")


def test_immutable_versions_and_atomic_cleanup(built, monkeypatch):
    root, registry, records, provenance, _ = built
    with pytest.raises(IngestionError, match="Immutable"):
        corpus._publish(root, "synthetic_v1", records, provenance, SplitConfig(), 42)
    import pyarrow.parquet as pq

    def failed_write(*args, **kwargs):
        raise OSError("SYNTHETIC simulated storage failure")

    monkeypatch.setattr(pq, "write_table", failed_write)
    with pytest.raises(OSError):
        corpus._publish(root, "synthetic_v2", records, provenance, SplitConfig(), 42)
    assert not corpus.directory(root, "synthetic_v2").exists()
    assert sorted(path.name for path in (root / "data/processed").iterdir()) == ["synthetic_v1"]
    assert corpus.verify(root, registry, "synthetic_v1")["leakage"]["critical_count"] == 0


def test_development_reader_never_reads_test_labels(built, monkeypatch):
    root, registry, _, _, _ = built
    original = corpus._read_partition
    opened = []

    def tracked(path):
        opened.append(path.name)
        return original(path)

    monkeypatch.setattr(corpus, "_read_partition", tracked)
    assert corpus.model_selection(root, registry, "synthetic_v1", "train")
    assert corpus.model_selection(root, registry, "synthetic_v1", "validation")
    for split in ("test", "../test", "all"):
        with pytest.raises(IngestionBlocked):
            corpus.model_selection(root, registry, "synthetic_v1", split)
    assert opened == ["train.parquet", "validation.parquet"]
    with pytest.raises(IngestionBlocked):
        corpus.evaluation_data(root, registry, "synthetic_v1", "fake")


def test_synthetic_cannot_escape_session_or_claim_human_gold(built):
    root, registry, records, provenance, _ = built
    with pytest.raises(IngestionBlocked):
        corpus._publish(root, "bad", records, provenance | {"human_gold": True}, SplitConfig(), 42)
    with pytest.raises(IngestionBlocked):
        corpus._publish(
            root, "bad", records, provenance | {"dataset_type": "RESEARCH"}, SplitConfig(), 42
        )
    store._SYNTHETIC_ROOTS.remove(root.resolve())
    try:
        with pytest.raises(IngestionBlocked):
            corpus.verify(root, registry, "synthetic_v1")
    finally:
        store._SYNTHETIC_ROOTS.add(root.resolve())


def test_schema_taxonomy_mismatch_fails():
    records, provenance = corpus_smoke.fixture()
    records[0].taxonomy_checksum = "0" * 64
    with pytest.raises(IngestionError, match="taxonomy"):
        corpus._prepare(records, provenance, SplitConfig(), 42)


def test_smoke_cli_is_synthetic_and_safe(monkeypatch, capsys, caplog):
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(ROOT))
    assert main(["dataset", "split-smoke"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "SPLIT_SMOKE_PASS_SYNTHETIC"
    assert result["temporary_storage_cleaned"] and result["test_access_blocked"]
    assert "SYNTHETIC:" not in json.dumps(result) + caplog.text
    assert main(["dataset", "check-leakage", "--version", "missing_version"]) == 4


def test_rehashed_manifest_semantic_tampering_rejected(built):
    root, registry, _, _, _ = built
    path = corpus.directory(root, "synthetic_v1")
    manifest = json.loads((path / "manifest.json").read_text())
    manifest["membership"]["test"][0] = "f_" + "f" * 32
    (path / "manifest.json").write_text(json.dumps(manifest))
    checksums = json.loads((path / "checksums.json").read_text())
    checksums["manifest.json"] = official.file_digest(path / "manifest.json")
    (path / "checksums.json").write_text(json.dumps(checksums))
    with pytest.raises(IngestionError):
        corpus.verify(root, registry, "synthetic_v1")


def test_zero_eligible_severity_and_zero_timestamp_statistics():
    rows, provenance = corpus_smoke.fixture()
    for row in rows:
        row.labels["severity"] = None
        row.eligible["severity"] = False
        row.exclusion_reasons["severity"] = "UNKNOWN_SEVERITY_SYNTHETIC"
        row.event_time = None
    _, report, _ = corpus._prepare(rows, provenance, SplitConfig(primary_task="severity"), 42)
    assert report["leakage"]["timestamp_known"] == 0
    assert report["event_time_range"] == {"minimum": None, "maximum": None}
    assert all(
        sum(tasks["severity"].values()) == 0 for tasks in report["class_distributions"].values()
    )


def test_2000_record_synthetic_corpus(tmp_path):
    registry = load_registry(ROOT / "configs/dataset_sources.yaml")
    records, provenance = corpus_smoke.fixture(2000)
    with store.synthetic_session(tmp_path):
        result = corpus._publish(tmp_path, "synthetic_2000", records, provenance, SplitConfig(), 42)
        assert sum(result["report"]["counts"].values()) == 2000
        assert corpus.verify(tmp_path, registry, "synthetic_2000")["leakage"]["critical_count"] == 0
