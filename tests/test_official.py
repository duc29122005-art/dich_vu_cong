"""Invented data and simulated approvals only; all builds use isolated temporary roots."""

import csv
import io
import json
import os
import subprocess
import unicodedata
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pfa.cli import main
from pfa.data import official, official_io
from pfa.data.official_io import IngestionBlocked, IngestionError, safe_path
from pfa.data.official_schema import Feedback, ImportOptions
from pfa.data.permissions import record_decision
from pfa.data.preprocessing import normalize_text
from pfa.data.privacy import screen
from pfa.data.registry import Registry, load_registry

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/public_service_feedback_synthetic.csv"
SOURCE = "authorized_agency_export"
KEY = b"SYNTHETIC-TEST-KEY-NEVER-USE-REAL!!"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/dataset_sources.yaml").write_bytes(
        (ROOT / "configs/dataset_sources.yaml").read_bytes()
    )
    (tmp_path / "configs/permission_evidence.json").write_text('{"decisions": []}')
    (tmp_path / "configs/permission_history.jsonl").write_text("")
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("PFA_ENVIRONMENT", "test")
    monkeypatch.setenv("PFA_LOG_LEVEL", "INFO")
    monkeypatch.setenv("PFA_FINGERPRINT_KEY", KEY.hex())
    return tmp_path, load_registry(tmp_path / "configs/dataset_sources.yaml")


def decision(root, registry, reference="test_approval", **changes):
    item = {
        "approval_ref": reference,
        "source_id": SOURCE,
        "reviewer": "SYNTHETIC TEST REVIEWER",
        "evidence_reference": "synthetic_test_document",
        "decision_date": (date.today() - timedelta(days=5)).isoformat(),
        "decision": "APPROVED",
        "allowed_scope": ["internal_analysis", "publication"],
        "human_verified": True,
        "license_verified": True,
        "privacy_verified": True,
        "retention_policy": "SYNTHETIC: delete at test teardown",
        "expires_on": (date.today() + timedelta(days=30)).isoformat(),
    }
    item.update(changes)
    path = root / "configs/permission_evidence.json"
    contents = json.loads(path.read_text())
    contents["decisions"].append(item)
    path.write_text(json.dumps(contents))
    record_decision(root, registry, SOURCE, reference)


@pytest.fixture
def authorized(workspace):
    root, registry = workspace
    payload = registry.model_dump()
    source = next(item for item in payload["sources"] if item["source_id"] == SOURCE)
    source.update(
        permission_status="APPROVED",
        license_status="VERIFIED",
        allowed_processing=["internal_analysis", "publication"],
        allowed_publication=True,
    )
    registry = Registry.model_validate(payload)
    (root / "configs/dataset_sources.yaml").write_text(json.dumps(registry.model_dump()))
    decision(root, registry)
    private = root / "data/private"
    private.mkdir(parents=True)
    file = private / "SYNTHETIC.csv"
    file.write_text(
        FIXTURE.read_text(encoding="utf-8").replace("synthetic_fixture", SOURCE), encoding="utf-8"
    )
    return root, registry, file


def preview(authorized, **kwargs):
    root, registry, file = authorized
    return official.ingest(root, registry, SOURCE, file, "test_approval", KEY, **kwargs)


def review(root, report, **changes):
    stage = root / "data/staging" / report["dataset_version"]
    queue = json.loads((stage / "review_queue.json").read_text())
    metadata = {
        "dataset_version": report["dataset_version"],
        "source_id": SOURCE,
        "source_checksum": report["source_checksum"],
        "candidates_checksum": report["candidates_checksum"],
        "queue_checksum": report["queue_checksum"],
        "permission_reference": "test_approval",
        "reviewer": "test_privacy_reviewer",
        "evidence_reference": "synthetic_test_review",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "provenance": "REAL_EXTERNAL",
        "quality_accepted": True,
        "decisions": [
            {
                "feedback_id": item["feedback_id"],
                "action": "REJECT" if item["ambiguous"] else "APPROVE",
                "privacy_cleared": not item["ambiguous"],
            }
            for item in queue["records"]
        ],
    }
    metadata.update(changes)
    folder = root / "data/private/reviews"
    folder.mkdir(exist_ok=True)
    (folder / "test_review.json").write_text(json.dumps(metadata))
    return metadata


def commit(authorized):
    report = preview(authorized)
    review(authorized[0], report)
    return preview(authorized, mode="commit", review_ref="test_review")


def test_canonical_schema_unicode_nulls_and_no_invented_labels():
    data = Feedback(
        feedback_id="SYNTHETIC",
        content="Không hài lòng, chưa rõ thủ tục!",
        created_at=None,
        source_id="synthetic_fixture",
    )
    assert data.agency is None and data.response_date is None
    assert not {"sentiment", "topic", "severity"} & Feedback.model_fields.keys()
    with pytest.raises(ValidationError):
        Feedback(feedback_id="x", content="test", source_id="synthetic_fixture")
    with pytest.raises(ValidationError):
        Feedback(feedback_id="x", content=" ", created_at=None, source_id="synthetic_fixture")


@pytest.mark.parametrize("value", ["not-a-date", "2026-02-30T12:00:00", "2026-01-01", 1234, True])
def test_timestamps_are_not_invented(value):
    with pytest.raises(ValidationError):
        Feedback(
            feedback_id="x", content="GIẢ LẬP", created_at=value, source_id="synthetic_fixture"
        )


def test_conservative_normalization_and_control_obfuscation():
    content = "Không hài lòng; chưa rõ!"
    assert normalize_text(" \t" + unicodedata.normalize("NFD", content) + "\n\x00") == content
    assert "[REDACTED_PHONE]" in screen("GIẢ LẬP: 0\u200b123456789").text
    with pytest.raises(ValueError):
        normalize_text("\x00\u200b ")
    with pytest.raises(ValueError):
        normalize_text("GIẢ LẬP", max_length=2)
    with pytest.raises(UnicodeError):
        normalize_text("GIẢ LẬP \ud800")


def test_pii_categories_false_positives_false_negatives_and_unicode():
    result = screen("GIẢ LẬP 0123456789 thư@example.invalid CCCD 000000000000")
    assert {"phone", "email", "citizen_id"} <= result.counts.keys()
    assert "0123456789" not in result.text and "example.invalid" not in result.text
    assert not screen("Hồ sơ ngày 01-02-2026, có 25 biểu mẫu.").counts
    # A ten-digit administrative code is a possible false positive, never proof of PII.
    assert screen("Mã hồ sơ giả lập 0123456789").counts["phone"] == 1
    # Unmarked names and free-form addresses are deliberate known false negatives.
    assert not screen("NGƯỜI GIẢ LẬP ở KHU VỰC GIẢ LẬP").counts
    ambiguous = screen(unicodedata.normalize("NFD", "Họ tên: NGƯỜI GIẢ LẬP. Địa chỉ: NƠI GIẢ LẬP."))
    assert ambiguous.ambiguous
    assert "personal_name" in ambiguous.counts and "address" in ambiguous.counts
    assert screen("CMND: 000000000").counts["personal_identifier"] == 1
    assert screen("CMND: 000000000, chưa nhận kết quả.").text == (
        "CMND: [REDACTED_PERSONAL_IDENTIFIER], chưa nhận kết quả."
    )


def test_csv_counts_duplicates_near_pairs_and_private_preview(authorized):
    report = preview(authorized)
    assert (report["input_records"], report["valid_records"], report["invalid_records"]) == (
        10,
        8,
        2,
    )
    assert report["unique_record_count"] == 5 and report["duplicate_count"] == 3
    assert report["duplicate_reasons"] == {
        "source_record": 1,
        "feedback_id": 1,
        "sanitized_content": 1,
    }
    assert report["suspected_duplicate_count"] == 1
    assert report["privacy_flagged_count"] == 3
    assert report["human_review_pending_count"] == 5 and report["published_count"] == 0
    stage = authorized[0] / "data/staging" / report["dataset_version"]
    candidates = (stage / "candidates.jsonl").read_text()
    assert "0123456789" not in candidates and "citizen@example.invalid" not in candidates
    records = [json.loads(line) for line in candidates.splitlines()]
    assert all(record["feedback_id"].startswith("f_") for record in records)
    assert all(record["feedback_id"] not in {"S01", "S02"} for record in records)
    assert not (authorized[0] / "data/processed").exists()
    assert preview(authorized)["dataset_version"] == report["dataset_version"]
    if os.name != "nt":
        assert stage.stat().st_mode & 0o777 == 0o700
        assert (stage / "candidates.jsonl").stat().st_mode & 0o777 == 0o600


def test_utf8_bom_and_jsonl_recovery(authorized):
    root, registry, file = authorized
    file.write_bytes(b"\xef\xbb\xbf" + file.read_bytes())
    assert preview(authorized)["valid_records"] == 8
    row = {
        "feedback_id": "GIẢ_LẬP",
        "content": "Không rõ hướng dẫn!",
        "created_at": None,
        "source_id": SOURCE,
    }
    other = root / "data/private/SYNTHETIC.jsonl"
    other.write_text(
        json.dumps(row, ensure_ascii=False) + '\nnot json\n{"content": "x", "content": "y"}\n',
        encoding="utf-8",
    )
    result = official.ingest(root, registry, SOURCE, other, "test_approval", KEY)
    assert (result["valid_records"], result["invalid_records"]) == (1, 2)


@pytest.mark.parametrize(
    "payload,error",
    [
        (b"\xff\xfeBAD", "encoding"),
        (b"content\nSYNTHETIC\n", "columns"),
        (b'feedback_id,content,created_at,source_id\na,"unclosed', "Malformed CSV"),
    ],
)
def test_invalid_file_rolls_back_without_staged_records(authorized, payload, error):
    root, _, file = authorized
    file.write_bytes(payload)
    with pytest.raises(IngestionError, match=error):
        preview(authorized)
    assert not list((root / "data/staging").iterdir())


def test_mapped_columns_and_invalid_mapping(authorized):
    _, _, file = authorized
    content = file.read_text(encoding="utf-8").replace("feedback_id,content,", "Mã,Nội dung,")
    file.write_text(content, encoding="utf-8")
    options = ImportOptions(column_mapping={"feedback_id": "Mã", "content": "Nội dung"})
    assert preview(authorized, options=options)["valid_records"] == 8
    with pytest.raises(ValidationError):
        ImportOptions(column_mapping={"content": "feedback_id"})


def test_source_identity_mismatch_fails_closed(authorized):
    _, _, file = authorized
    file.write_text(
        file.read_text(encoding="utf-8").replace(SOURCE, "other_source"), encoding="utf-8"
    )
    with pytest.raises(IngestionError, match="identity"):
        preview(authorized)


def test_permission_before_any_real_input_or_options_read(workspace, monkeypatch):
    root, registry = workspace
    sensitive = root / "data/private/PRIVATE_SENTINEL.csv"
    original = Path.open
    reads = []

    def guarded(path, *args, **kwargs):
        if path == sensitive:
            reads.append(path)
            raise AssertionError("Unauthorized input read")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(IngestionBlocked):
        official.ingest(root, registry, SOURCE, sensitive, "missing", b"", options_path=sensitive)
    assert reads == []


@pytest.mark.parametrize(
    "change",
    [
        {"expires_on": None},
        {
            "decision_date": (date.today() - timedelta(days=2)).isoformat(),
            "expires_on": (date.today() - timedelta(days=1)).isoformat(),
        },
        {"decision": "REVOKED", "allowed_scope": []},
        {"decision": "DENIED", "allowed_scope": []},
        {"allowed_scope": ["software_tests"]},
    ],
)
def test_permission_missing_expired_revoked_or_wrong_scope(authorized, change):
    root, registry, _ = authorized
    decision(root, registry, reference="test_new_decision", **change)
    with pytest.raises(IngestionBlocked):
        official.ingest(root, registry, SOURCE, root / "missing", "test_new_decision", KEY)


def test_invalid_approval_and_inconsistent_audit(authorized):
    root, registry, file = authorized
    with pytest.raises(IngestionBlocked):
        official.ingest(root, registry, SOURCE, file, "wrong", KEY)
    path = root / "configs/permission_evidence.json"
    value = json.loads(path.read_text())
    value["decisions"][0]["retention_policy"] = "SYNTHETIC altered evidence"
    path.write_text(json.dumps(value))
    with pytest.raises(IngestionBlocked):
        preview(authorized)


def test_commit_requires_review_and_publication_scope(authorized):
    with pytest.raises(IngestionBlocked, match="REVIEW"):
        preview(authorized, mode="commit")
    root, registry, _ = authorized
    decision(root, registry, reference="test_analysis_only", allowed_scope=["internal_analysis"])
    with pytest.raises(IngestionBlocked, match="PERMISSION"):
        official.ingest(
            root, registry, SOURCE, root / "missing", "test_analysis_only", KEY, "commit"
        )


@pytest.mark.parametrize(
    "change",
    [
        {"candidates_checksum": "0" * 64},
        {"queue_checksum": "0" * 64},
        {"permission_reference": "other"},
        {"reviewer": "unknown"},
        {"decisions": []},
        {"quality_accepted": False},
        {"provenance": "SYNTHETIC"},
    ],
)
def test_review_must_match_exact_build(authorized, change):
    report = preview(authorized)
    review(authorized[0], report, **change)
    with pytest.raises(IngestionBlocked):
        preview(authorized, mode="commit", review_ref="test_review")
    assert not (authorized[0] / "data/processed" / report["dataset_version"]).exists()


def test_commit_manifest_quality_and_immutable_version(authorized):
    root, registry, _ = authorized
    result = commit(authorized)
    assert result["published_count"] == 4 and result["human_review_pending_count"] == 0
    assert result["human_review_rejected_count"] == 1
    assert official.verify(root, registry, result["dataset_version"])["published_count"] == 4
    output = root / "data/processed" / result["dataset_version"] / "feedback.jsonl"
    published = output.read_text()
    assert "NGƯỜI GIẢ LẬP" not in published
    for row in map(json.loads, published.splitlines()):
        assert "Họ tên" not in row["content"] and "0123456789" not in row["content"]
    checksum = official.file_digest(output)
    with pytest.raises(IngestionError, match="exists"):
        preview(authorized, mode="commit", review_ref="test_review")
    assert official.file_digest(output) == checksum


@pytest.mark.parametrize("mutation", ["data", "quality", "manifest", "review", "statistics"])
def test_verification_rejects_corruption(authorized, mutation):
    root, registry, _ = authorized
    result = commit(authorized)
    version = result["dataset_version"]
    metadata = root / "data/manifests" / version
    manifest_file = metadata / "manifest.json"
    if mutation == "data":
        with (root / "data/processed" / version / "feedback.jsonl").open("a") as output:
            output.write("bad")
    elif mutation == "quality":
        (metadata / "quality_report.json").write_text("{}")
    elif mutation == "manifest":
        manifest_file.write_text('{"source_id": "invalid"}')
    elif mutation == "review":
        (root / "data/private/reviews/test_review.json").write_text("{}")
    else:
        report_file = metadata / "quality_report.json"
        report = json.loads(report_file.read_text())
        report["valid_records"] += 1
        report_file.write_text(json.dumps(report))
        manifest = json.loads(manifest_file.read_text())
        manifest["quality_checksum"] = official.file_digest(report_file)
        manifest_file.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        official.verify(root, registry, version)


def test_verify_revoked_before_published_data_read(authorized, monkeypatch):
    root, registry, _ = authorized
    result = commit(authorized)
    decision(root, registry, reference="test_revoke", decision="REVOKED", allowed_scope=[])
    data_file = root / "data/processed" / result["dataset_version"] / "feedback.jsonl"
    original = Path.open

    def guarded(path, *args, **kwargs):
        if path == data_file:
            raise AssertionError("Revoked dataset contents must not be read")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(IngestionBlocked):
        official.verify(root, registry, result["dataset_version"])


def test_atomic_catalog_failure_removes_uncommitted_output(authorized, monkeypatch):
    root, _, _ = authorized
    report = preview(authorized)
    review(root, report)
    original = Path.rename

    def fail_catalog(path, target):
        if path.name.startswith(".manifest-"):
            raise OSError("SYNTHETIC publication failure")
        return original(path, target)

    monkeypatch.setattr(Path, "rename", fail_catalog)
    with pytest.raises(OSError):
        preview(authorized, mode="commit", review_ref="test_review")
    assert not list((root / "data/processed").iterdir())
    assert not list((root / "data/manifests").iterdir())


def test_initial_write_failure_cleans_temporary_files(authorized, monkeypatch):
    root, _, _ = authorized
    monkeypatch.setattr(
        official, "write_json", lambda *args: (_ for _ in ()).throw(OSError("synthetic"))
    )
    with pytest.raises(OSError):
        preview(authorized)
    assert not list((root / "data/staging").iterdir())


def test_path_reparse_and_size_safety(authorized, monkeypatch):
    root, registry, file = authorized
    with pytest.raises(IngestionError, match="boundary"):
        official.ingest(root, registry, SOURCE, ROOT / "README.md", "test_approval", KEY)
    with pytest.raises(IngestionError, match="size"):
        preview(authorized, options=ImportOptions(max_input_bytes=10))
    original = Path.lstat

    def reparse(path, *args, **kwargs):
        if path == file:
            return SimpleNamespace(st_mode=0, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(IngestionError, match="reparse"):
        safe_path(file)


def test_growing_stream_and_hmac_secret_separation():
    with pytest.raises(IngestionError, match="maximum size"):
        list(official_io.rows(io.BytesIO(b"x" * 100), ".jsonl", ImportOptions(max_input_bytes=10)))
    assert official.fingerprint(KEY, "raw", "GIẢ LẬP") != official.fingerprint(
        b"x" * 32, "raw", "GIẢ LẬP"
    )


def test_synthetic_smoke_cli_and_schema(workspace, capsys):
    assert main(["dataset", "official", "schema"]) == 0
    assert set(json.loads(capsys.readouterr().out)["required"]) == {
        "feedback_id",
        "content",
        "created_at",
        "source_id",
    }
    assert main(["dataset", "official", "smoke", "--fixture", str(FIXTURE)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "SMOKE_PASS_SYNTHETIC"
    assert result["verification"]["status"] == "VERIFIED_SYNTHETIC"
    assert result["quality_report"]["metrics_usage"] == "SOFTWARE_TEST_ONLY"
    assert not (workspace[0] / "data").exists()
    other = workspace[0] / "other.csv"
    other.write_bytes(FIXTURE.read_bytes())
    with pytest.raises(IngestionError, match="bundled"):
        official.smoke(other, workspace[1])


def test_real_cli_permission_failure_and_missing_version(workspace, capsys):
    assert (
        main(
            [
                "dataset",
                "official",
                "import",
                "--source",
                SOURCE,
                "--input",
                "PRIVATE_SENTINEL.csv",
                "--approval-ref",
                "missing",
                "--mode",
                "preview",
            ]
        )
        == 3
    )
    assert "PRIVATE_SENTINEL" not in capsys.readouterr().out
    assert main(["dataset", "official", "verify", "--dataset-version", "of_" + "0" * 32]) == 4


def test_cli_preview_no_sensitive_output_and_commit(authorized, capsys, caplog):
    root, _, file = authorized
    args = [
        "dataset",
        "official",
        "import",
        "--source",
        SOURCE,
        "--input",
        str(file),
        "--approval-ref",
        "test_approval",
    ]
    assert main(args + ["--mode", "preview"]) == 0
    output = capsys.readouterr()
    assert "0123456789" not in output.out + output.err + caplog.text
    report = json.loads(output.out)
    review(root, report)
    assert main(args + ["--mode", "commit", "--review-ref", "test_review"]) == 0
    capsys.readouterr()
    assert (
        main(["dataset", "official", "verify", "--dataset-version", report["dataset_version"]]) == 0
    )


def test_two_thousand_synthetic_records(authorized):
    _, _, file = authorized
    with file.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["feedback_id", "content", "created_at", "source_id"])
        for index in range(2000):
            writer.writerow([f"SYNTHETIC_{index}", f"GIẢ LẬP hồ sơ thử {index}", "", SOURCE])
    result = preview(authorized)
    assert result["unique_record_count"] == 2000
    assert result["invalid_records"] == result["duplicate_count"] == result["published_count"] == 0
    assert result["human_review_pending_count"] == 2000


def test_git_excludes_private_staged_processed_and_manifests():
    paths = [
        "data/private/input.csv",
        "data/private/reviews/test.json",
        "data/staging/version/candidates.jsonl",
        "data/processed/version/feedback.jsonl",
        "data/manifests/version/manifest.json",
        "data/synthetic/generated.csv",
    ]
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "check-ignore", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and result.stdout.splitlines() == paths
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "check-ignore",
            "tests/fixtures/public_service_feedback_synthetic.csv",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1


def test_approved_review_requires_privacy_clearance(authorized):
    report = preview(authorized)
    metadata = review(authorized[0], report)
    metadata["decisions"][0]["privacy_cleared"] = False
    file = authorized[0] / "data/private/reviews/test_review.json"
    file.write_text(json.dumps(metadata))
    with pytest.raises(IngestionBlocked):
        preview(authorized, mode="commit", review_ref="test_review")


def test_unsupported_format_is_rejected_after_authorization(authorized):
    root, registry, _ = authorized
    file = root / "data/private/SYNTHETIC.xlsx"
    file.write_bytes(b"SYNTHETIC unsupported input")
    with pytest.raises(IngestionError, match="Unsupported"):
        official.ingest(root, registry, SOURCE, file, "test_approval", KEY)


def test_native_storage_protection_failure_is_fatal(tmp_path, monkeypatch):
    if os.name == "nt":
        monkeypatch.setattr(official_io, "windows_sid", lambda: "S-1-5-18")
        monkeypatch.setattr(
            official_io.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1)
        )
        with pytest.raises(IngestionError, match="ACL"):
            official_io.protect_directory(tmp_path)
    else:
        original = Path.chmod

        def failure(path, *args, **kwargs):
            if path == tmp_path:
                raise PermissionError("SYNTHETIC chmod failure")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "chmod", failure)
        with pytest.raises(PermissionError):
            official_io.protect_directory(tmp_path)
