from __future__ import annotations

import json as json_module
from socket import timeout as SocketTimeout
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .contracts import (
    ConnectorExecutionDeadlineExceeded,
    ConnectorTransportError,
    bounded_transport_timeout,
)


class UrlLibJsonHttpTransport:
    """Small reusable JSON HTTP transport for governed connectors.

    Provider credentials remain in caller-supplied headers and are never included
    in raised errors. HTTP response bodies are decoded only as JSON objects.
    """

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]:
        target = url
        if params:
            query = urlencode(
                [(str(key), str(value)) for key, value in params.items() if value is not None],
                doseq=True,
            )
            target = f"{target}{'&' if '?' in target else '?'}{query}"

        payload = None
        request_headers = {str(key): str(value) for key, value in headers.items()}
        if json is not None:
            payload = json_module.dumps(dict(json), separators=(",", ":")).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        request_headers.setdefault("Accept", "application/json")

        request = Request(
            target,
            data=payload,
            headers=request_headers,
            method=method.upper().strip(),
        )
        effective_timeout = bounded_transport_timeout(timeout_seconds)
        deadline_limited = effective_timeout < timeout_seconds
        try:
            with urlopen(request, timeout=effective_timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            raise ConnectorTransportError(
                f"HTTP transport failed with status {exc.code}",
                status_code=int(exc.code),
                retry_after_seconds=_retry_after_seconds(exc.headers),
            ) from exc
        except (TimeoutError, SocketTimeout) as exc:
            if deadline_limited:
                raise ConnectorExecutionDeadlineExceeded(
                    "governed provider execution deadline exceeded"
                ) from exc
            raise ConnectorTransportError("HTTP transport failed") from exc
        except URLError as exc:
            if deadline_limited and isinstance(exc.reason, (TimeoutError, SocketTimeout)):
                raise ConnectorExecutionDeadlineExceeded(
                    "governed provider execution deadline exceeded"
                ) from exc
            raise ConnectorTransportError("HTTP transport failed") from exc
        except OSError as exc:
            raise ConnectorTransportError("HTTP transport failed") from exc

        if not raw:
            return {}
        try:
            decoded = json_module.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json_module.JSONDecodeError) as exc:
            raise ConnectorTransportError("HTTP response was not valid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise ConnectorTransportError("HTTP response must be a JSON object")
        return dict(decoded)


def _retry_after_seconds(headers: Any) -> float | None:
    """Return a numeric Retry-After delay without retaining provider headers."""

    if headers is None:
        return None
    try:
        raw = headers.get("Retry-After")
    except AttributeError:
        return None
    if raw is None:
        return None
    try:
        value = float(str(raw).strip())
    except ValueError:
        return None
    return value if value >= 0 else None
