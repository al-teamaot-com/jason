"""Governed HTTPS JSON retrieval for Microsoft OpenID discovery and JWKS.

This transport is deliberately restricted to canonical Microsoft login endpoints.
It does not follow arbitrary redirects or accept caller-supplied authorization
headers, preventing the token-verification trust boundary from becoming a generic
network capability.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class MicrosoftOpenIdHttpError(PermissionError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass(frozen=True, slots=True)
class MicrosoftOpenIdJsonFetcher:
    timeout_seconds: float = 10.0
    max_response_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.timeout_seconds > 30:
            raise ValueError("OpenID timeout must be greater than 0 and at most 30 seconds")
        if self.max_response_bytes < 1024 or self.max_response_bytes > 4_194_304:
            raise ValueError("OpenID response limit must be between 1 KiB and 4 MiB")

    def get_json(self, url: str) -> Mapping[str, Any]:
        self._validate_url(url)
        request = Request(
            url=url,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": "Jason/1.0"},
        )
        opener = build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                if content_type not in {"application/json", "application/jwk-set+json"}:
                    raise MicrosoftOpenIdHttpError("Microsoft OpenID endpoint returned an unapproved content type")
                raw = response.read(self.max_response_bytes + 1)
        except HTTPError as exc:
            raise MicrosoftOpenIdHttpError(f"Microsoft OpenID HTTP {exc.code}") from exc
        except URLError as exc:
            raise MicrosoftOpenIdHttpError("Microsoft OpenID network retrieval failed") from exc

        if len(raw) > self.max_response_bytes:
            raise MicrosoftOpenIdHttpError("Microsoft OpenID response exceeded the configured size limit")
        if not raw:
            raise MicrosoftOpenIdHttpError("Microsoft OpenID endpoint returned an empty response")
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MicrosoftOpenIdHttpError("Microsoft OpenID endpoint returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise MicrosoftOpenIdHttpError("Microsoft OpenID response must be a JSON object")
        return parsed

    @staticmethod
    def _validate_url(url: str) -> None:
        if not isinstance(url, str) or not url.strip():
            raise MicrosoftOpenIdHttpError("Microsoft OpenID URL is required")
        parsed = urlparse(url.strip())
        if parsed.scheme != "https" or parsed.hostname != "login.microsoftonline.com":
            raise MicrosoftOpenIdHttpError("Microsoft OpenID URL is not an approved endpoint")
        if parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
            raise MicrosoftOpenIdHttpError("Microsoft OpenID URL contains unapproved authority components")
        if parsed.fragment:
            raise MicrosoftOpenIdHttpError("Microsoft OpenID URL fragments are not permitted")
