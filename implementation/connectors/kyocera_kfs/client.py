from __future__ import annotations

import base64
import binascii
import json
from http.cookiejar import CookieJar
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorTransportError,
)
from connectors.core.http_transport import _safe_network_failure_code

KFS_PUBLIC_API_HOST = "api.kyods.com"
KFS_DEFAULT_API_URL = f"https://{KFS_PUBLIC_API_HOST}"


def _basic_authorization_pair(value: str) -> tuple[str, str] | None:
    token = str(value or "").strip()
    if token.lower().startswith("basic "):
        token = token[6:].strip()
    try:
        decoded = base64.b64decode(token, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if ":" not in decoded:
        return None
    username, password = decoded.split(":", 1)
    return username, password


def require_kfs_credentials(credentials: Mapping[str, str]) -> None:
    required = (
        "api_url",
        "request_from",
        "request_to",
        "authorization",
        "kfs_username",
        "kfs_password",
    )
    missing = [name for name in required if not str(credentials.get(name, "")).strip()]
    if missing:
        raise ConnectorConfigurationError(
            "Kyocera KFS credential contract is incomplete: " + ", ".join(missing)
        )

    parsed = urlparse(str(credentials["api_url"]).strip())
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() != KFS_PUBLIC_API_HOST
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ConnectorConfigurationError(
            "Kyocera KFS api_url must be the approved HTTPS api.kyods.com endpoint."
        )

    gateway_pair = _basic_authorization_pair(str(credentials["authorization"]))
    if gateway_pair is not None:
        manager_pair = (
            str(credentials["kfs_username"]),
            str(credentials["kfs_password"]),
        )
        if manager_pair == gateway_pair:
            raise ConnectorConfigurationError(
                "Kyocera KFS Manager login must be distinct from the dealer API gateway credential."
            )


class KyoceraKfsApplicationStatusError(ConnectorTransportError):
    """A provider application-status failure, distinct from an HTTP failure.

    Exposes only a bounded numeric status and never the KFS login response,
    request contents, gateway credentials, or provider-controlled message.
    """

    def __init__(self, operation: str, code: Any):
        super().__init__("Kyocera KFS operation returned an unsuccessful application status", service="kyocera_kfs")
        safe_code = code if type(code) is int and 100 <= code <= 999 else "UNKNOWN"
        self.error_code = f"KFS_APPLICATION_STATUS_{safe_code}"
        self.operation = operation  # internal fixed operation label, not response text


class KyoceraKfsSafeResponseError(ConnectorTransportError):
    """A fixed diagnostic for a KFS response that is not usable JSON.

    No provider text, body, Authorization or credential values are retained.
    """

    _ALLOWED_CODES = frozenset({
        "NETWORK_TIMEOUT", "DNS_RESOLUTION", "TLS_FAILURE",
        "CONNECTION_REFUSED", "NETWORK_UNREACHABLE", "NETWORK_IO_FAILURE",
        "INVALID_JSON", "INVALID_RESPONSE_SHAPE",
    })

    def __init__(self, code: str):
        safe_code = code if code in self._ALLOWED_CODES else "NETWORK_IO_FAILURE"
        super().__init__("Kyocera KFS read could not obtain a valid response", service="kyocera_kfs")
        self.error_code = f"KFS_{safe_code}"


class KyoceraKfsSessionClient:
    """KFS v6 session client.

    KFS uses two authentication layers: the dealer API Authorization header and
    a KFS Manager-or-higher login. The login cookie is kept only in this
    short-lived client and is never persisted by Jason.
    """

    def __init__(
        self,
        credentials: Mapping[str, str],
        *,
        api_version: int = 6,
        timeout_seconds: float = 30.0,
        opener=None,
    ) -> None:
        require_kfs_credentials(credentials)
        self.credentials = credentials
        self.api_version = int(api_version)
        self.timeout_seconds = timeout_seconds
        self.base_url = str(credentials["api_url"]).rstrip("/")
        self._opener = opener or build_opener(HTTPCookieProcessor(CookieJar()))
        self._logged_in = False

    def call(self, path: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        if not self._logged_in:
            self.login()
        payload = self._post(path, body)
        status = payload.get("status")
        code = status.get("code") if isinstance(status, Mapping) else None
        if code == 401:
            self._logged_in = False
            self.login()
            payload = self._post(path, body)
        self._require_success(payload, path)
        return payload

    def login(self) -> None:
        payload = self._post(
            "/KFS/Login",
            {
                "RequestFrom": self.credentials["request_from"],
                "RequestTo": self.credentials["request_to"],
                "BODID": "Global_KFS_Pull_Login",
                "id": self.credentials["kfs_username"],
                "password": self.credentials["kfs_password"],
                "isPersistent": False,
                "timeZone": -400,
            },
        )
        self._require_success(payload, "KFS login")
        self._logged_in = True

    def _authorization_header(self) -> str:
        value = str(self.credentials["authorization"]).strip()
        return value if value.lower().startswith("basic ") else f"Basic {value}"

    def _post(self, path: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(dict(body), separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
                "Authorization": self._authorization_header(),
                "x-api-version": str(self.api_version),
            },
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            # Keep HTTP status as bounded diagnostic metadata. The previous
            # exception discarded it, collapsing 401/403/429/5xx into one
            # opaque PROVIDER_TRANSPORT_FAILURE. Never include HTTP response
            # body, headers, tokens, or the provider-supplied error message.
            raise ConnectorTransportError(
                "Kyocera KFS HTTP request failed",
                status_code=int(exc.code),
                service="kyocera_kfs",
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            # Network failure taxonomy is a fixed local classification, not an
            # uncontrolled exception message or provider response body.
            raise KyoceraKfsSafeResponseError(_safe_network_failure_code(exc)) from exc

        try:
            decoded = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KyoceraKfsSafeResponseError("INVALID_JSON") from exc
        if not isinstance(decoded, Mapping):
            raise KyoceraKfsSafeResponseError("INVALID_RESPONSE_SHAPE")
        return dict(decoded)

    @staticmethod
    def _require_success(payload: Mapping[str, Any], operation: str) -> None:
        status = payload.get("status")
        code = status.get("code") if isinstance(status, Mapping) else None
        if code != 200:
            # An HTTP 200 may still carry a failed KFS *application* status;
            # never mislabel it PROVIDER_HTTP_STATUS_401, and never leak the
            # provider's optional human-readable error text.
            raise KyoceraKfsApplicationStatusError(operation, code)
