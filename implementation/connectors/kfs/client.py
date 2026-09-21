from __future__ import annotations

import json
from http.cookiejar import CookieJar
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorTransportError,
)


class KfsApiClient:
    """KFS client using gateway Authorization plus a KFS Manager login cookie."""

    REQUIRED_SECRET_FIELDS = (
        "request_from",
        "request_to",
        "manager_id",
        "manager_password",
        "authorization",
    )

    def __init__(
        self,
        credentials: Mapping[str, str],
        *,
        base_url: str,
        api_version: int = 6,
        timeout_seconds: float = 30.0,
        opener=None,
    ) -> None:
        self.credentials = self._validate_credentials(credentials)
        if not base_url.strip():
            raise ConnectorConfigurationError("KFS base_url is required.")
        self.base_url = base_url.rstrip("/")
        self.api_version = int(api_version)
        self.timeout_seconds = timeout_seconds
        self._opener = opener or build_opener(HTTPCookieProcessor(CookieJar()))

    @classmethod
    def _validate_credentials(cls, credentials: Mapping[str, str]) -> Mapping[str, str]:
        missing = [
            field
            for field in cls.REQUIRED_SECRET_FIELDS
            if not str(credentials.get(field, "")).strip()
        ]
        if missing:
            raise ConnectorConfigurationError(
                "KFS credential binding is incomplete: " + ", ".join(missing)
            )
        return credentials

    def call(
        self,
        path: str,
        body: Mapping[str, Any],
        *,
        min_api_version: int = 1,
    ) -> Mapping[str, Any]:
        if self.api_version < min_api_version:
            raise ConnectorConfigurationError(
                f"KFS capability requires API version {min_api_version} or later."
            )
        self._login()
        payload = self._post(path, body)
        self.require_success(payload, path)
        return payload

    def _login(self) -> None:
        payload = self._post(
            "/KFS/Login",
            {
                "RequestFrom": self.credentials["request_from"],
                "RequestTo": self.credentials["request_to"],
                "BODID": "Global_KFS_Pull_Login",
                "id": self.credentials["manager_id"],
                "password": self.credentials["manager_password"],
                "isPersistent": False,
                "timeZone": "-0400",
            },
        )
        self.require_success(payload, "KFS login")

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
            raise ConnectorTransportError(
                f"KFS HTTP request failed with status {exc.code}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ConnectorTransportError("KFS HTTP request failed") from exc

        try:
            decoded = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectorTransportError("KFS response was not valid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise ConnectorTransportError("KFS response must be a JSON object")
        return dict(decoded)

    @staticmethod
    def require_success(payload: Mapping[str, Any], operation: str) -> None:
        status = payload.get("status")
        code = status.get("code") if isinstance(status, Mapping) else None
        if code != 200:
            raise ConnectorTransportError(
                f"{operation} failed with KFS status {code!r}"
            )
