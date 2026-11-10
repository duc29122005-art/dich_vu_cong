"""STEP 06 software tests only: invented annotations, never human-labeled gold data."""

import csv
import io
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pfa.annotation import io as annotation_io
from pfa.annotation.schema import Annotation, AnnotationMetadata, BlankAnnotation
from pfa.annotation.taxonomy import CHECKSUM, VERSION, Taxonomy, checksum, load_taxonomy
from pfa.cli import main
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    for name in (
        "taxonomy_v1.yaml",
        "dataset_sources.yaml",
        "permission_evidence.json",
        "permission_history.jsonl",
    ):
        (tmp_path / "configs" / name).write_bytes((ROOT / "configs" / name).read_bytes())
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("PFA_ENVIRONMENT", "test")
    monkeypatch.setenv("PFA_LOG_LEVEL", "INFO")
    return tmp_path, load_registry(tmp_path / "configs/dataset_sources.yaml")


@pytest.fixture
def sample():
    version, ids = annotation_io.synthetic_inventory()
    return dict(
        feedback_id=sorted(ids)[0],
        dataset_version=version,
        taxonomy_version=VERSION,
        taxonomy_checksum=CHECKSUM,
        source_id="synthetic_demo",
        dataset_type="SYNTHETIC",
        annotator_id="ann_0123456789abcdef",
        topic_label="delayed_processing",
        sentiment_label="negative",
        severity_label="medium",
        multiple_issues=False,
        annotation_status="SUBMITTED",
        topic_justification="SYNTHETIC: vấn đề chính là tiến độ xử lý.",
        sentiment_justification="SYNTHETIC: thể hiện chưa hài lòng.",
        severity_justification="SYNTHETIC: mô tả gián đoạn cụ thể, chưa có rủi ro khẩn cấp.",
        review_reason=None,
        annotated_at="2026-01-02T09:00:00+07:00",
    )


def submission(path, records, *, changes=None):
    version, _ = annotation_io.synthetic_inventory()
    metadata = dict(
        format_version="annotation-1",
        purpose="ANNOTATION_SUBMISSION",
        taxonomy_version=VERSION,
        taxonomy_checksum=CHECKSUM,
        dataset_type="SYNTHETIC",
        source_id="synthetic_demo",
        dataset_version=version,
        columns=annotation_io.COLUMNS,
        human_gold=False,
    )
    metadata.update(changes or {})
    annotation_io.metadata_path(path).write_text(json.dumps(metadata), encoding="utf-8")
    if path.suffix == ".csv":
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=annotation_io.COLUMNS)
            writer.writeheader()
            for item in records:
                item = item.copy()
                item["multiple_issues"] = "true" if item["multiple_issues"] else "false"
                writer.writerow(item)
    else:
        path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
            encoding="utf-8",
        )
    return path


@pytest.mark.parametrize(
    "topic",
    [
        "delayed_processing",
        "complex_procedure",
        "unclear_guidance",
        "online_system_error",
        "staff_attitude",
        "fees",
        "unsatisfactory_result",
        "other",
    ],
)
def test_eight_topics(sample, topic):
    sample["topic_label"] = topic
    assert Annotation.model_validate(sample).topic_label == topic


@pytest.mark.parametrize("sentiment", ["negative", "neutral", "positive"])
def test_three_sentiments(sample, sentiment):
    sample["sentiment_label"] = sentiment
    assert Annotation.model_validate(sample).sentiment_label == sentiment


@pytest.mark.parametrize("severity", ["low", "medium", "high"])
def test_three_severities_independent_of_sentiment(sample, severity):
    sample.update(severity_label=severity, sentiment_label="positive")
    assert Annotation.model_validate(sample).severity_label == severity


def test_unknown_severity_requires_reason_and_review(sample):
    sample["severity_label"] = "unknown"
    with pytest.raises(ValidationError):
        Annotation.model_validate(sample)
    sample.update(annotation_status="REQUIRES_REVIEW", review_reason="SYNTHETIC: thiếu bằng chứng.")
    assert Annotation.model_validate(sample).severity_label == "unknown"
    sample["review_reason"] = None
    with pytest.raises(ValidationError):
        Annotation.model_validate(sample)


@pytest.mark.parametrize(
    "field,value",
    [
        ("topic_label", "wrong"),
        ("topic_label", ["fees", "other"]),
        ("sentiment_label", "mixed"),
        ("severity_label", "requires_review"),
        ("taxonomy_version", "2.0.0"),
        ("taxonomy_checksum", "0" * 64),
        ("annotation_status", "APPROVED"),
        ("annotator_id", None),
        ("annotator_id", "person@example.invalid"),
        ("feedback_id", "raw-citizen-id"),
        ("feedback_id", None),
        ("dataset_version", "unknown"),
        ("topic_justification", None),
        ("sentiment_justification", None),
        ("severity_justification", "   "),
        ("multiple_issues", "true"),
        ("annotated_at", "bad-date"),
        ("annotated_at", "2026-01-01T00:00:00"),
        ("annotated_at", "9999-01-01T00:00:00+00:00"),
        ("annotation_status", "DRAFT"),
    ],
)
def test_invalid_fields(sample, field, value):
    sample[field] = value
    with pytest.raises(ValidationError):
        Annotation.model_validate(sample)


def test_partial_review_and_multiple_issues(sample):
    sample.update(multiple_issues=True)
    assert Annotation.model_validate(sample).multiple_issues
    sample.update(
        topic_label=None,
        topic_justification=None,
        annotation_status="REQUIRES_REVIEW",
        review_reason="SYNTHETIC: hai vấn đề ngang nhau, cần xem xét trọng tâm.",
    )
    assert Annotation.model_validate(sample).topic_label is None
    sample["review_reason"] = None
    with pytest.raises(ValidationError):
        Annotation.model_validate(sample)


@pytest.mark.parametrize("status", ["OUT_OF_SCOPE", "UNLABELABLE"])
def test_excluded_records_are_not_other(sample, status):
    sample.update(annotation_status=status, review_reason="SYNTHETIC: lý do loại khỏi nhãn.")
    with pytest.raises(ValidationError):
        Annotation.model_validate(sample)
    for name in (
        "topic_label",
        "sentiment_label",
        "severity_label",
        "topic_justification",
        "sentiment_justification",
        "severity_justification",
    ):
        sample[name] = None
    assert Annotation.model_validate(sample).annotation_status == status
    sample["topic_label"] = "other"
    with pytest.raises(ValidationError):
        Annotation.model_validate(sample)


def test_review_reason_cannot_be_submitted_as_complete(sample):
    sample["review_reason"] = "SYNTHETIC: chưa giải quyết ngữ cảnh."
    with pytest.raises(ValidationError):
        Annotation.model_validate(sample)


def test_taxonomy_checksum_and_all_definitions(workspace):
    root, _ = workspace
    taxonomy = load_taxonomy(root)
    assert checksum(taxonomy) == CHECKSUM
    assert [len(task.labels) for task in taxonomy.tasks] == [8, 3, 3]
    assert all(
        label.definition and label.name_vi for task in taxonomy.tasks for label in task.labels
    )
    value = json.loads((root / "configs/taxonomy_v1.yaml").read_text("utf-8"))
    reversed_keys = dict(reversed(list(value.items())))
    assert checksum(Taxonomy.model_validate(reversed_keys)) == CHECKSUM
    (root / "configs/taxonomy_v1.yaml").write_text(json.dumps(value, indent=4), encoding="utf-8")
    assert checksum(load_taxonomy(root)) == CHECKSUM


@pytest.mark.parametrize(
    "mutation", ["definition", "order", "version", "duplicate", "unknown_label"]
)
def test_taxonomy_immutability(workspace, mutation):
    root, _ = workspace
    path = root / "configs/taxonomy_v1.yaml"
    value = json.loads(path.read_text("utf-8"))
    labels = value["tasks"][0]["labels"]
    if mutation == "definition":
        labels[0]["definition"] += " Changed meaning"
    elif mutation == "order":
        labels.reverse()
    elif mutation == "version":
        value["version"] = "1.0.1"
    elif mutation == "duplicate":
        labels.append(labels[0])
    else:
        labels[0]["code"] = "invalid"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(IngestionError):
        load_taxonomy(root)


@pytest.mark.parametrize("suffix", [".csv", ".jsonl"])
def test_empty_template_schema_only_and_no_overwrite(workspace, suffix):
    root, registry = workspace
    path = root / "data/fixtures" / ("annotation_template" + suffix)
    result = annotation_io.template(root, path)
    assert result["record_count"] == 0 and result["human_gold"] is False
    metadata = AnnotationMetadata.model_validate_json(
        annotation_io.metadata_path(path).read_bytes()
    )
    assert metadata.dataset_version is None and metadata.dataset_type == "TEMPLATE"
    assert metadata.taxonomy_checksum == CHECKSUM
    result = annotation_io.validate(root, registry, path, schema_only=True)
    assert result["status"] == "PASS" and result["record_count"] == 0
    before = path.read_bytes()
    with pytest.raises(IngestionError, match="already exists"):
        annotation_io.template(root, path)
    assert path.read_bytes() == before
    with pytest.raises(IngestionError, match="blank templates"):
        annotation_io.validate(root, registry, path)


@pytest.mark.parametrize("suffix", [".csv", ".jsonl"])
def test_valid_utf8_submission_and_no_source_mutation(workspace, sample, suffix):
    root, registry = workspace
    path = submission(root / ("SYNTHETIC" + suffix), [sample])
    before = path.read_bytes()
    result = annotation_io.validate(root, registry, path)
    assert result["status"] == "PASS" and result["valid_count"] == 1
    assert result["metrics_usage"] == "SOFTWARE_TEST_ONLY" and not result["human_gold"]
    assert path.read_bytes() == before


def test_duplicate_keys_and_independent_annotators(workspace, sample):
    root, registry = workspace
    path = submission(root / "SYNTHETIC.jsonl", [sample, sample])
    result = annotation_io.validate(root, registry, path)
    assert result["status"] == "FAIL" and result["invalid_count"] == 1
    assert result["errors"] == [{"row": 2, "code": "DUPLICATE_ANNOTATION_KEY"}]
    second = {**sample, "annotator_id": "ann_fedcba9876543210"}
    submission(path, [sample, second])
    result = annotation_io.validate(root, registry, path)
    assert result["status"] == "PASS" and result["valid_count"] == 2
    assert (
        Annotation.model_validate(sample).record_key != Annotation.model_validate(second).record_key
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "authorized_agency_export"),
        ("dataset_version", "of_" + "0" * 32),
        ("dataset_type", "RESEARCH"),
        ("feedback_id", "f_" + "0" * 32),
    ],
)
def test_source_membership_mismatch(workspace, sample, field, value):
    root, registry = workspace
    sample[field] = value
    path = submission(root / "SYNTHETIC.jsonl", [sample])
    assert annotation_io.validate(root, registry, path)["status"] == "FAIL"


def test_empty_strict_submission_fails(workspace):
    root, registry = workspace
    path = submission(root / "SYNTHETIC.jsonl", [])
    assert annotation_io.validate(root, registry, path)["quality_failures"] == ["EMPTY_SUBMISSION"]


@pytest.mark.parametrize("problem", ["missing", "extra", "duplicate", "bad_quote", "encoding"])
def test_invalid_csv(workspace, sample, problem):
    root, registry = workspace
    path = submission(root / "SYNTHETIC.csv", [sample])
    if problem == "encoding":
        path.write_bytes(b"\xff\xfe")
    else:
        stream = io.StringIO(newline="")
        columns = annotation_io.COLUMNS.copy()
        if problem == "missing":
            columns.pop()
        elif problem == "extra":
            columns.append("PRIVATE_SENTINEL_COLUMN")
        elif problem == "duplicate":
            columns[-1] = columns[0]
        csv.writer(stream).writerow(columns)
        path.write_text(
            stream.getvalue() + ('"unterminated' if problem == "bad_quote" else ""),
            encoding="utf-8",
        )
    with pytest.raises(IngestionError):
        annotation_io.validate(root, registry, path)


def test_missing_metadata_and_bad_jsonl_are_safe(workspace, sample):
    root, registry = workspace
    path = submission(root / "SYNTHETIC.jsonl", [sample])
    path.write_text('{"PRIVATE_KEY":"PRIVATE_VALUE"}\n{bad-json}\n', encoding="utf-8")
    result = annotation_io.validate(root, registry, path)
    assert result["invalid_count"] == 2
    assert "PRIVATE" not in json.dumps(result)
    annotation_io.metadata_path(path).unlink()
    with pytest.raises(IngestionError, match="metadata sidecar"):
        annotation_io.validate(root, registry, path)


def test_permission_gate_precedes_annotation_content(workspace, sample, monkeypatch):
    root, registry = workspace
    path = submission(
        root / "SYNTHETIC.jsonl",
        [sample],
        changes={"dataset_type": "RESEARCH", "source_id": "authorized_agency_export"},
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Unauthorized annotation content must not be read")

    monkeypatch.setattr(annotation_io, "annotation_rows", forbidden)
    with pytest.raises(IngestionBlocked):
        annotation_io.validate(root, registry, path)
    with pytest.raises(IngestionBlocked):
        annotation_io.validate(root, registry, path, schema_only=True)


def test_synthetic_provenance_cannot_be_rebound(workspace, sample):
    root, registry = workspace
    path = submission(
        root / "SYNTHETIC.jsonl", [sample], changes={"source_id": "authorized_agency_export"}
    )
    with pytest.raises(IngestionError, match="bundled software fixture"):
        annotation_io.validate(root, registry, path)


def test_pii_never_in_reports_or_logs(workspace, sample, capsys, caplog):
    root, registry = workspace
    sample["topic_justification"] = "PRIVATE_SENTINEL 0123456789 user@example.invalid"
    path = submission(root / "SYNTHETIC.jsonl", [sample])
    result = annotation_io.validate(root, registry, path)
    assert result["status"] == "FAIL"
    assert main(["annotation", "validate", "--input", str(path)]) == 2
    output = json.dumps(result) + capsys.readouterr().out + caplog.text
    for text in ("PRIVATE_SENTINEL", "0123456789", "user@example.invalid", sample["feedback_id"]):
        assert text not in output


def test_cli_taxonomy_and_template(workspace, capsys):
    root, _ = workspace
    assert main(["annotation", "taxonomy", "show"]) == 0
    assert json.loads(capsys.readouterr().out)["checksum"] == CHECKSUM
    path = root / "data/fixtures/annotation_template.csv"
    assert main(["annotation", "template", "--output", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["record_count"] == 0
    assert main(["annotation", "validate", "--input", str(path), "--schema-only"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    assert main(["annotation", "validate", "--input", str(path)]) == 2
    assert "blank templates" in capsys.readouterr().out


def test_blank_model_and_unknown_columns():
    assert all(value is None for value in BlankAnnotation().model_dump().values())
    with pytest.raises(ValidationError):
        BlankAnnotation(raw_content="not permitted")


def test_template_pair_failure_rolls_back(workspace, monkeypatch):
    root, _ = workspace
    original = annotation_io.os.link

    def fail_second(source, destination):
        if str(destination).endswith("metadata.json"):
            raise OSError("SYNTHETIC failure")
        original(source, destination)

    monkeypatch.setattr(annotation_io.os, "link", fail_second)
    output = root / "data/fixtures/annotation_template.csv"
    with pytest.raises(OSError):
        annotation_io.template(root, output)
    assert not output.exists() and not annotation_io.metadata_path(output).exists()
    assert list(output.parent.iterdir()) == []
