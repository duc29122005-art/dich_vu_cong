"""Canonical feedback contract; provenance and review evidence stay separate."""

import re
from datetime import datetime

from pydantic import Field, StrictStr, field_validator

from pfa.data.registry import Identifier, Metadata


class Feedback(Metadata):
    feedback_id: StrictStr = Field(min_length=1, max_length=256)
    content: StrictStr = Field(min_length=1)
    created_at: datetime | None
    source_id: Identifier
    domain: StrictStr | None = None
    agency: StrictStr | None = None
    channel: StrictStr | None = None
    processing_status: StrictStr | None = None
    response_date: datetime | None = None

    @field_validator("feedback_id", "content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Required text cannot be blank")
        return value

    @field_validator("created_at", "response_date", mode="before")
    @classmethod
    def timestamp(cls, value: object) -> datetime | None:
        """Accept ISO datetimes and null; never invent a time or timezone."""
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
            raise ValueError("ISO datetime required")
        return datetime.fromisoformat(value)

    @field_validator("domain", "agency", "channel", "processing_status", mode="before")
    @classmethod
    def optional_text(cls, value: object) -> object:
        """CSV blanks represent missing optional values."""
        return None if isinstance(value, str) and not value.strip() else value


class ImportOptions(Metadata):
    max_input_bytes: int = Field(default=20 * 1024**2, gt=0, le=1024**3)
    max_records: int = Field(default=10000, gt=0, le=100000)
    max_text_length: int = Field(default=20000, gt=0, le=100000)
    near_duplicate_threshold: float = Field(default=0.85, gt=0, le=1)
    column_mapping: dict[str, str] = Field(default_factory=dict)
    pii_categories: list[str] = Field(
        default_factory=lambda: [
            "email",
            "phone",
            "citizen_id",
            "personal_identifier",
            "address",
            "personal_name",
        ]
    )

    @field_validator("column_mapping")
    @classmethod
    def mapping(cls, value: dict[str, str]) -> dict[str, str]:
        effective = [value.get(name, name) for name in Feedback.model_fields]
        if (
            not set(value).issubset(Feedback.model_fields)
            or any(not item.strip() for item in value.values())
            or len(set(effective)) != len(effective)
        ):
            raise ValueError("Mapping requires unique input columns and known canonical fields")
        return value

    @field_validator("pii_categories")
    @classmethod
    def categories(cls, value: list[str]) -> list[str]:
        allowed = {
            "email",
            "phone",
            "citizen_id",
            "personal_identifier",
            "address",
            "personal_name",
        }
        if not value or not set(value).issubset(allowed) or len(value) != len(set(value)):
            raise ValueError("Unknown or duplicate PII categories")
        return value
