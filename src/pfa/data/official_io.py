"""Streaming local readers and protected, atomic storage helpers."""

import csv
import io
import json
import os
import stat
import subprocess
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

from pfa.data.official_schema import Feedback, ImportOptions


class IngestionError(ValueError):
    """Static safe diagnostics only; never include input paths or content."""


class IngestionBlocked(PermissionError):
    """Static permission or human-review gate failure."""


def safe_path(path: Path, boundary: Path | None = None) -> Path:
    """Reject symlinks/junctions in every existing component and path escapes."""
    absolute = Path(os.path.abspath(path))
    for part in (absolute, *absolute.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise IngestionError("Unsafe symlink or reparse point")
    if boundary is not None and not absolute.resolve().is_relative_to(boundary.resolve()):
        raise IngestionError("Path must stay inside its authorized storage boundary")
    return absolute


@lru_cache(maxsize=1)
def windows_sid() -> str:
    """Resolve the executing Windows account without trusting environment variables."""
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=False
    )
    try:
        sid = next(csv.reader([result.stdout.strip()]))[1]
    except (IndexError, StopIteration):
        raise IngestionError("Cannot determine storage owner SID") from None
    if result.returncode or not sid.startswith("S-1-"):
        raise IngestionError("Cannot determine storage owner SID")
    return sid


def protect_directory(path: Path) -> str:
    """Restrict an application-created empty directory before writing sensitive data."""
    if os.name == "nt":
        result = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{windows_sid()}:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise IngestionError("Unable to apply restricted Windows storage ACL")
        return "WINDOWS_OWNER_SYSTEM_ACL"
    path.chmod(0o700)
    return "POSIX_0700_0600"


def write_json(path: Path, value: object) -> None:
    """Write inside a protected temporary directory; caller publishes atomically."""
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        if os.name != "nt":
            path.chmod(0o600)
        json.dump(value, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


class BoundedReader(io.RawIOBase):
    """Bound reads even if another process grows the input file after stat()."""

    def __init__(self, stream: BinaryIO, limit: int) -> None:
        self.stream = stream
        self.remaining = limit

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray) -> int:
        data = self.stream.read(min(len(buffer), self.remaining + 1))
        if len(data) > self.remaining:
            raise IngestionError("Input exceeds configured maximum size")
        self.remaining -= len(data)
        buffer[: len(data)] = data
        return len(data)


def rows(
    stream: BinaryIO, suffix: str, options: ImportOptions
) -> Iterator[tuple[int, dict | None]]:
    """Yield an ordinal and object, or None for recoverable malformed records."""
    buffered = io.BufferedReader(BoundedReader(stream, options.max_input_bytes))
    text = io.TextIOWrapper(buffered, encoding="utf-8-sig", errors="strict", newline="")
    required = {name for name, field in Feedback.model_fields.items() if field.is_required()}
    mapping = {name: options.column_mapping.get(name, name) for name in Feedback.model_fields}

    def canonical(record: dict) -> dict:
        return {name: record[column] for name, column in mapping.items() if column in record}

    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON keys")
            result[key] = value
        return result

    try:
        if suffix == ".csv":
            reader = csv.DictReader(text, strict=True)
            names = reader.fieldnames or []
            if len(names) != len(set(names)) or not {mapping[name] for name in required} <= set(
                names
            ):
                raise IngestionError("CSV required columns missing or duplicated")
            for index, record in enumerate(reader, 1):
                yield (
                    index,
                    None if None in record or None in record.values() else canonical(record),
                )
        elif suffix == ".jsonl":
            for index, line in enumerate(text, 1):
                try:
                    record = json.loads(line, object_pairs_hook=unique_object)
                except ValueError:
                    yield index, None
                    continue
                yield index, canonical(record) if isinstance(record, dict) else None
        else:
            raise IngestionError("Unsupported input format; only UTF-8 CSV and JSONL are supported")
    except UnicodeError:
        raise IngestionError("Input encoding is invalid; UTF-8 required") from None
    except csv.Error:
        raise IngestionError("Malformed CSV cannot be safely resynchronized") from None
    finally:
        text.close()  # BoundedReader does not own the caller's binary handle.
