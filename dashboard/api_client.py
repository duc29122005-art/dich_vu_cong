"""Server-side local API client. Never accepts a browser-supplied credential or URL."""

from urllib.parse import urlsplit

import httpx
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pfa.analytics.schemas import Filters, Report


class DashboardError(Exception):
    """Contains only a fixed public error code, never upstream exception text."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PFA_DASHBOARD_", env_file=None, extra="forbid", hide_input_in_errors=True
    )
    api_url: str = "http://127.0.0.1:8000"
    api_key: SecretStr | None = Field(default=None, repr=False)

    @field_validator("api_url")
    @classmethod
    def local_origin(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Explicit local API origin required")
        _ = parsed.port
        return value.rstrip("/")


class Client:
    def __init__(self, settings=None, *, http=None):
        self.settings = settings or Settings()
        self.http = http

    def fetch(self, endpoint, filters):
        if endpoint not in {"summary", "topics", "trends", "alerts"}:
            raise DashboardError("UNSUPPORTED_ENDPOINT")
        if self.settings.api_key is None:
            raise DashboardError("MISSING_API_CREDENTIAL")
        filters = filters if isinstance(filters, Filters) else Filters.model_validate(filters)
        params = filters.model_dump(mode="json", exclude_none=True)
        headers = {"X-API-Key": self.settings.api_key.get_secret_value()}
        path = "/api/v1/analytics/" + endpoint
        try:
            if self.http is not None:
                response = self.http.get(path, params=params, headers=headers)
            else:
                with httpx.Client(
                    base_url=self.settings.api_url,
                    timeout=5,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    response = client.get(path, params=params, headers=headers)
            if response.status_code in {401, 403}:
                raise DashboardError("AUTHORIZATION_DENIED")
            if response.status_code != 200:
                raise DashboardError("API_UNAVAILABLE")
            if len(response.content) > 2 * 1024**2:
                raise DashboardError("INVALID_API_RESPONSE")
            return Report.model_validate(response.json())
        except DashboardError:
            raise
        except Exception:
            raise DashboardError("API_UNAVAILABLE_OR_INVALID") from None
