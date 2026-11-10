"""UIT-VSFC validation, preserving Vietnamese text and original numeric labels."""

import json
from collections.abc import Iterator, Mapping
from pathlib import Path

SPLITS = ("train", "validation", "test")
LABELS = {
    "sentiment": {"0": "negative", "1": "neutral", "2": "positive"},
    "topic": {"0": "lecturer", "1": "training_program", "2": "facility", "3": "others"},
}
ADAPTER_VERSION = "1"


class BenchmarkError(ValueError):
    """Diagnostics must never contain row text or raw remote responses."""


def validate_row(row: Mapping[str, object], index: int = 0) -> None:
    """Reject invalid rows; retain original values without label remapping."""
    if set(row) != {"sentence", "sentiment", "topic"}:
        raise BenchmarkError("Schema mismatch: require sentence, sentiment, topic only")
    text = row["sentence"]
    if not isinstance(text, str) or not text.strip():
        raise BenchmarkError(f"Row {index}: sentence must be nonempty text")
    try:
        text.encode("utf-8")
    except UnicodeError:
        raise BenchmarkError(f"Row {index}: sentence is not valid UTF-8") from None
    for field in LABELS:
        label = row[field]
        if type(label) is not int or str(label) not in LABELS[field]:
            raise BenchmarkError(f"Row {index}: invalid {field} label ID")


def label_status(features: object) -> dict[str, str]:
    """Compare available source ClassLabel names with the unverified reference."""
    result = dict.fromkeys(LABELS, "UNVERIFIED")
    if isinstance(features, list):
        features = {
            item.get("name"): item.get("dtype") for item in features if isinstance(item, dict)
        }
    if not isinstance(features, dict):
        return result
    for field, expected in LABELS.items():
        feature = features.get(field, {})
        if not isinstance(feature, dict):
            continue
        feature = feature.get("class_label", feature)
        if not isinstance(feature, dict):
            continue
        names = feature.get("names")
        if names is None:
            continue
        actual = dict(enumerate(names)) if isinstance(names, list) else names
        if (
            not isinstance(actual, dict)
            or {str(key): value for key, value in actual.items()} != expected
        ):
            raise BenchmarkError(f"Source metadata conflicts with expected {field} mapping")
        result[field] = "VERIFIED_SOURCE_METADATA"
    return result


def parquet_rows(path: Path, split: str) -> Iterator[dict[str, object]]:
    """Read at most 1024 rows per batch; never drop malformed records."""
    if split not in SPLITS:
        raise BenchmarkError("Unknown split; expected train, validation, or test")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise BenchmarkError("Parquet support missing; install the data extra (PyArrow)") from None
    if not path.is_file() or path.is_symlink():
        raise BenchmarkError("Parquet file missing or unsafe")
    try:
        with path.open("rb") as stream, pq.ParquetFile(stream) as parquet:
            schema = parquet.schema_arrow
            if set(schema.names) != {"sentence", "sentiment", "topic"} or len(schema) != 3:
                raise BenchmarkError("Parquet schema mismatch: sentence, sentiment, topic required")
            if not (
                pa.types.is_string(schema.field("sentence").type)
                or pa.types.is_large_string(schema.field("sentence").type)
            ):
                raise BenchmarkError("Parquet sentence column must be string")
            if any(not pa.types.is_integer(schema.field(field).type) for field in LABELS):
                raise BenchmarkError("Parquet sentiment/topic columns must be integers")
            index = 0
            for batch in parquet.iter_batches(batch_size=1024):
                for row in batch.to_pylist():
                    validate_row(row, index)
                    index += 1
                    yield row
    except BenchmarkError:
        raise
    except (OSError, ValueError, pa.ArrowException):
        raise BenchmarkError("Unreadable or corrupted Parquet data") from None


def summarize_parquet(path: Path, split: str) -> dict:
    """Return actual counts, physical schema, and available mapping evidence."""
    count = sum(1 for _ in parquet_rows(path, split))
    import pyarrow.parquet as pq

    with path.open("rb") as stream, pq.ParquetFile(stream) as parquet:
        schema = parquet.schema_arrow
        try:
            metadata = json.loads((schema.metadata or {}).get(b"huggingface", b"{}"))
            features = metadata.get("info", {}).get("features", {})
        except (ValueError, AttributeError):
            raise BenchmarkError("Invalid embedded source label metadata") from None
        return {
            "row_count": count,
            "schema": {field.name: str(field.type) for field in schema},
            "label_status": label_status(features),
        }
