"""Versioned immutable engineering assumptions and reviewed scanner exclusions."""

import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from pfa.data.official_io import safe_path
from pfa.data.registry import Metadata


class Exclusion(Metadata):
    path: str = Field(min_length=1)
    rule: Literal[
        "LITERAL_SECRET",
        "CREDENTIAL_URL",
        "SENSITIVE_SAMPLE",
        "SERVICE_TOKEN",
        "SENSITIVE_IDENTIFIER",
        "ENV_SECRET",
    ]
    line_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=20)


class Config(Metadata):
    version: Literal["integration-1"]
    mode: Literal["SYNTHETIC_ENGINEERING_TEST"]
    source_id: Literal["synthetic_demo"]
    seed: Literal[8]
    postgres_target: Literal["LOCAL_DATABASE_NAME_ENDING_IN_TEST"]
    reviewed_exclusions: list[Exclusion]


def load(root: Path):
    path = safe_path(root / "configs/integration_v1.yaml", root)
    if path.stat().st_size > 65536:
        raise ValueError("Oversized integration configuration")
    config = Config.model_validate(json.loads(path.read_text("utf-8")))
    for exclusion in config.reviewed_exclusions:
        safe_path(root / exclusion.path, root)
    return config
