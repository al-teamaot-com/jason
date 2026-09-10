"""Bounded text HTTP transport for provider-published metadata.

This transport is deliberately separate from the JSON connector transport.  It is
intended for authoritative provider schemas/manifests such as XML CSDL documents,
not arbitrary conversation-supplied URLs.  Callers remain responsible for constructing
an approved fixed/provider-governed URL before invoking it.
"""

from __future__ import annotations

from dataclasses import dataclass
from socket import timeout as SocketTimeout
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contracts import (
    ConnectorExecutionDeadlineExceeded,
    ConnectorTransportError,
    bounded_transport_timeout,
)


@dataclass(frozen=True, slots=True)
class UrlLibBoundedTextHttpTransport:
    """Fetch one bounded UTF-8 text document without retaining response headers."""

    maximum_response_bytes: int = 20 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.maximum_response_bytes < 1 or self.maximum_response_bytes > 32 * 1024 * 1024:
            raise ValueError("text metadata response bound must be between 1 byte and 32 MiB")

    def request_text(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float = 30.0,
    ) -> str:
        method = str(method).strip().upper()
        if method not in {"GET", "HEAD"}:
            raise ValueError("text metadata transport permits only GET or HEAD")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError("text metadata transport requires an HTTPS URL")
        if timeout_seconds <= 0:
            raise ValueError("text metadata timeout must be positive")

        request = Request(
            url,
            headers={str(key): str(value) for key, value in headers.items()},
            method=method,
        )
        effective_timeout = bounded_transport_timeout(timeout_seconds)
        deadline_limited = effective_timeout < timeout_seconds

        try:
            with urlopen(request, timeout=effective_timeout) as response:
                raw = response.read(self.maximum_response_bytes + 1)
        except HTTPError as error:
            raise ConnectorTransportError(
                f"metadata HTTP transport failed with status {error.code}",
                status_code=int(error.code),
            ) from error
        except (TimeoutError, SocketTimeout) as error:
            if deadline_limited:
                raise ConnectorExecutionDeadlineExceeded(
                    "governed provider execution deadline exceeded"
                ) from error
            raise ConnectorTransportError("metadata HTTP transport failed") from error
        except URLError as error:
            if deadline_limited and isinstance(error.reason, (TimeoutError, SocketTimeout)):
                raise ConnectorExecutionDeadlineExceeded(
                    "governed provider execution deadline exceeded"
                ) from error
            raise ConnectorTransportError("metadata HTTP transport failed") from error
        except OSError as error:
            raise ConnectorTransportError("metadata HTTP transport failed") from error

        if len(raw) > self.maximum_response_bytes:
            raise ConnectorTransportError("provider metadata response exceeded governed size bound")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ConnectorTransportError("provider metadata response was not UTF-8 text") from error
