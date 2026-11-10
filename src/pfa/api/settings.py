"""Explicit local mode, bounded resources and environment-only credentials."""

from functools import cached_property
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PFA_API_",
        extra="forbid",
        env_file=None,
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    mode: Literal["APPROVED_MODEL", "DEMO_ONLY"] = "APPROVED_MODEL"
    environment: Literal["development", "test", "production"] = "development"
    host: Literal["127.0.0.1", "localhost", "::1"] = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)
    max_text_length: int = Field(default=4000, ge=1, le=20000)
    max_batch_size: int = Field(default=16, ge=1, le=128)
    max_body_bytes: int = Field(default=262144, ge=1024, le=1048576)
    body_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30, allow_inf_nan=False)
    max_concurrency: int = Field(default=1, ge=1, le=4)
    observability_enabled: bool = False
    cors_origins: list[str] = Field(default_factory=list, max_length=16)
    api_key: SecretStr | None = Field(default=None, repr=False, validation_alias="PFA_API_KEY")
    principals: SecretStr | None = Field(default=None, repr=False)
    segmenters_file: Path | None = None

    @field_validator("api_key")
    @classmethod
    def key_strength(cls, value):
        if value is not None:
            key = value.get_secret_value()
            if (
                not 32 <= len(key) <= 256
                or not key.isascii()
                or not key.isprintable()
                or key.strip() != key
            ):
                raise ValueError("API key must contain 32..256 printable ASCII characters")
        return value

    @field_validator("cors_origins")
    @classmethod
    def origins(cls, values):
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in value
            ):
                raise ValueError("Explicit HTTP(S) origins without paths or credentials required")
            _ = parsed.port
        return values

    @model_validator(mode="after")
    def production(self):
        if self.mode == "DEMO_ONLY" and self.environment == "production":
            raise ValueError("DEMO_ONLY is forbidden in production")
        _ = self.credentials
        return self

    @cached_property
    def credentials(self):
        from pfa.api.identity import parse_credentials

        return parse_credentials(self.principals)

    @property
    def authentication_configured(self):
        return self.api_key is not None or bool(self.credentials)

    def public(self):
        return {
            "processing_mode": self.mode,
            "authentication_configured": self.authentication_configured,
            "max_text_length": self.max_text_length,
            "max_batch_size": self.max_batch_size,
        }
