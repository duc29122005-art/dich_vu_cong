"""SYNTHETIC fixtures only. Mocked external branches never contact Hugging Face."""

import io
import json
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from pfa.cli import main
from pfa.data import benchmark, benchmark_http
from pfa.data.adapters.uit_vsfc import (
    LABELS,
    SPLITS,
    BenchmarkError,
    label_status,
    parquet_rows,
    summarize_parquet,
    validate_row,
)
from pfa.data.permissions import record_decision
from pfa.data.registry import Registry, load_registry

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / "tests/fixtures/uit_vsfc_synthetic.json").read_text(encoding="utf-8"))
ROWS = FIXTURES["valid_rows"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    opener = Mock()
    opener.open.side_effect = AssertionError("Unexpected network attempt in offline tests")
    monkeypatch.setattr(benchmark_http, "build_opener", lambda *args: opener)
    monkeypatch.setattr(benchmark_http.time, "sleep", Mock())


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "dataset_sources.yaml").write_bytes(
        (ROOT / "configs/dataset_sources.yaml").read_bytes()
    )
    (configs / "permission_evidence.json").write_text('{"decisions": []}')
    (configs / "permission_history.jsonl").write_text("")
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("PFA_ENVIRONMENT", "test")
    monkeypatch.setenv("PFA_LOG_LEVEL", "INFO")
    return tmp_path, load_registry(configs / "dataset_sources.yaml")


def review_fixture(
    root, registry, *, scope=None, decision="APPROVED", reference="synthetic_review"
):
    """Invented metadata, used only inside pytest temporary storage."""
    record = {
        "approval_ref": reference,
        "source_id": "uit_vsfc",
        "reviewer": "SYNTHETIC TEST REVIEWER",
        "evidence_reference": "synthetic_document",
        "decision_date": date.today().isoformat(),
        "decision": decision,
        "allowed_scope": scope if scope is not None else ["internal_analysis"],
        "human_verified": True,
        "license_verified": True,
        "privacy_verified": True,
        "retention_policy": "SYNTHETIC: delete at test teardown",
    }
    path = root / "configs/permission_evidence.json"
    payload = json.loads(path.read_text())
    payload["decisions"].append(record)
    path.write_text(json.dumps(payload))
    record_decision(root, registry, "uit_vsfc", reference)


@pytest.fixture
def approved(workspace):
    root, registry = workspace
    payload = registry.model_dump()
    source = next(item for item in payload["sources"] if item["source_id"] == "uit_vsfc")
    source.update(
        permission_status="APPROVED",
        license_status="VERIFIED",
        allowed_processing=["internal_analysis"],
    )
    registry = Registry.model_validate(payload)
    review_fixture(root, registry)
    (root / "configs/dataset_sources.yaml").write_text(json.dumps(registry.model_dump()))
    return root, registry


def table(rows=ROWS, *, official_labels=False):
    schema = pa.schema(
        [("sentence", pa.string()), ("sentiment", pa.int64()), ("topic", pa.int64())]
    )
    metadata = {b"pfa_fixture": b"SYNTHETIC"}
    if official_labels:
        # Simulated official metadata; never an actual verification of UIT-VSFC.
        features = {field: {"names": list(names.values())} for field, names in LABELS.items()}
        metadata[b"huggingface"] = json.dumps({"info": {"features": features}}).encode()
    return pa.Table.from_pylist(rows, schema=schema.with_metadata(metadata))


def parquet_bytes():
    stream = io.BytesIO()
    pq.write_table(table(), stream)
    return stream.getvalue()


def fake_metadata():
    return {
        "id": benchmark.REPOSITORY,
        "sha": "a" * 40,
        "siblings": [{"rfilename": f"default/{split}/0000.parquet"} for split in SPLITS],
        "cardData": {
            "dataset_info": {
                "features": [
                    {"name": field, "dtype": {"class_label": {"names": names}}}
                    for field, names in LABELS.items()
                ]
            }
        },
    }


def mock_transfers(monkeypatch, *, broken=False):
    calls = []

    def transfer(url, stream, limit=None):
        calls.append(url)
        if "/api/datasets/" in url:
            stream.write(json.dumps(fake_metadata()).encode())
        else:
            stream.write(parquet_bytes())
            if broken:
                raise BenchmarkError("SYNTHETIC connection failure")

    monkeypatch.setattr(benchmark, "transfer", transfer)
    return calls


def synthetic_directory(root):
    directory = root / "data/benchmarks/uit_vsfc"
    directory.mkdir(parents=True)
    records = []
    for split in SPLITS:
        file = directory / f"{split}.parquet"
        pq.write_table(table(), file)
        records.append(
            {
                "path": file.name,
                "split": split,
                "file_url": f"https://example.invalid/SYNTHETIC/{file.name}",
                "sha256": benchmark.checksum(file),
                "size_bytes": file.stat().st_size,
                "row_count": len(ROWS),
            }
        )
    manifest = {
        "source_id": "synthetic_fixture",
        "source_url": "https://example.invalid/SYNTHETIC",
        "dataset_role": "BENCHMARK",
        "dataset_revision": "SYNTHETIC",
        "approval_reference": None,
        "download_timestamp": datetime.now(UTC).isoformat(),
        "files": records,
        "schema": summarize_parquet(directory / "train.parquet", "train")["schema"],
        "split_names": list(SPLITS),
        "row_counts": dict.fromkeys(SPLITS, len(ROWS)),
        "label_mapping": LABELS,
        "label_mapping_status": dict.fromkeys(LABELS, "UNVERIFIED"),
        "metadata_features": {},
        "data_provenance": "SYNTHETIC",
        "source_repository": "SYNTHETIC",
        "metadata_url": "UNKNOWN",
        "adapter_version": "1",
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory, manifest


def test_valid_utf8_schema_and_original_ids(tmp_path):
    file = tmp_path / "synthetic.parquet"
    pq.write_table(table(), file)
    assert list(parquet_rows(file, "train")) == ROWS
    result = summarize_parquet(file, "train")
    assert result["row_count"] == 4
    assert result["label_status"] == dict.fromkeys(LABELS, "UNVERIFIED")


@pytest.mark.parametrize("row", FIXTURES["invalid_rows"])
def test_invalid_records_never_drop_or_echo_text(row):
    with pytest.raises(BenchmarkError) as failure:
        validate_row(row)
    assert "GIẢ LẬP" not in str(failure.value)


def test_schema_split_and_missing_files(tmp_path):
    with pytest.raises(BenchmarkError, match="Schema mismatch"):
        validate_row({"sentence": "GIẢ LẬP"})
    with pytest.raises(BenchmarkError, match="Unknown split"):
        list(parquet_rows(tmp_path / "missing", "unknown"))
    with pytest.raises(BenchmarkError, match="missing"):
        list(parquet_rows(tmp_path / "missing", "train"))
    file = tmp_path / "bad.parquet"
    pq.write_table(pa.table({"sentence": ["GIẢ LẬP"]}), file)
    with pytest.raises(BenchmarkError, match="schema mismatch"):
        list(parquet_rows(file, "train"))
    pq.write_table(pa.table({"sentence": ["GIẢ LẬP"], "sentiment": [1.0], "topic": [0]}), file)
    with pytest.raises(BenchmarkError, match="integers"):
        list(parquet_rows(file, "train"))
    file.write_bytes(b"SYNTHETIC corrupted parquet")
    with pytest.raises(BenchmarkError, match="corrupted"):
        list(parquet_rows(file, "train"))


def test_invalid_parquet_row_fails_entire_validation(tmp_path):
    file = tmp_path / "bad.parquet"
    pq.write_table(table([ROWS[0], {**ROWS[0], "sentence": None}]), file)
    with pytest.raises(BenchmarkError, match="Row 1"):
        summarize_parquet(file, "train")


def test_mapping_requires_available_metadata(tmp_path):
    assert label_status({}) == dict.fromkeys(LABELS, "UNVERIFIED")
    with pytest.raises(BenchmarkError, match="conflicts"):
        label_status({"topic": {"names": ["public_service"]}})
    file = tmp_path / "synthetic.parquet"
    pq.write_table(table(official_labels=True), file)
    assert set(summarize_parquet(file, "test")["label_status"].values()) == {
        "VERIFIED_SOURCE_METADATA"
    }


def test_local_inspect_and_missing_cli(workspace, capsys):
    assert main(["dataset", "benchmark", "inspect", "--source", "uit_vsfc"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["actual_row_counts"] is None
    assert result["verified_fields"] == []
    assert main(["dataset", "benchmark", "verify", "--source", "uit_vsfc"]) == 4
    assert "NOT_AVAILABLE" in capsys.readouterr().out


def test_download_blocked_before_network(workspace, monkeypatch, capsys):
    root, registry = workspace
    transfer = Mock(side_effect=AssertionError("Network must not run"))
    monkeypatch.setattr(benchmark, "transfer", transfer)
    assert (
        main(
            [
                "dataset",
                "benchmark",
                "fetch",
                "--source",
                "uit_vsfc",
                "--approval-ref",
                "unapproved",
            ]
        )
        == 3
    )
    assert "BLOCKED_PERMISSION" in capsys.readouterr().out
    with pytest.raises(benchmark.BenchmarkPermissionError):
        benchmark.discover(root, registry, "unapproved")
    transfer.assert_not_called()
    assert not (root / "data").exists()


def test_invalid_reference_revocation_and_evidence_mismatch(approved):
    root, registry = approved
    with pytest.raises(benchmark.BenchmarkPermissionError, match="not current"):
        benchmark.fetch(root, registry, "wrong_reference")
    review_fixture(root, registry, scope=[], decision="REVOKED", reference="synthetic_revocation")
    with pytest.raises(benchmark.BenchmarkPermissionError):
        benchmark.fetch(root, registry, "synthetic_review")
    path = root / "configs/permission_evidence.json"
    path.write_text('{"decisions": []}')
    with pytest.raises(benchmark.BenchmarkPermissionError):
        benchmark.fetch(root, registry, "synthetic_revocation")


def test_wrong_scope_or_unresolved_registry(workspace):
    root, registry = workspace
    review_fixture(root, registry, scope=["software_tests"])
    with pytest.raises(benchmark.BenchmarkPermissionError):
        benchmark.fetch(root, registry, "synthetic_review")
    review_fixture(root, registry, reference="synthetic_internal")
    with pytest.raises(benchmark.BenchmarkPermissionError, match="unresolved"):
        benchmark.fetch(root, registry, "synthetic_internal")


def test_discovery_resolves_and_pins_metadata(approved, monkeypatch):
    root, registry = approved
    calls = mock_transfers(monkeypatch)
    result = benchmark.discover(root, registry, "synthetic_review")
    assert result["dataset_revision"] == "a" * 40
    assert all("/resolve/" + "a" * 40 in item["url"] for item in result["files"])
    assert result["actual_row_counts"] is None
    assert result["download_status"] == "NOT_DOWNLOADED"
    assert len(calls) == 1


def test_pinned_revision_mismatch_is_rejected(approved, monkeypatch):
    root, registry = approved
    mock_transfers(monkeypatch)
    with pytest.raises(BenchmarkError, match="pinned commit"):
        benchmark.discover(root, registry, "synthetic_review", "b" * 40)


def test_explicit_remote_inspection_cli(approved, monkeypatch, capsys):
    mock_transfers(monkeypatch)
    arguments = ["dataset", "benchmark", "inspect", "--source", "uit_vsfc", "--remote"]
    assert main(arguments) == 3
    assert "approval reference" in capsys.readouterr().out
    assert main(arguments + ["--approval-ref", "synthetic_review", "--revision", "a" * 40]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["remote_metadata"]["download_status"] == "NOT_DOWNLOADED"
    assert result["remote_metadata"]["actual_row_counts"] is None


def test_http_size_limit_keeps_safe_specific_error(monkeypatch):
    opener = Mock()
    opener.open.return_value = Response()
    monkeypatch.setattr(benchmark_http, "build_opener", lambda *args: opener)
    with pytest.raises(BenchmarkError, match="size limit"):
        benchmark_http.transfer("https://example.invalid/SYNTHETIC", io.BytesIO(), limit=2)


def test_invalid_download_never_publishes_manifest(approved, monkeypatch):
    root, registry = approved

    def invalid_transfer(url, stream, limit=None):
        if "/api/datasets/" in url:
            stream.write(json.dumps(fake_metadata()).encode())
        else:
            stream.write(b"SYNTHETIC broken parquet")

    monkeypatch.setattr(benchmark, "transfer", invalid_transfer)
    with pytest.raises(BenchmarkError, match="corrupted"):
        benchmark.fetch(root, registry, "synthetic_review")
    assert not list((root / "data/benchmarks").iterdir())


@pytest.mark.parametrize("mutation", ["no_parquet", "unknown_split", "bad_sha", "conflict"])
def test_discovery_rejects_incomplete_metadata(approved, monkeypatch, mutation):
    root, registry = approved
    payload = fake_metadata()
    if mutation == "no_parquet":
        payload["siblings"] = []
    elif mutation == "unknown_split":
        payload["siblings"][0]["rfilename"] = "default/unknown/0000.parquet"
    elif mutation == "bad_sha":
        payload["sha"] = "main"
    else:
        payload["cardData"]["dataset_info"]["features"][0]["dtype"]["class_label"]["names"] = [
            "wrong"
        ]
    monkeypatch.setattr(
        benchmark, "transfer", lambda url, stream, limit: stream.write(json.dumps(payload).encode())
    )
    with pytest.raises(BenchmarkError):
        benchmark.discover(root, registry, "synthetic_review")


def test_mocked_fetch_atomic_manifest_and_no_overwrite(approved, monkeypatch):
    root, registry = approved
    calls = mock_transfers(monkeypatch)
    result = benchmark.fetch(root, registry, "synthetic_review")
    assert result["row_counts"] == dict.fromkeys(SPLITS, 4)
    assert len(calls) == 4
    directory = root / "data/benchmarks/uit_vsfc"
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["approval_reference"] == "synthetic_review"
    assert manifest["dataset_revision"] == "a" * 40
    assert benchmark.verify_local(root, registry)["status"] == "VERIFIED"
    with pytest.raises(BenchmarkError, match="exists"):
        benchmark.fetch(root, registry, "synthetic_review")
    assert list(directory.parent.iterdir()) == [directory]


def test_partial_download_cleanup(approved, monkeypatch):
    root, registry = approved
    mock_transfers(monkeypatch, broken=True)
    with pytest.raises(BenchmarkError):
        benchmark.fetch(root, registry, "synthetic_review")
    assert not list((root / "data/benchmarks").iterdir())


def test_synthetic_cli_verify_without_external_approval(workspace, capsys):
    root, _ = workspace
    synthetic_directory(root)
    assert main(["dataset", "benchmark", "verify", "--source", "uit_vsfc"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "VERIFIED_SYNTHETIC"
    assert result["data_provenance"] == "SYNTHETIC"


@pytest.mark.parametrize(
    "mutation", ["checksum", "rows", "schema", "missing", "extra", "path", "corrupt"]
)
def test_manifest_and_files_must_agree(workspace, mutation):
    root, _ = workspace
    directory, manifest = synthetic_directory(root)
    file = directory / "train.parquet"
    if mutation == "checksum":
        manifest["files"][0]["sha256"] = "0" * 64
    elif mutation == "rows":
        manifest["row_counts"]["train"] += 1
    elif mutation == "schema":
        manifest["schema"]["topic"] = "string"
    elif mutation == "missing":
        file.unlink()
    elif mutation == "extra":
        (directory / "unexpected.parquet").write_bytes(b"SYNTHETIC")
    elif mutation == "path":
        manifest["files"][0]["path"] = "../escape.parquet"
    else:
        file.write_bytes(b"SYNTHETIC broken Parquet")
        manifest["files"][0].update(sha256=benchmark.checksum(file), size_bytes=file.stat().st_size)
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        benchmark.verify_directory(directory)


class Response(io.BytesIO):
    def __init__(self, data=b"SYNTHETIC", length=None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data) if length is None else length)}

    def geturl(self):
        return "https://example.invalid/SYNTHETIC"


@pytest.mark.parametrize("code,attempts", [(403, 1), (404, 1), (429, 3), (503, 3)])
def test_http_failures_bounded_safe_and_timed(monkeypatch, code, attempts):
    opener = Mock()
    opener.open.side_effect = lambda *args, **kwargs: (_ for _ in ()).throw(
        HTTPError("https://example.invalid/private", code, "PRIVATE-SENTINEL", {}, None)
    )
    monkeypatch.setattr(benchmark_http, "build_opener", lambda *args: opener)
    with pytest.raises(BenchmarkError, match=f"HTTP {code}") as failure:
        benchmark_http.transfer("https://example.invalid/SYNTHETIC", io.BytesIO())
    assert "PRIVATE-SENTINEL" not in str(failure.value)
    assert opener.open.call_count == attempts
    assert opener.open.call_args.kwargs["timeout"] == 30


def test_http_retry_restarts_and_truncates(monkeypatch):
    class Partial(Response):
        def read(self, size=-1):
            if self.tell():
                raise ConnectionError("PRIVATE-SENTINEL")
            return super().read(3)

    opener = Mock()
    opener.open.side_effect = [Partial(b"partial"), URLError("private"), Response()]
    monkeypatch.setattr(benchmark_http, "build_opener", lambda *args: opener)
    stream = io.BytesIO()
    benchmark_http.transfer("https://example.invalid/SYNTHETIC", stream)
    assert stream.getvalue() == b"SYNTHETIC"
    assert opener.open.call_count == 3
    assert benchmark_http.time.sleep.call_count == 2


def test_https_redirect_and_length_checks(monkeypatch):
    for url in ("http://example.invalid", "https://secret:token@example.invalid"):
        with pytest.raises(BenchmarkError):
            benchmark_http.transfer(url, io.BytesIO())
    with pytest.raises(BenchmarkError):
        benchmark_http.HTTPSRedirect().redirect_request(
            None, None, 302, "", {}, "http://example.invalid"
        )
    opener = Mock()
    opener.open.side_effect = lambda *args, **kwargs: Response(length=999)
    monkeypatch.setattr(benchmark_http, "build_opener", lambda *args: opener)
    with pytest.raises(BenchmarkError, match="exhausted"):
        benchmark_http.transfer("https://example.invalid/SYNTHETIC", io.BytesIO())
    assert opener.open.call_count == 3


def test_downloaded_data_and_manifests_ignored_by_git():
    paths = [
        "data/benchmarks/uit_vsfc/train.parquet",
        "data/benchmarks/uit_vsfc/manifest.json",
        "data/benchmarks/.uit_vsfc-partial/train.parquet",
    ]
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "check-ignore", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == paths
