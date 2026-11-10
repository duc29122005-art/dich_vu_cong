"""Server-configured pseudonymous principals; no client-provided roles are trusted."""

import hmac
import json
from typing import Literal

from fastapi import Depends, HTTPException, Request, Security
from pydantic import Field, SecretStr

from pfa.api.security import KEY, require_key
from pfa.data.registry import Metadata

Role = Literal["ADMIN", "REVIEWER", "ANALYST"]


class Principal(Metadata):
    actor_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    role: Role
    source_ids: list[str] = Field(min_length=1, max_length=20)
    can_view_text: bool = False
    can_adjudicate: bool = False


class Credential(Principal):
    key: SecretStr = Field(repr=False)


def parse_credentials(secret: SecretStr | None) -> list[Credential]:
    if secret is None:
        return []
    try:
        records = json.loads(secret.get_secret_value())
        if not isinstance(records, list) or not 1 <= len(records) <= 32:
            raise ValueError
        credentials = [Credential.model_validate(value) for value in records]
        if len({c.actor_id for c in credentials}) != len(credentials) or len(
            {c.key.get_secret_value() for c in credentials}
        ) != len(credentials):
            raise ValueError
        for item in credentials:
            key = item.key.get_secret_value()
            if (
                not 32 <= len(key) <= 256
                or not key.isascii()
                or not key.isprintable()
                or key.strip() != key
                or (item.can_adjudicate and item.role != "REVIEWER")
                or any(
                    not source.isascii() or not source.replace("_", "").isalnum()
                    for source in item.source_ids
                )
            ):
                raise ValueError
        return credentials
    except (ValueError, TypeError):
        raise ValueError("Invalid protected principal configuration") from None


def resolve(credentials, key):
    match = None
    for candidate in credentials:
        if key is not None and hmac.compare_digest(
            key.encode("utf-8"), candidate.key.get_secret_value().encode("utf-8")
        ):
            match = Principal.model_validate(candidate.model_dump(exclude={"key"}))
    return match


def principal(
    request: Request, key: str | None = Security(KEY), authenticated=Depends(require_key)
) -> Principal:
    value = resolve(request.app.state.settings.credentials, key)
    if value is None:
        # The legacy API key authenticates STEP12 but grants no persistence role.
        raise HTTPException(403, "ROLE_REQUIRED")
    return value
