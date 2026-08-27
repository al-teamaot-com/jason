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


_MAX_PROVIDER_ERROR_BODY_BYTES = 16384
_MAX_PROVIDER_ERROR_FIELD_CHARS = 500


def _bounded_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple, set)):
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > _MAX_PROVIDER_ERROR_FIELD_CHARS:
        text = text[:_MAX_PROVIDER_ERROR_FIELD_CHARS] + "..."
    return _redact_diagnostic_text(text)


def _redact_diagnostic_text(text: str) -> str:
    """Remove common credential/token forms from bounded diagnostic text."""

    import re

    patterns = (
        (
            re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
            r"\1[REDACTED]",
        ),
        (
            re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
            r"\1[REDACTED]",
        ),
        (
            re.compile(
                r"(?i)((?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
                r"client[_ -]?secret|secret[_ -]?id|password)\s*[:=]\s*)"
                r"[^\s,;]+"
            ),
            r"\1[REDACTED]",
        ),
        (
            re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
            "[REDACTED]",
        ),
    )

    result = text
    for pattern, replacement in patterns:
        result = pattern.sub(replacement, result)
    return result


def _provider_error_fields(raw: bytes) -> dict[str, str | None]:
    """Extract a small provider-neutral diagnostic envelope from JSON errors."""

    import json

    try:
        decoded = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {
            "provider_error_type": None,
            "provider_error_code": None,
            "provider_error_param": None,
            "provider_error_message": None,
        }

    candidate = decoded
    if isinstance(decoded, dict) and isinstance(decoded.get("error"), dict):
        candidate = decoded["error"]

    if not isinstance(candidate, dict):
        return {
            "provider_error_type": None,
            "provider_error_code": None,
            "provider_error_param": None,
            "provider_error_message": None,
        }

    return {
        "provider_error_type": _bounded_text(
            candidate.get("type") or candidate.get("error_type")
        ),
        "provider_error_code": _bounded_text(
            candidate.get("code") or candidate.get("error_code")
        ),
        "provider_error_param": _bounded_text(
            candidate.get("param") or candidate.get("parameter")
        ),
        "provider_error_message": _bounded_text(
            candidate.get("message")
            or candidate.get("detail")
            or candidate.get("error_description")
            or candidate.get("description")
        ),
    }


def _http_service(url: str) -> str | None:
    from urllib.parse import urlsplit

    try:
        hostname = urlsplit(url).hostname
    except Exception:
        return None
    return hostname.strip().lower() if hostname else None


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
            try:
                raw_error = exc.read(_MAX_PROVIDER_ERROR_BODY_BYTES)
            except Exception:
                raw_error = b""

            provider_fields = _provider_error_fields(raw_error)

            raise ConnectorTransportError(
                f"HTTP transport failed with status {exc.code}",
                status_code=int(exc.code),
                retry_after_seconds=_retry_after_seconds(exc.headers),
                service=_http_service(url),
                **provider_fields,
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
