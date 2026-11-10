"""Protected immutable local bundles. Trusted coordinator controls requests and audit history."""

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from pfa.annotation.taxonomy import unique_object
from pfa.data.official import file_digest
from pfa.data.official_io import (
    IngestionBlocked,
    IngestionError,
    protect_directory,
    safe_path,
    write_json,
)

_SYNTHETIC_ROOTS: set[Path] = set()


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,79}", value):
        raise IngestionError("Invalid pilot, actor or decision identifier")
    return value


def base(root: Path) -> Path:
    return safe_path(root / "data/private/annotation_pilots", root)


def private_directory(path: Path) -> None:
    """Restrict each newly created application directory before storing artifacts."""
    if path.exists():
        if not path.is_dir():
            raise IngestionError("Storage directory unavailable")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()
    protect_directory(path)


def read_json(path: Path, limit: int = 20 * 1024**2) -> object:
    path = safe_path(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise IngestionError("NOT_AVAILABLE: required bounded artifact is missing")
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise IngestionError("Artifact exceeds size limit")
    try:
        return json.loads(payload, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError):
        raise IngestionError("Invalid JSON artifact") from None


def file_checksum(path: Path, limit: int = 20 * 1024**2) -> str:
    """Bound checksum reads even if an untrusted submission grows during validation."""
    checksum, size = hashlib.sha256(), 0
    with safe_path(path).open("rb") as stream:
        while block := stream.read(65536):
            size += len(block)
            if size > limit:
                raise IngestionError("Submission exceeds checksum size limit")
            checksum.update(block)
    return checksum.hexdigest()


def publish(path: Path, documents: dict[str, object]) -> str:
    """Atomic directory publication under a local exclusive writer lock; never overwrite."""
    path = safe_path(path)
    private_directory(path.parent)
    lock = safe_path(path.parent / ".writer.lock")
    try:
        handle = lock.open("x")
    except FileExistsError:
        raise IngestionError("Storage writer busy; retry after reviewing the lock") from None
    try:
        with handle:
            if path.exists():
                raise IngestionError(
                    "Immutable artifact already exists; use an explicit new version"
                )
            with TemporaryDirectory(prefix=".pilot-", dir=path.parent) as temporary:
                work = Path(temporary)
                protect_directory(work)
                for name, value in documents.items():
                    if not re.fullmatch(r"[a-z_]+\.json", name) or name == "integrity.json":
                        raise IngestionError("Invalid artifact filename")
                    write_json(work / name, value)
                    if (work / name).stat().st_size > 20 * 1024**2:
                        raise IngestionError("Pilot artifact exceeds 20 MiB limit")
                inventory = {name: file_digest(work / name) for name in sorted(documents)}
                write_json(work / "integrity.json", inventory)
                work.rename(path)
        return digest(inventory)
    finally:
        lock.unlink()


def bundle(path: Path) -> tuple[dict[str, object], str]:
    path = safe_path(path)
    inventory = read_json(path / "integrity.json", 65536)
    if not isinstance(inventory, dict) or not inventory:
        raise IngestionError("Invalid bundle integrity inventory")
    if {item.name for item in path.iterdir()} != {*inventory, "integrity.json"}:
        raise IngestionError("Bundle inventory mismatch")
    documents = {}
    for name, checksum in inventory.items():
        if not re.fullmatch(r"[a-z_]+\.json", name) or name == "integrity.json":
            raise IngestionError("Invalid artifact inventory filename")
        file = safe_path(path / name, path)
        if file_digest(file) != checksum:
            raise IngestionError("Bundle checksum mismatch")
        documents[name] = read_json(file)
    return documents, digest(inventory)


@contextmanager
def synthetic_session(root: Path) -> Iterator[None]:
    """Internal temporary smoke/test capability; no CLI flag or on-disk bypass marker."""
    resolved = root.resolve()
    if resolved in _SYNTHETIC_ROOTS:
        raise IngestionError("Nested synthetic session")
    _SYNTHETIC_ROOTS.add(resolved)
    try:
        yield
    finally:
        _SYNTHETIC_ROOTS.remove(resolved)


def is_synthetic(root: Path) -> bool:
    return root.resolve() in _SYNTHETIC_ROOTS


def require_synthetic(root: Path) -> None:
    if not is_synthetic(root):
        raise IngestionBlocked(
            "Synthetic artifacts cannot be promoted or opened as research pilots"
        )
