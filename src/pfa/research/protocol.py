"""Bind prospective research rules to STEP 11 without changing or unlocking it."""

import csv
import io
import json
from pathlib import Path

from pydantic import Field

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.data.official_io import IngestionBlocked, IngestionError, safe_path
from pfa.ml import model_registry
from pfa.research.schemas import SHA, TEMPLATES, Contract


class Protocol(Contract):
    version: str = Field(pattern="^research-protocol-1$")
    seed: int = Field(ge=0, lt=2**32)
    taxonomy_version: str = Field(pattern="^1\\.0\\.0$")
    taxonomy_checksum: SHA
    evaluation_config_sha256: SHA
    evaluation_document_sha256: SHA
    analytics_config_sha256: SHA
    kpi_dictionary_sha256: SHA
    participant_information_sha256: SHA
    dashboard_tasks_sha256: SHA
    cases_per_condition: int = Field(ge=1, le=100)
    minimum_participants: int = Field(ge=20, le=10000)
    minimum_case_groups: int = Field(ge=20, le=5000)
    minimum_order_participants: int = Field(ge=5)
    bootstrap_replicates: int = Field(ge=500, le=5000)
    confidence_level: float = Field(gt=0.8, lt=1)
    primary_outcomes: list[str]
    researcher: str
    class_name: str
    faculty: str
    university: str
    supervisor: None
    confirmed_independent_annotators: int = Field(ge=0)


def load(root: Path) -> Protocol:
    from pfa.research.rq3 import TASKS

    value = Protocol.model_validate(
        store.read_json(root / "configs/research_protocol_v1.yaml", 65536)
    )
    if (value.taxonomy_version, value.taxonomy_checksum) != (VERSION, CHECKSUM) or (
        value.evaluation_config_sha256 != store.file_checksum(root / "configs/evaluation_v1.yaml")
        or value.evaluation_document_sha256
        != store.file_checksum(root / "docs/EXPERIMENT_PROTOCOL.md")
        or value.primary_outcomes != ["completed_case_time_seconds", "independent_gold_accuracy"]
    ):
        raise IngestionBlocked(
            "Research protocol or STEP11 binding changed; independent design review required"
        )
    for field, file in (
        ("analytics_config_sha256", "configs/analytics_v1.yaml"),
        ("kpi_dictionary_sha256", "docs/KPI_DICTIONARY.md"),
        ("participant_information_sha256", "docs/RESEARCH_PARTICIPANT_CONSENT.md"),
    ):
        if getattr(value, field) != store.file_checksum(root / file):
            raise IngestionBlocked(
                "Analytics or participant material changed; protocol review required"
            )
    if value.dashboard_tasks_sha256 != store.digest(TASKS):
        raise IngestionBlocked("Dashboard questions or scoring rules changed")
    return value


def implementation():
    from pfa.ml import baseline, evaluation, evaluation_policy

    files = {
        "research/" + p.name: store.file_checksum(p) for p in Path(__file__).parent.glob("*.py")
    }
    files.update(
        {
            "ml/" + Path(m.__file__).name: store.file_checksum(Path(m.__file__))
            for m in (baseline, evaluation, evaluation_policy)
        }
    )
    return store.digest(files)


def base(root):
    return safe_path(root / "data/private/research", root)


def freeze(root, protocol, manifest, approval_ref=None):
    """Freeze exact allocation before observations; immutable publication refuses all rewrites."""
    target = store.digest({"protocol": protocol.model_dump(), "allocation": manifest})
    if manifest["mode"] == "SYNTHETIC_ENGINEERING_TEST":
        store.require_synthetic(root)
        evidence = None
    else:
        evidence = model_registry.authorize(root, approval_ref, "RESEARCH_ALLOCATION", target)
    store.publish(
        base(root) / "allocations" / store.identifier(manifest["experiment_id"]),
        {
            "protocol.json": protocol.model_dump(),
            "allocation.json": manifest,
            "lock.json": {
                "target_sha256": target,
                "authorization": evidence,
                "approval_ref": approval_ref,
            },
        },
    )
    return target


def templates(output: Path):
    """New empty directory only: never overwrite collected observations."""
    output = safe_path(output)
    if output.exists():
        raise IngestionError("Template output must be a new directory")
    documents = {}
    for name, schema in TEMPLATES.items():
        stream = io.StringIO(newline="")
        csv.writer(stream).writerow(schema.model_fields)
        documents[name] = (stream.getvalue(), schema.model_json_schema())
    store.private_directory(output)
    for name, (header, schema) in documents.items():
        (output / (name + ".csv")).write_text(header, encoding="utf-8", newline="")
        (output / (name + ".jsonl")).write_text("", encoding="utf-8")
        (output / (name + ".schema.json")).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return {
        "status": "BLANK_TEMPLATES_CREATED",
        "schemas": sorted(TEMPLATES),
        "records": 0,
        "consent_or_participants_created": False,
    }
