"""Real-source branches use STEP 04's simulated approvals and invented data in temporary roots."""

import json

import pytest
import test_annotation
import test_official

from pfa.annotation import io as annotation_io
from pfa.data.official_io import IngestionBlocked, IngestionError

authorized = test_official.authorized
workspace = test_official.workspace
sample = test_annotation.sample


@pytest.fixture
def submitted(authorized, sample):
    root, registry, _ = authorized
    (root / "configs/taxonomy_v1.yaml").write_bytes(
        (test_annotation.ROOT / "configs/taxonomy_v1.yaml").read_bytes()
    )
    built = test_official.commit(authorized)
    version = built["dataset_version"]
    data = root / "data/processed" / version / "feedback.jsonl"
    row = json.loads(data.read_text("utf-8").splitlines()[0])
    sample.update(
        dataset_type="RESEARCH",
        source_id=test_official.SOURCE,
        dataset_version=version,
        feedback_id=row["feedback_id"],
    )
    path = test_annotation.submission(
        root / "SYNTHETIC_TEST_SUBMISSION.jsonl",
        [sample],
        changes={
            "dataset_type": "RESEARCH",
            "source_id": test_official.SOURCE,
            "dataset_version": version,
        },
    )
    return root, registry, path, sample


def test_reviewed_membership(submitted):
    root, registry, path, _ = submitted
    result = annotation_io.validate(root, registry, path)
    assert result["status"] == "PASS" and result["valid_count"] == 1
    assert result["human_gold"] is False
    assert result["metrics_usage"] == "CONTRACT_VALIDATION_ONLY"


def test_revocation_before_annotation_read(submitted, monkeypatch):
    root, registry, path, _ = submitted
    test_official.decision(
        root, registry, reference="annotation_revocation", decision="REVOKED", allowed_scope=[]
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Annotation content must not be read after revocation")

    monkeypatch.setattr(annotation_io, "annotation_rows", forbidden)
    with pytest.raises(IngestionBlocked):
        annotation_io.validate(root, registry, path)


def test_corrupted_dataset_before_annotation_read(submitted, monkeypatch):
    root, registry, path, sample = submitted
    data = root / "data/processed" / sample["dataset_version"] / "feedback.jsonl"
    data.write_text("SYNTHETIC corruption")

    def forbidden(*args, **kwargs):
        raise AssertionError("Unverified input must not be read")

    monkeypatch.setattr(annotation_io, "annotation_rows", forbidden)
    with pytest.raises(IngestionError, match="checksum"):
        annotation_io.validate(root, registry, path)


def test_source_mismatch_before_other_dataset_verification(submitted, monkeypatch):
    root, registry, path, sample = submitted
    manifest = root / "data/manifests" / sample["dataset_version"] / "manifest.json"
    value = json.loads(manifest.read_text("utf-8"))
    value["source_id"] = "public_service_official"
    manifest.write_text(json.dumps(value))

    def forbidden(*args, **kwargs):
        raise AssertionError("Mismatched source must fail before data verification reads")

    monkeypatch.setattr(annotation_io.official, "verify", forbidden)
    with pytest.raises(IngestionError, match="provenance"):
        annotation_io.validate(root, registry, path)


def test_membership_failure_and_mid_validation_revocation(submitted, monkeypatch):
    root, registry, path, sample = submitted
    sample["feedback_id"] = "f_" + "0" * 32
    path.write_text(json.dumps(sample) + "\n")
    result = annotation_io.validate(root, registry, path)
    assert result["errors"] == [{"row": 1, "code": "UNKNOWN_FEEDBACK_MEMBERSHIP"}]
    original = annotation_io.annotation_rows

    def revoke_after_rows(source):
        yield from original(source)
        test_official.decision(
            root,
            registry,
            reference="annotation_mid_revocation",
            decision="REVOKED",
            allowed_scope=[],
        )

    monkeypatch.setattr(annotation_io, "annotation_rows", revoke_after_rows)
    with pytest.raises(IngestionBlocked):
        annotation_io.validate(root, registry, path)


def test_changed_manifest_snapshot_is_rejected(submitted, monkeypatch):
    root, registry, path, sample = submitted
    manifest = root / "data/manifests" / sample["dataset_version"] / "manifest.json"
    original = annotation_io.annotation_rows

    def change_after_rows(source):
        yield from original(source)
        value = json.loads(manifest.read_text("utf-8"))
        value["built_at"] = "2026-01-01T00:00:00+00:00"
        manifest.write_text(json.dumps(value))

    monkeypatch.setattr(annotation_io, "annotation_rows", change_after_rows)
    with pytest.raises(IngestionError, match="provenance changed"):
        annotation_io.validate(root, registry, path)
