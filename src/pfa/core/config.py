"""Validated local configuration. No credentials are required in STEP 01."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment variables override the local working directory's .env file."""

    model_config = SettingsConfigDict(env_prefix="PFA_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    project_root: Path = Field(default_factory=Path.cwd)
    fingerprint_key: SecretStr | None = None

    @field_validator("project_root")
    @classmethod
    def validate_root(cls, value: Path) -> Path:
        """Require an existing directory and normalize relative paths."""
        root = value.expanduser().resolve()
        if not root.is_dir():
            raise ValueError("project_root must be an existing directory")
        return root

    @property
    def data_dir(self) -> Path:
        """Return the local dataset root."""
        return self.project_root / "data"

    @property
    def required_directories(self) -> tuple[Path, ...]:
        """Directories required by the research workspace."""
        names = (
            "configs",
            "data/raw",
            "data/interim",
            "data/processed",
            "data/benchmarks",
            "data/annotations",
            "docs",
            "reports",
            "scripts",
            "src/pfa",
            "tests",
        )
        return tuple(self.project_root / name for name in names)
