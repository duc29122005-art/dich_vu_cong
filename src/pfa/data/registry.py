"""Offline source metadata. Registry files use the JSON subset of YAML 1.2."""

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
Identifier = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*$")]
Scope = Literal["software_tests", "training", "internal_analysis", "publication"]
PermissionState = Literal["UNKNOWN", "PENDING", "APPROVED", "DENIED", "REVOKED"]
Role = Literal["BENCHMARK", "PRIMARY_CANDIDATE", "AUXILIARY", "REFERENCE", "AGGREGATE", "SYNTHETIC"]


class Metadata(BaseModel):
    """Reject typos and type coercion at the metadata boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Source(Metadata):
    source_id: Identifier
    source_name: Text
    source_url: Text
    description: Text
    domain_fit: Literal["DIRECT", "ADJACENT", "INDIRECT", "SYNTHETIC", "UNKNOWN"]
    dataset_role: Role
    available_tasks: list[Text] = Field(min_length=1)
    expected_schema: dict[Text, Text] = Field(min_length=1)
    license_status: Literal["UNKNOWN", "VERIFIED", "RESTRICTED"]
    permission_status: PermissionState
    allowed_processing: list[Scope]
    allowed_training: bool
    allowed_publication: bool
    pii_risk: Literal["UNKNOWN", "HIGH", "LOW", "NONE"]
    access_method: Text
    coverage: Text
    last_verified: Text
    source_owner: Text
    evidence_references: list[Text]
    retention_policy: Text

    @model_validator(mode="after")
    def consistency(self) -> "Source":
        """Registry declarations never substitute for permission decisions."""
        if self.source_url != "UNKNOWN" and not self.source_url.startswith("https://"):
            raise ValueError("source_url must be HTTPS or UNKNOWN")
        if self.last_verified != "UNKNOWN":
            date.fromisoformat(self.last_verified)
        if self.permission_status == "APPROVED":
            if self.license_status != "VERIFIED" or not self.evidence_references:
                raise ValueError("APPROVED requires verified license and approval evidence")
        elif self.allowed_processing or self.allowed_training or self.allowed_publication:
            raise ValueError("Unapproved sources cannot declare allowed usage")
        if self.allowed_training != ("training" in self.allowed_processing):
            raise ValueError("allowed_training must match allowed_processing")
        if self.allowed_publication != ("publication" in self.allowed_processing):
            raise ValueError("allowed_publication must match allowed_processing")
        if self.license_status == "VERIFIED" and not self.evidence_references:
            raise ValueError("Verified license requires evidence")
        return self


class Registry(Metadata):
    sources: list[Source] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> "Registry":
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate source IDs")
        return self

    def source(self, source_id: str) -> Source:
        """Resolve an exact identifier without interpreting it as a path."""
        for source in self.sources:
            if source.source_id == source_id:
                return source
        raise ValueError("Unknown source ID")


def load_registry(path: Path) -> Registry:
    """Read JSON-compatible YAML without executing YAML constructors."""
    return Registry.model_validate(json.loads(path.read_text(encoding="utf-8")))
