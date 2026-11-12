"""Bounded Constant Contact V3 HTTP transport helpers.

The caller resolves OAuth credentials from OpenBao and enforces Jason identity,
information-release and authorization gates before calling these helpers.
No provider writes are available here.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

BASE_URL = "https://api.cc.email/v3"
ALLOWED_RESOURCES = frozenset({"/contact_lists", "/contacts", "/contact_custom_fields"})


class ConstantContactProviderError(RuntimeError):
    """Redacted provider failure with no request data or response body."""


def _resource_path(path: str) -> str:
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment or parsed.username:
        raise ConstantContactProviderError("Absolute or malformed resource URL rejected")
    if parsed.path not in ALLOWED_RESOURCES:
        raise ConstantContactProviderError("Unapproved Constant Contact resource")
    if parsed.query:
        raise ConstantContactProviderError("Resource must not contain raw query")
    return parsed.path


def read_page(
    *,
    resource: str,
    access_token: str,
    limit: int = 50,
    cursor: str | None = None,
    transport: Callable = urlopen,
) -> dict:
    """Read one bounded page. A cursor is opaque and never interpreted as a URL."""
    path = _resource_path(resource)
    if not access_token:
        raise ConstantContactProviderError("Missing token")
    if not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ConstantContactProviderError("Invalid page size")
    if cursor is not None and (not cursor or len(cursor) > 2048):
        raise ConstantContactProviderError("Invalid cursor")
    params = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    req = Request(BASE_URL + path + "?" + urlencode(params), headers={
        "Authorization": "Bearer " + access_token,
        "Accept": "application/json",
    }, method="GET")
    try:
        with transport(req, timeout=15) as response:
            payload = response.read(1048577)
        if len(payload) > 1048576:
            raise ConstantContactProviderError("Provider response exceeds limit")
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Not a JSON object")
        return data
    except ConstantContactProviderError:
        raise
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        raise ConstantContactProviderError("Constant Contact read failed") from None
