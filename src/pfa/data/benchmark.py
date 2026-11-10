"""Permission-gated UIT-VSFC discovery, installation, and local integrity checks."""

import hashlib
import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal
from urllib.parse import quote

from pydantic import Field, model_validator

from pfa.data.adapters.uit_vsfc import (
    ADAPTER_VERSION,
    LABELS,
    SPLITS,
    BenchmarkError,
    label_status,
    summarize_parquet,
)
from pfa.data.benchmark_http import transfer, validate_https
from pfa.data.permissions import Decision, current_decision, require_access
from pfa.data.registry import Identifier, Metadata, Registry, Text

REPOSITORY = "uitnlp/vietnamese_students_feedback"
SOURCE_URL = "https://huggingface.co/datasets/" + REPOSITORY
DEFAULT_REVISION = "refs/convert/parquet"


class BenchmarkPermissionError(PermissionError):
    """Only static, non-sensitive permission diagnostics may be emitted."""


def authorize(root: Path, registry: Registry, approval_ref: str) -> Decision:
    """A reviewed registry and a matching effective scope are both required."""
    source = registry.source("uit_vsfc")
    try:
        require_access(root, registry, "uit_vsfc", "internal_analysis")
        decision = current_decision(root, registry, "uit_vsfc")
    except (ValueError, OSError):
        raise BenchmarkPermissionError(
            "BLOCKED_PERMISSION: matching audited internal_analysis approval required; "
            "review evidence, revocation, and audit consistency"
        ) from None
    if decision is None or decision.approval_ref != approval_ref:
        raise BenchmarkPermissionError("BLOCKED_PERMISSION: approval reference is not current")
    if source.permission_status != "APPROVED" or source.license_status != "VERIFIED":
        raise BenchmarkPermissionError(
            "BLOCKED_PERMISSION: registry permission and license remain unresolved; "
            "human review required"
        )
    if source.source_url != SOURCE_URL or source.dataset_role != "BENCHMARK":
        raise BenchmarkError("UIT-VSFC registry URL or benchmark role does not match the adapter")
    return decision


def inspect_local(root: Path, registry: Registry) -> dict:
    """Inspect expectations only; no network and no sample counts are invented."""
    source = registry.source("uit_vsfc")
    return {
        "source_id": source.source_id,
        "source_url": source.source_url,
        "dataset_role": source.dataset_role,
        "permission_status": source.permission_status,
        "license_status": source.license_status,
        "expected_fields": {
            "sentence": "UTF-8 string",
            "sentiment": "integer 0..2",
            "topic": "integer 0..3",
        },
        "expected_splits": list(SPLITS),
        "reference_label_mapping": LABELS,
        "label_mapping_status": "UNVERIFIED: official metadata has not been inspected",
        "verified_fields": [],
        "expected_row_counts": "UNKNOWN",
        "actual_row_counts": None,
        "local_manifest_present": (root / "data/benchmarks/uit_vsfc/manifest.json").is_file(),
        "notice": "Student feedback; never map education topics to public-service labels.",
    }


def discover(
    root: Path, registry: Registry, approval_ref: str, revision: str = DEFAULT_REVISION
) -> dict:
    """Resolve a revision once and discover Parquet paths from repository metadata."""
    authorize(root, registry, approval_ref)
    if not revision or len(revision) > 200:
        raise BenchmarkError("Invalid requested revision")
    metadata_url = (
        f"https://huggingface.co/api/datasets/{REPOSITORY}/revision/{quote(revision, safe='')}"
        "?blobs=true"
    )
    stream = io.BytesIO()
    transfer(metadata_url, stream, limit=4 * 1024**2)
    try:
        metadata = json.loads(stream.getvalue())
        resolved = metadata["sha"]
        if metadata["id"] != REPOSITORY or not re.fullmatch(r"[a-f0-9]{40}", resolved):
            raise ValueError
        if re.fullmatch(r"[a-f0-9]{40}", revision) and revision != resolved:
            raise BenchmarkError("Resolved revision does not match the requested pinned commit")
        files = []
        configurations = set()
        for item in metadata["siblings"]:
            name = item["rfilename"]
            if not name.endswith(".parquet"):
                continue
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name:
                raise ValueError
            matches = list(re.finditer(r"(?:^|/)(train|validation|test)(?=[/.-])", name))
            if len(matches) != 1:
                raise BenchmarkError("Discovered Parquet path has unknown or ambiguous split")
            configurations.add(name[: matches[0].start()].rstrip("/"))
            files.append(
                {
                    "split": matches[0].group(1),
                    "repository_path": name,
                    "url": f"{SOURCE_URL}/resolve/{resolved}/{quote(name, safe='/')}",
                }
            )
        if {item["split"] for item in files} != set(SPLITS):
            raise BenchmarkError("Pinned repository metadata must expose all three Parquet splits")
        if len({item["repository_path"] for item in files}) != len(files):
            raise ValueError
        # Different configurations must not be silently merged into one benchmark.
        if len(configurations) != 1:
            raise BenchmarkError("Multiple Parquet configurations require explicit adapter review")
        card = metadata.get("cardData") or {}
        info = card.get("dataset_info") or {}
        if isinstance(info, list):
            info = info[0] if len(info) == 1 else {}
        status = label_status(info.get("features", {}))
    except BenchmarkError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError):
        raise BenchmarkError("Repository metadata is invalid or incomplete") from None
    return {
        "source_repository": REPOSITORY,
        "requested_revision": revision,
        "dataset_revision": resolved,
        "metadata_url": metadata_url,
        "files": sorted(files, key=lambda item: item["repository_path"]),
        "verified_fields": ["repository", "resolved_revision", "Parquet paths"],
        "label_status": status,
        "metadata_features": {
            field: {"names": list(LABELS[field].values())}
            for field in LABELS
            if status[field] == "VERIFIED_SOURCE_METADATA"
        },
        "actual_row_counts": None,
        "download_status": "NOT_DOWNLOADED",
    }


class FileRecord(Metadata):
    path: Text
    split: Literal["train", "validation", "test"]
    file_url: Text
    sha256: Text
    size_bytes: int = Field(gt=0)
    row_count: int = Field(ge=0)

    @model_validator(mode="after")
    def safe_file(self) -> "FileRecord":
        if not re.fullmatch(r"[a-z0-9_-]+\.parquet", self.path):
            raise ValueError("Manifest file name must be a safe Parquet basename")
        if not re.fullmatch(r"[a-f0-9]{64}", self.sha256):
            raise ValueError("Invalid SHA256")
        validate_https(self.file_url)
        return self


class Manifest(Metadata):
    source_id: Literal["uit_vsfc", "synthetic_fixture"]
    source_url: Text
    dataset_role: Literal["BENCHMARK"]
    dataset_revision: Text
    approval_reference: Identifier | None
    download_timestamp: Text
    files: list[FileRecord] = Field(min_length=1)
    physical_schema: dict[str, str] = Field(alias="schema")
    split_names: list[str]
    row_counts: dict[str, int]
    label_mapping: dict[str, dict[str, str]]
    label_mapping_status: dict[str, str]
    metadata_features: dict
    data_provenance: Literal["REAL_EXTERNAL", "SYNTHETIC"]
    source_repository: Text
    metadata_url: Text
    adapter_version: Literal[ADAPTER_VERSION]

    @model_validator(mode="after")
    def consistent(self) -> "Manifest":
        if set(self.split_names) != set(SPLITS) or len(self.split_names) != 3:
            raise ValueError("Manifest must describe exactly three splits")
        if set(self.row_counts) != set(SPLITS) or any(
            value <= 0 for value in self.row_counts.values()
        ):
            raise ValueError("Manifest requires positive actual row counts per split")
        if len({item.path for item in self.files}) != len(self.files):
            raise ValueError("Duplicate manifest file names")
        if set(self.physical_schema) != {"sentence", "sentiment", "topic"}:
            raise ValueError("Manifest schema mismatch")
        if self.label_mapping != LABELS:
            raise ValueError("Manifest reference label mapping mismatch")
        when = datetime.fromisoformat(self.download_timestamp)
        if when.tzinfo is None:
            raise ValueError("Manifest timestamp must include a timezone")
        if self.data_provenance == "REAL_EXTERNAL":
            validate_https(self.metadata_url)
            if (
                self.source_id != "uit_vsfc"
                or self.source_url != SOURCE_URL
                or self.source_repository != REPOSITORY
                or not self.approval_reference
                or not re.fullmatch(r"[a-f0-9]{40}", self.dataset_revision)
            ):
                raise ValueError("Real manifest provenance is incomplete")
            expected = f"{SOURCE_URL}/resolve/{self.dataset_revision}/"
            if any(not item.file_url.startswith(expected) for item in self.files):
                raise ValueError("File URL is not pinned to the manifest revision")
        elif (
            self.source_id != "synthetic_fixture"
            or self.dataset_revision != "SYNTHETIC"
            or self.approval_reference is not None
        ):
            raise ValueError("Synthetic fixtures must never impersonate real benchmark data")
        return self


def checksum(path: Path) -> str:
    """Hash in bounded chunks."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_directory(directory: Path) -> dict:
    """Check local integrity, not legal authorization; synthetic provenance stays explicit."""
    path = directory / "manifest.json"
    if directory.is_symlink() or path.is_symlink() or not path.is_file():
        raise BenchmarkError("NOT_AVAILABLE: local dataset manifest is missing or unsafe")
    manifest = Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    actual_files = {item.name for item in directory.iterdir() if item.name != "manifest.json"}
    if actual_files != {item.path for item in manifest.files}:
        raise BenchmarkError("Manifest file inventory mismatch")
    counts = dict.fromkeys(SPLITS, 0)
    status = label_status(manifest.metadata_features)
    for record in manifest.files:
        file = directory / record.path
        if file.is_symlink() or not file.is_file():
            raise BenchmarkError("Manifest Parquet file missing or unsafe")
        if file.stat().st_size != record.size_bytes or checksum(file) != record.sha256:
            raise BenchmarkError("Parquet checksum or file size mismatch")
        summary = summarize_parquet(file, record.split)
        if (
            summary["row_count"] != record.row_count
            or summary["schema"] != manifest.physical_schema
        ):
            raise BenchmarkError("Actual Parquet rows/schema disagree with manifest")
        counts[record.split] += summary["row_count"]
        status.update(
            {
                field: value
                for field, value in summary["label_status"].items()
                if value == "VERIFIED_SOURCE_METADATA"
            }
        )
    if manifest.data_provenance == "SYNTHETIC":
        status = dict.fromkeys(LABELS, "UNVERIFIED")
    if counts != manifest.row_counts or status != manifest.label_mapping_status:
        raise BenchmarkError("Manifest row counts or label evidence inconsistent")
    return {
        "status": "VERIFIED_SYNTHETIC" if manifest.data_provenance == "SYNTHETIC" else "VERIFIED",
        "data_provenance": manifest.data_provenance,
        "row_counts": counts,
        "label_mapping_status": status,
        "notice": "Integrity check only; no permission or training authorization is granted.",
    }


def verify_local(root: Path, registry: Registry) -> dict:
    """Preserve synthetic provenance; require current permission for real local samples."""
    directory = root / "data/benchmarks/uit_vsfc"
    path = directory / "manifest.json"
    if (
        directory.is_symlink()
        or path.is_symlink()
        or not directory.resolve().is_relative_to(root.resolve())
    ):
        raise BenchmarkError("Unsafe local benchmark location")
    if not path.is_file():
        raise BenchmarkError("NOT_AVAILABLE: no local benchmark manifest; nothing was downloaded")
    manifest = Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if manifest.data_provenance == "REAL_EXTERNAL":
        authorize(root, registry, manifest.approval_reference)
    return verify_directory(directory)


def fetch(
    root: Path, registry: Registry, approval_ref: str, revision: str = DEFAULT_REVISION
) -> dict:
    """Stage and validate every shard, then atomically publish one complete directory."""
    authorize(root, registry, approval_ref)
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        raise BenchmarkError("Parquet support missing; install the data extra (PyArrow)") from None
    parent = root / "data/benchmarks"
    if not parent.resolve().is_relative_to(root.resolve()):
        raise BenchmarkError("Benchmark storage must remain within the project")
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / "uit_vsfc"
    if destination.exists() or destination.is_symlink():
        raise BenchmarkError("Dataset destination exists; verify it instead of overwriting")
    lock = parent / ".uit_vsfc-fetch.lock"
    lock_stream = lock.open("x")
    try:
        with lock_stream, TemporaryDirectory(prefix=".uit_vsfc-", dir=parent) as temporary:
            stage = Path(temporary)
            metadata = discover(root, registry, approval_ref, revision)
            files = []
            counts = dict.fromkeys(SPLITS, 0)
            schema = None
            status = metadata["label_status"].copy()
            for index, item in enumerate(metadata["files"]):
                authorize(root, registry, approval_ref)
                name = f"{item['split']}-{index:04d}.parquet"
                file = stage / name
                with file.open("w+b") as stream:
                    transfer(item["url"], stream)
                summary = summarize_parquet(file, item["split"])
                if schema is not None and schema != summary["schema"]:
                    raise BenchmarkError("Parquet shards have inconsistent schemas")
                schema = summary["schema"]
                counts[item["split"]] += summary["row_count"]
                status.update(
                    {
                        field: value
                        for field, value in summary["label_status"].items()
                        if value == "VERIFIED_SOURCE_METADATA"
                    }
                )
                files.append(
                    {
                        "path": name,
                        "split": item["split"],
                        "file_url": item["url"],
                        "sha256": checksum(file),
                        "size_bytes": file.stat().st_size,
                        "row_count": summary["row_count"],
                    }
                )
            payload = {
                "source_id": "uit_vsfc",
                "source_url": SOURCE_URL,
                "dataset_role": "BENCHMARK",
                "dataset_revision": metadata["dataset_revision"],
                "approval_reference": approval_ref,
                "download_timestamp": datetime.now(UTC).isoformat(),
                "files": files,
                "schema": schema,
                "split_names": list(SPLITS),
                "row_counts": counts,
                "label_mapping": LABELS,
                "label_mapping_status": status,
                "metadata_features": metadata["metadata_features"],
                "data_provenance": "REAL_EXTERNAL",
                "source_repository": REPOSITORY,
                "metadata_url": metadata["metadata_url"],
                "adapter_version": ADAPTER_VERSION,
            }
            manifest = Manifest.model_validate(payload)
            (stage / "manifest.json").write_text(
                manifest.model_dump_json(by_alias=True, indent=2), encoding="utf-8"
            )
            result = verify_directory(stage)
            authorize(root, registry, approval_ref)
            if destination.exists() or destination.is_symlink():
                raise BenchmarkError("Dataset destination appeared; refusing overwrite")
            stage.rename(destination)
            return result
    finally:
        lock.unlink()
