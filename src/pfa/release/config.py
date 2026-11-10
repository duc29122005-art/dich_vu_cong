"""Strict release contracts; no production or approved-model switch."""

from typing import Literal

from pydantic import Field

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import VERSION, load_taxonomy
from pfa.api.schemas import API_VERSION, SCHEMA_VERSION
from pfa.data.registry import Metadata
from pfa.research.protocol import load as research_protocol


class Release(Metadata):
    version: Literal["release-1"]
    release_id: Literal["pfa-0.1.0-technical-demo-1"]
    project_version: Literal["0.1.0"]
    classification: Literal["TECHNICAL_DEMO_ONLY"]
    python: Literal["3.11"]
    api_version: Literal[API_VERSION]
    api_schema: Literal[SCHEMA_VERSION]
    taxonomy_version: Literal[VERSION]
    taxonomy_reference: Literal["configs/taxonomy_v1.yaml"]
    research_protocol_reference: Literal["configs/research_protocol_v1.yaml"]
    fixture_version: Literal["synthetic-release-fixtures-1"]
    fixture_seed: int = Field(ge=0, lt=2**32)
    model_mode: Literal["DEMO_ONLY"]
    datastore: Literal["OWNED_TEMPORARY_SQLITE"]
    bind_host: Literal["127.0.0.1"]
    required_checks: list[str] = Field(min_length=1)
    restrictions: list[str] = Field(min_length=1)


def load(root):
    config = Release.model_validate(store.read_json(root / "configs/release_v1.yaml", 65536))
    load_taxonomy(root)
    research_protocol(root)
    if set(config.required_checks) != {
        "configuration",
        "dependencies",
        "governance",
        "ci",
        "security",
        "synthetic_smoke",
        "manifest",
    }:
        raise ValueError("Mandatory release checks cannot be removed")
    if set(config.restrictions) != {
        "NO_REAL_DATA",
        "NO_RESEARCH_RESULTS",
        "NO_APPROVED_MODEL",
        "LOCALHOST_ONLY",
        "NO_AUTOMATIC_PUBLICATION",
    }:
        raise ValueError("Release restrictions cannot be removed")
    return config
