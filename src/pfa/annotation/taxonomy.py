"""Immutable proposed v1 taxonomy, using the project's JSON-compatible YAML convention."""

import hashlib
import json
from pathlib import Path
from typing import Literal, get_args

from pydantic import Field, model_validator

from pfa.data.official_io import IngestionError, safe_path
from pfa.data.registry import Identifier, Metadata, Text

VERSION = "1.0.0"
CHECKSUM = "500a61fd8f8fe49d31f3ec7eca955ebfe1856bb235e04ffc62d6f44f16f5af02"
Topic = Literal[
    "delayed_processing",
    "complex_procedure",
    "unclear_guidance",
    "online_system_error",
    "staff_attitude",
    "fees",
    "unsatisfactory_result",
    "other",
]
Sentiment = Literal["negative", "neutral", "positive"]
Severity = Literal["low", "medium", "high"]
Status = Literal["DRAFT", "SUBMITTED", "REQUIRES_REVIEW", "OUT_OF_SCOPE", "UNLABELABLE"]


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate JSON keys rather than silently changing human input."""
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate object keys")
        result[name] = value
    return result


class Label(Metadata):
    code: Identifier
    name_vi: Text
    definition: Text


class Task(Metadata):
    task_id: Literal["topic", "sentiment", "severity"]
    single_label: bool
    workflow_states: list[Text]
    labels: list[Label]


class Taxonomy(Metadata):
    version: Literal[VERSION]
    instrument_status: Literal["PROPOSED_PENDING_HUMAN_APPROVAL"]
    primary_topic_rule: Text
    tie_breaking: list[Text] = Field(min_length=1)
    tasks: list[Task]

    @model_validator(mode="after")
    def stable_labels(self) -> "Taxonomy":
        expected = [get_args(Topic), get_args(Sentiment), get_args(Severity)]
        if [task.task_id for task in self.tasks] != ["topic", "sentiment", "severity"]:
            raise ValueError("Expected three ordered, independent tasks")
        states = [["OUT_OF_SCOPE", "UNLABELABLE"], ["REQUIRES_REVIEW"], ["unknown"]]
        for task, codes, workflow in zip(self.tasks, expected, states, strict=True):
            if task.single_label is not True:
                raise ValueError("All tasks require a single supervised label")
            if (
                tuple(label.code for label in task.labels) != codes
                or task.workflow_states != workflow
            ):
                raise ValueError("Stable supervised labels and separate workflow states required")
        return self


def checksum(value: Taxonomy) -> str:
    """Canonical UTF-8 JSON: mapping order/whitespace ignored, label list order preserved."""
    return hashlib.sha256(
        json.dumps(
            value.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def load_taxonomy(root: Path) -> Taxonomy:
    """Reject edits to the frozen meaning/order/version of the proposed instrument."""
    path = safe_path(root / "configs/taxonomy_v1.yaml", root)
    if not path.is_file() or path.stat().st_size > 65536:
        raise IngestionError("Taxonomy file missing or oversized")
    try:
        value = Taxonomy.model_validate(
            json.loads(path.read_text("utf-8"), object_pairs_hook=unique_object)
        )
    except (ValueError, UnicodeError):
        raise IngestionError("Invalid taxonomy schema") from None
    if checksum(value) != CHECKSUM:
        raise IngestionError("Taxonomy integrity failure: immutable v1 definition changed")
    return value
