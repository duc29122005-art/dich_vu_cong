"""Bounded HTTPS transfers with safe errors and no repository code execution."""

import http.client
import ssl
import time
from email.message import Message
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pfa.data.adapters.uit_vsfc import BenchmarkError

TIMEOUT_SECONDS = 30  # Applies to connection and individual socket reads.
ATTEMPTS = 3


def validate_https(url: str) -> None:
    """Reject credentials and non-HTTPS locations, including redirect targets."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise BenchmarkError("Only credential-free HTTPS URLs are supported")


class HTTPSRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: BinaryIO, code: int, msg: str, headers: Message, newurl: str
    ) -> Request | None:
        validate_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def transfer(url: str, stream: BinaryIO, limit: int = 2 * 1024**3) -> None:
    """Retry transient errors from byte zero; never retain a partial attempt."""
    validate_https(url)
    opener = build_opener(HTTPSRedirect())
    failure = "HTTPS connection/read failure"
    for attempt in range(ATTEMPTS):
        stream.seek(0)
        stream.truncate()
        try:
            request = Request(url, headers={"User-Agent": "public-feedback-ai/0.1"})
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                validate_https(response.geturl())
                declared = response.headers.get("Content-Length")
                expected = int(declared) if declared is not None else None
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise BenchmarkError("HTTPS response exceeds configured size limit")
                    stream.write(chunk)
                if expected is not None and size != expected:
                    raise http.client.IncompleteRead(b"")
            stream.flush()
            return
        except HTTPError as error:
            error.close()
            failure = f"HTTPS HTTP {error.code}"
            if error.code != 429 and not 500 <= error.code <= 599:
                raise BenchmarkError(failure + "; no data installed") from None
        except (URLError, TimeoutError, ConnectionError, ssl.SSLError, http.client.HTTPException):
            failure = "HTTPS connection/read failure"
        except BenchmarkError:
            raise
        except ValueError:
            raise BenchmarkError("Invalid HTTPS response headers") from None
        if attempt < ATTEMPTS - 1:
            time.sleep(2**attempt)
    raise BenchmarkError(failure + "; bounded retries exhausted")
