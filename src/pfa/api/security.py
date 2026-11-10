"""Bound bodies before parsing; authenticate before reading; never reflect/log input."""

import hmac
import ipaddress
import json
import logging
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

import anyio
from fastapi import HTTPException, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from pfa.annotation.taxonomy import unique_object
from pfa.api.settings import ApiSettings

LOGGER = logging.getLogger("pfa.api")
KEY = APIKeyHeader(name="X-API-Key", auto_error=False)
ROUTES = {
    "/health/live",
    "/health/ready",
    "/api/v1/models/status",
    "/api/v1/predict",
    "/api/v1/predict/batch",
    "/api/v1/taxonomy",
    "/api/v1/version",
    "/openapi.json",
    "/docs",
    "/api/v1/operations/status",
    "/api/v1/feedback",
    "/api/v1/reviews/queue",
    "/api/v1/analytics/summary",
    "/api/v1/analytics/topics",
    "/api/v1/analytics/trends",
    "/api/v1/analytics/alerts",
}


def authentication(settings: ApiSettings, supplied: str | None):
    from pfa.api.identity import resolve

    if not settings.authentication_configured:
        return 503, "AUTHENTICATION_NOT_CONFIGURED"
    legacy = (
        supplied is not None
        and settings.api_key is not None
        and hmac.compare_digest(
            supplied.encode("utf-8"), settings.api_key.get_secret_value().encode("utf-8")
        )
    )
    if not legacy and resolve(settings.credentials, supplied) is None:
        return 401, "UNAUTHORIZED"
    return None


def require_key(request: Request, key: str | None = Security(KEY)):
    failure = authentication(request.app.state.settings, key)
    if failure:
        raise HTTPException(failure[0], failure[1])


def error(status, code, trace, headers=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": "Request could not be processed",
                "request_id": trace,
            }
        },
        headers=headers,
    )


class Boundary:
    def __init__(self, app, settings, metrics=None):
        self.app, self.settings = app, settings
        self.metrics = metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        trace, started, status, sent = uuid4().hex, perf_counter(), 500, False
        scope.setdefault("state", {})["trace_id"] = trace

        async def safe_send(message):
            nonlocal status, sent
            if message["type"] == "http.response.start":
                status, sent = message["status"], True
                message["headers"] = [
                    *message.get("headers", []),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-request-id", trace.encode("ascii")),
                ]
            await send(message)

        async def reject(code, label):
            await error(
                code, label, trace, {"WWW-Authenticate": "ApiKey"} if code == 401 else None
            )(scope, receive, safe_send)

        try:
            headers = {}
            for key, value in scope.get("headers", []):
                key = key.decode("latin-1").lower()
                if key in headers and key in {
                    "content-length",
                    "host",
                    "x-api-key",
                    "content-type",
                }:
                    return await reject(400, "INVALID_HEADERS")
                headers[key] = value.decode("latin-1")
            if self.settings.mode == "DEMO_ONLY":
                try:
                    local = ipaddress.ip_address(scope.get("client", ("", 0))[0]).is_loopback
                    host = urlsplit("//" + headers.get("host", "")).hostname
                except (ValueError, TypeError):
                    local, host = False, None
                if not local or host not in {"127.0.0.1", "localhost", "::1"}:
                    return await reject(403, "DEMO_LOCAL_ONLY")
            path, method = scope["path"], scope["method"]
            if path.startswith("/api/") and method != "OPTIONS":
                failure = authentication(self.settings, headers.get("x-api-key"))
                if failure:
                    return await reject(*failure)
            if headers.get("content-encoding", "identity") != "identity":
                return await reject(415, "UNSUPPORTED_CONTENT_ENCODING")
            length = headers.get("content-length")
            if length is not None:
                if (
                    not length.isascii()
                    or not length.isdecimal()
                    or len(length) > 10
                    or "transfer-encoding" in headers
                ):
                    return await reject(400, "INVALID_HEADERS")
                if int(length) > self.settings.max_body_bytes:
                    return await reject(413, "REQUEST_BODY_TOO_LARGE")
            chunks, count = [], 0
            with anyio.fail_after(self.settings.body_timeout_seconds):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    block = message.get("body", b"")
                    count += len(block)
                    if count > self.settings.max_body_bytes:
                        return await reject(413, "REQUEST_BODY_TOO_LARGE")
                    chunks.append(block)
                    if not message.get("more_body", False):
                        break
            if length is not None and int(length) != count:
                return await reject(400, "INVALID_BODY_LENGTH")
            body = b"".join(chunks)
            if method in {"POST", "PATCH"} and path.startswith("/api/v1/"):
                content_type = headers.get("content-type", "").lower().replace(" ", "")
                if content_type not in {"application/json", "application/json;charset=utf-8"}:
                    return await reject(415, "JSON_CONTENT_TYPE_REQUIRED")
                try:
                    # Decode UTF-8 strictly; JSON duplicate keys and NaN/Infinity are rejected.
                    def invalid_constant(value):
                        raise ValueError("Nonfinite JSON constant")

                    json.loads(
                        body.decode("utf-8"),
                        object_pairs_hook=unique_object,
                        parse_constant=invalid_constant,
                    )
                except (ValueError, UnicodeError, RecursionError):
                    return await reject(400, "MALFORMED_JSON")
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await self.app(scope, replay, safe_send)
        except TimeoutError:
            if not sent:
                await reject(408, "REQUEST_BODY_TIMEOUT")
        except Exception:
            # No exception repr/stack: third-party exceptions can contain text or filesystem paths.
            if not sent:
                await reject(500, "INTERNAL_ERROR")
        finally:
            duration = (perf_counter() - started) * 1000
            if self.metrics is not None:
                self.metrics.record(status, duration)
            LOGGER.info(
                json.dumps(
                    {
                        "event": "api_request",
                        "trace_id": trace,
                        "route": scope["path"] if scope["path"] in ROUTES else "UNMATCHED",
                        "status": status,
                        "duration_ms": round(duration, 3),
                    }
                )
            )
