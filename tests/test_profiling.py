"""Offline STEP 05 audits: exclusively invented records and simulated permission decisions."""

import io
import json
import subprocess
import unicodedata
from pathlib import Path

import pytest
from pydantic import ValidationError

from pfa.cli import main
from pfa.data import profiling
from pfa.data.official_io import IngestionBlocked, IngestionError, rows
from pfa.data.official_schema import ImportOptions
from pfa.data.preprocessing import TRANSFORMATION_VERSION, transform_text
from pfa.data.privacy import audit_screen, screen
from pfa.data.quality import (
    ProfileContext,
    QualityConfig,
    QualityReport,
    markdown_summary,
    parse_timestamp,
    quality_gates,
)
from pfa.data.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]
KEY = b"SYNTHETIC-AUDIT-TEST-KEY-32-BYTES!!"


def context(**changes):
    values = dict(
        dataset_source="synthetic_demo",
        dataset_version="synthetic_test",
        dataset_type="SYNTHETIC",
        expected_record_source="synthetic_fixture",
        source_manifest_reference="synthetic_test_descriptor",
        source_manifest_checksum="a" * 64,
        permission_verified=False,
        manifest_verified=True,
        human_reviewed=False,
    )
    values.update(changes)
    return ProfileContext(**values)


def record(**changes):
    values = dict(
        feedback_id="INVENTED_1",
        content="Thủ tục chưa từng nhanh, không rõ hướng dẫn!",
        created_at=None,
        source_id="synthetic_fixture",
    )
    values.update(changes)
    return values


def profile(values, config=None, **changes):
    return profiling.profile_records(enumerate(values, 1), context(**changes), KEY, config)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    configs = tmp_path / "configs"
    configs.mkdir()
    for name in ("dataset_sources.yaml", "permission_evidence.json", "permission_history.jsonl"):
        (configs / name).write_bytes((ROOT / "configs" / name).read_bytes())
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("PFA_ENVIRONMENT", "test")
    monkeypatch.setenv("PFA_LOG_LEVEL", "INFO")
    return tmp_path, load_registry(configs / "dataset_sources.yaml")


def test_bundled_fixture_computed_statistics(workspace):
    root, registry = workspace
    report, path = profiling.run_audit(root, registry, "synthetic_demo")
    assert (report.record_count, report.valid_count, report.invalid_count) == (10, 8, 2)
    assert report.missing_values["created_at"] == 7
    assert report.missing_values["agency"] == 10
    assert report.missing_values["domain"] == 9
    assert report.timestamp_coverage["created_at"]["INVALID"] == 1
    assert report.timestamp_coverage["created_at"]["AWARE_TO_UTC"] == 2
    assert report.duplicate_statistics["exact_duplicate_count"] == 3
    assert report.duplicate_statistics["near_duplicate_pair_count"] == 1
    assert report.privacy_statistics["flagged_record_count"] == 3
    assert report.privacy_statistics["categories"]["phone"] == 2
    assert report.overall_quality_status == "WARN"
    assert not report.publication_eligible
    assert QualityReport.model_validate_json((path / "quality_report.json").read_bytes()) == report


@pytest.mark.parametrize("content", ["", "   ", "\x00\u200b"])
def test_empty_text(content):
    report, audit = profile([record(content=content)])
    assert report.invalid_count == 1
    assert "INVALID_TEXT" in audit["record_audit"][0]["warnings"]


def test_missing_metadata_and_unparseable_denominator():
    report, _ = profile([record(), None])
    assert (report.valid_count, report.invalid_count) == (1, 1)
    assert report.missing_values["agency"] == 1
    assert report.transformation_statistics["missing_fields"]["agency"] == 1
    assert report.transformation_statistics["unparseable_records"] == 1
    assert report.domain_distribution == {"MISSING": 1}


def test_missing_required_fields_are_counted():
    value = record()
    del value["source_id"]
    del value["created_at"]
    report, _ = profile([value])
    assert report.invalid_count == 1
    assert report.missing_values["source_id"] == 1
    assert report.transformation_statistics["missing_fields"]["created_at"] == 1


def test_unicode_normalization_negation_and_version():
    original = "  " + unicodedata.normalize("NFD", "không, chưa, chẳng, chưa từng!") + "\x00\n"
    cleaned, delta = transform_text(original)
    assert cleaned == "không, chưa, chẳng, chưa từng!"
    assert delta == {"unicode_nfc": 1, "controls_removed": 1, "whitespace": 1}
    report, audit = profile([record(content=original)])
    assert report.unicode_statistics["non_nfc_count"] == 1
    assert report.unicode_statistics["diacritic_record_count"] == 1
    assert report.transformation_version == TRANSFORMATION_VERSION
    assert audit["record_audit"][0]["changes"]["content"] == delta
    assert profiling.configuration_hash(QualityConfig()) != profiling.configuration_hash(
        QualityConfig(whitespace=False)
    )


def test_invalid_unicode_and_mixed_language():
    report, _ = profile([record(content="hỏng\ud800"), record(content="Please hướng dẫn 中文")])
    assert report.unicode_statistics["invalid_unicode_count"] == 1
    assert report.unicode_statistics["mixed_language_candidates"] == 1
    assert report.invalid_count == 1


@pytest.mark.parametrize(
    "value,state",
    [
        ("bad-date", "INVALID"),
        ("2026-01-01T10:00:00", "AMBIGUOUS_TIMEZONE"),
        (None, "MISSING"),
        ("2026-01-01T10:00:00+07:00", "AWARE_TO_UTC"),
    ],
)
def test_timestamp_states(value, state):
    parsed, actual = parse_timestamp(value, None)
    assert actual == state
    if state == "AWARE_TO_UTC":
        assert parsed.hour == 3


def test_configured_timezone_and_invalid_timestamp_records():
    parsed, state = parse_timestamp("2026-01-01T10:00:00", "+07:00")
    assert state == "CONFIGURED_TIMEZONE_TO_UTC" and parsed.hour == 3
    report, audit = profile([record(created_at="bad-date")])
    assert report.invalid_count == 1
    assert report.timestamp_coverage["created_at"]["INVALID"] == 1
    assert "CREATED_AT_INVALID" in audit["record_audit"][0]["warnings"]


def test_timestamp_overflow_is_invalid_without_crashing():
    value = "0001-01-01T00:00:00+23:00"
    assert parse_timestamp(value, None) == (None, "INVALID")
    assert profile([record(created_at=value)])[0].invalid_count == 1


def test_lengths_and_opaque_distributions():
    report, _ = profile(
        [
            record(content="Rõ", agency="PRIVATE_SENTINEL", domain="PRIVATE_DOMAIN"),
            record(feedback_id="two", content="Hướng dẫn không rõ."),
        ]
    )
    assert report.text_length_statistics["distribution"] == {
        "min": 2,
        "max": 19,
        "mean": 10.5,
        "p50": 2,
        "p95": 2,
    }
    assert report.text_length_statistics["short_count"] == 1
    assert report.missing_values["agency"] == report.missing_values["domain"] == 1
    assert "PRIVATE" not in report.model_dump_json()


def test_duplicate_groups_and_split_lineage():
    values = [
        record(),
        record(),
        record(feedback_id="other"),
        record(feedback_id="near", content="Thủ tục chưa từng rất nhanh, không rõ hướng dẫn!"),
    ]
    report, audit = profile(values, QualityConfig(near_duplicate_threshold=0.8))
    assert report.duplicate_statistics["exact_duplicate_count"] == 2
    assert report.duplicate_statistics["by_category"]["feedback_id"] == 1
    assert report.duplicate_statistics["near_duplicate_pair_count"] == 1
    assert len(audit["split_group_lineage"]) == 4
    assert len({item["group_id"] for item in audit["split_group_lineage"]}) == 1
    assert report.duplicate_statistics["same_case_or_thread"] == "NOT_AVAILABLE"
    assert "INVENTED_1" not in json.dumps(audit)


def test_sanitized_duplicates_have_separate_diagnostics():
    report, audit = profile(
        [
            record(content="GIẢ LẬP a@example.invalid"),
            record(feedback_id="two", content="GIẢ LẬP b@example.invalid"),
        ]
    )
    assert report.duplicate_statistics["by_category"]["normalized_text"] == 0
    assert report.duplicate_statistics["by_category"]["sanitized_content"] == 1
    assert len(audit["duplicate_groups"]["sanitized_content"]) == 1


def test_labeled_privacy_fixture_coverage():
    fixture = json.loads((ROOT / "tests/fixtures/privacy_audit_synthetic.json").read_text("utf-8"))
    assert fixture["dataset_type"] == "SYNTHETIC"
    tp = fp = fn = 0
    covered = set()
    for item in fixture["cases"]:
        actual = set(audit_screen(item["text"]).counts)
        expected = set(item["expected"])
        tp += len(actual & expected)
        fp += len(actual - expected)
        fn += len(expected - actual)
        covered |= actual & expected
    # These are intentional known regex errors, not real-world evaluation estimates.
    assert (tp, fp, fn) == (8, 1, 1)
    assert covered == {
        "phone",
        "email",
        "citizen_id",
        "personal_identifier",
        "address",
        "personal_name",
        "case_number",
        "sensitive_context",
    }


def test_redaction_regression_and_privacy_review():
    text = "GIẢ LẬP 0123456789 a@example.invalid CCCD 000000000000"
    for result in (screen(text), audit_screen(text)):
        assert "0123456789" not in result.text
        assert "a@example.invalid" not in result.text
        assert "000000000000" not in result.text
    assert audit_screen("Mã hồ sơ: HS-12345").text == "Mã hồ sơ: [REDACTED_CASE_NUMBER]"
    report, _ = profile([record(content="Địa chỉ: GIẢ LẬP")])
    assert report.privacy_statistics["review_pending_count"] == 1
    assert not report.publication_eligible


def test_no_raw_text_in_reports_logs_or_buckets(tmp_path, caplog):
    text = "SECRET_SENTINEL 0123456789 private@example.invalid"
    report, audit = profile([record(content=text, agency=text, domain=text)])
    path = profiling.save_reports(tmp_path, report, audit)
    outputs = "".join(file.read_text("utf-8") for file in path.iterdir()) + caplog.text
    for secret in (text, "SECRET_SENTINEL", "0123456789", "private@example.invalid", "INVENTED_1"):
        assert secret not in outputs
    assert "SYNTHETIC" in (path / "summary.md").read_text()


def test_quality_thresholds_and_mandatory_research_gates():
    report, _ = profile([record(), record(content="")])
    assert report.overall_quality_status == "FAIL"
    report, _ = profile([record()], QualityConfig(missingness_warn_fraction=1))
    assert report.overall_quality_status == "PASS"
    assert quality_gates(report, context(), QualityConfig()).overall_quality_status == "WARN"
    assert (
        quality_gates(
            report, context(manifest_verified=False), QualityConfig()
        ).overall_quality_status
        == "FAIL"
    )
    assert (
        quality_gates(
            report, context(supported_format=False), QualityConfig()
        ).overall_quality_status
        == "FAIL"
    )
    research = context(dataset_type="RESEARCH", permission_verified=True)
    modified = report.model_copy(update={"dataset_type": "RESEARCH"})
    assert quality_gates(modified, research, QualityConfig()).overall_quality_status == "FAIL"
    blocked = quality_gates(modified, context(dataset_type="RESEARCH"), QualityConfig())
    assert blocked.overall_quality_status == "BLOCKED_PERMISSION"
    assert not blocked.publication_eligible
    assert profile([])[0].overall_quality_status == "NOT_AVAILABLE"


def test_configured_failure_thresholds_and_research_privacy():
    config = QualityConfig(duplicate_warn_fraction=0.1, duplicate_fail_fraction=0.4)
    report, _ = profile([record(), record()], config)
    assert "DUPLICATE_ANOMALY" in report.quality_failures
    config = QualityConfig(missingness_warn_fraction=0.1, missingness_fail_fraction=0.5)
    report, _ = profile([record()], config)
    assert "MISSING_AGENCY" in report.quality_failures
    report, _ = profile(
        [record(content="GIẢ LẬP bệnh án")],
        dataset_type="RESEARCH",
        permission_verified=True,
        human_reviewed=True,
    )
    assert "UNRESOLVED_PRIVACY_REVIEW" in report.quality_failures
    assert not report.publication_eligible


def test_disabled_cleanup_cannot_pass_unsafe_controls():
    report, _ = profile([record(content="Hướng dẫn\x00 giả lập")], QualityConfig(controls=False))
    assert "UNSAFE_CONTROLS_REMAIN" in report.quality_failures


def test_near_pair_limit_fails_without_truncation():
    values = [
        record(feedback_id=f"TEST_{n}", content=f"Thủ tục giả lập cần hướng dẫn rõ ràng {n}")
        for n in range(4)
    ]
    with pytest.raises(IngestionError, match="review limit"):
        profile(values, QualityConfig(near_duplicate_threshold=0.5, max_candidate_pairs=1))


@pytest.mark.parametrize(
    "options",
    [
        {"max_records": 0},
        {"unknown": True},
        {"controls": "false"},
        {"max_invalid_fraction": 2},
        {"duplicate_warn_fraction": 0.8, "duplicate_fail_fraction": 0.2},
        {"known_timezone": "Mars/Unknown"},
        {"known_timezone": "+24:00"},
        {"short_text_chars": 1001},
        {"missingness_fail_fraction": 0.1},
    ],
)
def test_invalid_configuration(options):
    with pytest.raises(ValidationError):
        QualityConfig(**options)


def test_limits_and_source_identity():
    with pytest.raises(IngestionError, match="record count"):
        profile([record(), record()], QualityConfig(max_records=1))
    with pytest.raises(IngestionError, match="source identity"):
        profile([record(source_id="real_source")])
    with pytest.raises(IngestionBlocked):
        profile([record()], dataset_type="RESEARCH")


def test_permission_before_any_manifest_or_config_read(workspace, monkeypatch):
    root, registry = workspace

    def forbidden(*args, **kwargs):
        raise AssertionError("Manifest/config must not be read")

    monkeypatch.setattr(profiling, "safe_path", forbidden)
    with pytest.raises(IngestionBlocked):
        profiling.run_audit(
            root,
            registry,
            "authorized_agency_export",
            dataset_version="of_" + "a" * 32,
            config_path=Path("SECRET"),
        )


def test_cli_commands_and_real_gate(workspace, capsys):
    for action in ("profile", "preprocess", "audit-privacy"):
        assert main(["dataset", action, "--source", "synthetic_demo"]) == 0
        output = json.loads(capsys.readouterr().out)
        assert output["dataset_type"] == "SYNTHETIC" and output["status"] == "WARN"
        assert not output["publication_eligible"]
        assert main(["dataset", action, "--source", "authorized_agency_export"]) == 3
        assert "BLOCKED_PERMISSION" in capsys.readouterr().out


def test_cli_policy_failure_and_safe_configuration_errors(workspace, capsys):
    root, _ = workspace
    policy = root / "policy.json"
    policy.write_text('{"max_invalid_fraction": 0.0}')
    args = ["dataset", "profile", "--source", "synthetic_demo", "--config", str(policy)]
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"
    policy.write_text('{"PRIVATE_CONFIG_SENTINEL": "PRIVATE_VALUE"}')
    assert main(args) == 2
    output = capsys.readouterr().out
    assert "PRIVATE_CONFIG_SENTINEL" not in output and "PRIVATE_VALUE" not in output


def test_no_arbitrary_synthetic_inputs_or_versions(workspace):
    root, registry = workspace
    with pytest.raises(SystemExit) as error:
        main(["dataset", "profile", "--source", "synthetic_demo", "--input", "private.csv"])
    assert error.value.code == 2
    with pytest.raises(IngestionError, match="bundled"):
        profiling.run_audit(root, registry, "synthetic_demo", dataset_version="real")


def test_deterministic_immutable_reports_and_tamper_detection(tmp_path):
    report, audit = profile([record()])
    first = profiling.save_reports(tmp_path, report, audit)
    assert profiling.save_reports(tmp_path, report, audit) == first
    (first / "summary.md").write_text("CORRUPTED")
    with pytest.raises(IngestionError, match="integrity"):
        profiling.save_reports(tmp_path, report, audit)


def test_atomic_cleanup(tmp_path, monkeypatch):
    report, audit = profile([record()])

    def failure(*args, **kwargs):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(profiling.os, "fsync", failure)
    with pytest.raises(OSError):
        profiling.save_reports(tmp_path, report, audit)
    assert list((tmp_path / "reports/dataset").iterdir()) == []


def test_two_thousand_synthetic_records():
    values = (
        record(feedback_id=f"SYNTHETIC_{n}", content=f"Hướng dẫn giả lập mục {n}.")
        for n in range(2000)
    )
    report, audit = profiling.profile_records(enumerate(values, 1), context(), KEY)
    assert report.record_count == report.valid_count == 2000
    assert report.invalid_count == report.duplicate_statistics["exact_duplicate_count"] == 0
    assert len(audit["split_group_lineage"]) == 2000
    assert report.dataset_type == "SYNTHETIC" and not report.publication_eligible


def test_streaming_jsonl_and_encoding_validation():
    payload = json.dumps(record(), ensure_ascii=False).encode("utf-8") + b"\ninvalid\n"
    report, _ = profiling.profile_records(
        rows(io.BytesIO(payload), ".jsonl", ImportOptions()), context(), KEY
    )
    assert (report.valid_count, report.invalid_count) == (1, 1)
    with pytest.raises(IngestionError, match="UTF-8"):
        profiling.profile_records(
            rows(io.BytesIO(b"\xff\n"), ".jsonl", ImportOptions()), context(), KEY
        )


def test_git_excludes_report_bundles():
    paths = ["reports/dataset/q_test/quality_report.json", "reports/dataset/q_test/audit.json"]
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "check-ignore", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and result.stdout.splitlines() == paths


def test_markdown_never_renders_metadata_values():
    report, _ = profile([record(agency="SENSITIVE_AGENCY")])
    assert "SENSITIVE_AGENCY" not in markdown_summary(report)
