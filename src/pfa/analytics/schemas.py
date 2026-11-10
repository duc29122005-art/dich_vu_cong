"""Versioned aggregate contracts; no feedback identifiers or text fields."""

import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pfa.annotation.taxonomy import VERSION, Sentiment, Severity, Topic, unique_object
from pfa.data.official_io import safe_path
from pfa.db.contracts import State

NOTICE = "SYNTHETIC DATA — DEMO ONLY"
Basis = Literal["prediction", "reviewed", "adjudicated"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Config(Contract):
    version: Literal["analytics-1"] = "analytics-1"
    timezone: Literal["Asia/Ho_Chi_Minh"] = "Asia/Ho_Chi_Minh"
    small_group: int = Field(default=5, ge=2, le=100)
    max_records: int = Field(default=5000, ge=100, le=20000)
    max_days: int = Field(default=366, ge=8, le=366)
    agencies: list[str] = ["demo_agency_a", "demo_agency_b"]
    domains: list[str] = ["demo_domain_a", "demo_domain_b"]
    baseline_windows: int = Field(default=7, ge=3, le=28)
    baseline_min_count: int = Field(default=10, ge=5)
    current_min_count: int = Field(default=20, ge=5)
    max_missing_date_share: float = Field(default=0.1, ge=0, le=1)
    max_missing_label_share: float = Field(default=0.1, ge=0, le=1)
    volume_ratio: float = Field(default=2.0, ge=1.5)
    volume_sigma: float = Field(default=3.0, ge=2)
    share_increase: float = Field(default=0.2, ge=0.1, le=1)
    topic_increase: float = Field(default=0.25, ge=0.1, le=1)


def load_config(root: Path):
    path = safe_path(root / "configs/analytics_v1.yaml", root)
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("Analytics configuration missing or oversized")
    return Config.model_validate(
        json.loads(path.read_text("utf-8"), object_pairs_hook=unique_object)
    )


class Filters(Contract):
    start: date | None = None
    end: date | None = None
    interval: Literal["day", "week", "month"] = "day"
    basis: Basis = "prediction"
    source_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    agency: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    domain: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    topic: Topic | None = None
    sentiment: Sentiment | None = None
    severity: Severity | Literal["unknown"] | None = None
    review_status: State | None = None
    model_family: Literal["mock", "lr", "svm", "phobert"] | None = None
    model_version: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    model_task: Literal["topic", "sentiment", "severity"] = "topic"

    @field_validator("start", "end", mode="before")
    @classmethod
    def date_only(cls, value):
        if (
            value is not None
            and isinstance(value, str)
            and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        ):
            raise ValueError("ISO calendar date required")
        return value

    @model_validator(mode="after")
    def dates(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("Both start and end dates are required")
        if self.start and (self.end < self.start or (self.end - self.start).days >= 366):
            raise ValueError("Ordered date range of at most 366 days required")
        if self.start and not (1900 <= self.start.year <= self.end.year <= 2100):
            raise ValueError("Supported calendar years are 1900 through 2100")
        return self


class Metric(Contract):
    numerator: int | None
    denominator: int | None
    share: float | None
    suppressed: bool = False


class Cell(Contract):
    code: str
    count: int | None
    share: float | None = None
    suppressed: bool = False


class Bucket(Contract):
    start: date
    end_exclusive: date
    count: int | None
    negative: Metric
    high_severity: Metric
    complete_calendar_window: bool
    observation_coverage: Literal["UNKNOWN"] = "UNKNOWN"
    suppressed: bool = False


class Alert(Contract):
    rule: Literal["volume", "high_severity_share", "topic_concentration"]
    status: Literal["TRIGGERED", "NORMAL", "SUPPRESSED", "INSUFFICIENT_DATA"]
    reason: str
    observed: float | None = None
    baseline: float | None = None
    topic: Topic | None = None
    processing_mode: Literal["DEMO_ONLY"] = "DEMO_ONLY"
    window_start: date | None = None
    window_end_exclusive: date | None = None
    baseline_start: date | None = None
    baseline_end_exclusive: date | None = None


class ModelInfo(Contract):
    task: Literal["topic", "sentiment", "severity"]
    family: Literal["mock", "lr", "svm", "phobert"]
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    status: Literal["DEMO_ONLY"] = "DEMO_ONLY"


class Report(Contract):
    schema_version: Literal["analytics-schema-1"] = "analytics-schema-1"
    config_version: Literal["analytics-1"] = "analytics-1"
    config_checksum: str
    processing_mode: Literal["DEMO_ONLY"] = "DEMO_ONLY"
    notice: Literal[NOTICE] = NOTICE
    taxonomy_version: Literal[VERSION] = VERSION
    timezone: Literal["Asia/Ho_Chi_Minh"] = "Asia/Ho_Chi_Minh"
    status: Literal["AVAILABLE", "EMPTY", "SUPPRESSED"]
    filters: Filters
    total: int | None
    small_group: int
    metrics: dict[str, Metric] = Field(default_factory=dict)
    distributions: dict[str, list[Cell]] = Field(default_factory=dict)
    cross_tab: list[Cell] = Field(default_factory=list)
    top_complaint_topic: Topic | None = None
    buckets: list[Bucket] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    models: list[ModelInfo] = Field(default_factory=list)
    warnings: list[str] = Field(
        default_factory=lambda: [
            "SYNTHETIC_STATISTICS_NOT_RESEARCH_RESULTS",
            "SELF_SELECTED_FEEDBACK_NOT_POPULATION_SATISFACTION",
            "EXPOSURE_AND_REPORTING_COMPLETENESS_UNKNOWN",
            "NO_SEASONAL_ADJUSTMENT",
            "SMALL_CELL_SUPPRESSION_IS_NOT_DIFFERENTIAL_PRIVACY",
        ]
    )
