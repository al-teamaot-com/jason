from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Mapping

from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorContext,
    SecretResolver,
)


class OpenBaoSecretResolutionError(RuntimeError):
    """Safe secret-resolution failure that must not contain secret values."""


DEFAULT_MAPPINGS: Mapping[str, str] = {
    "autotask.readonly": (
        "secret/data/connectors/autotask/production/read-only"
    ),
    "it_glue.readonly": (
        "secret/data/connectors/it-glue/production/read-only"
    ),
    "datto_rmm.readonly": (
        "secret/data/connectors/datto-rmm/production/read-only"
    ),
    "aws_ses.sendmail": (
        "secret/data/connectors/aws-ses/production/sendmail"
    ),
    "microsoft_graph.directory_read": (
        "secret/data/connectors/microsoft-graph/production/directory-read"
    ),
}

DEFAULT_FIELDS: Mapping[str, frozenset[str]] = {
    "autotask.readonly": frozenset(
        {
            "username",
            "secret",
            "integration_code",
        }
    ),
    "it_glue.readonly": frozenset(
        {
            "api_key",
        }
    ),
    "datto_rmm.readonly": frozenset(
        {
            "api_url",
            "api_key",
            "api_secret",
        }
    ),
    "aws_ses.sendmail": frozenset(
        {
            "access_key_id",
            "secret_access_key",
        }
    ),
    "microsoft_graph.directory_read": frozenset(
        {
            "private_key_pem",
            "certificate_pem",
            "certificate_thumbprint",
            "generation",
        }
    ),
}


class OpenBaoSecretResolver(SecretResolver):
    def __init__(
        self,
        *,
        base_url: str,
        role_id_path: Path,
        secret_id_path: Path,
        mappings: Mapping[str, str] | None = None,
        allowed_fields: Mapping[str, frozenset[str]] | None = None,
        opener: Callable[..., object] = urllib.request.urlopen,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._role_id_path = role_id_path
        self._secret_id_path = secret_id_path
        self._mappings = dict(mappings or DEFAULT_MAPPINGS)
        self._allowed_fields = dict(allowed_fields or DEFAULT_FIELDS)
        self._opener = opener
        self._timeout_seconds = timeout_seconds

    def resolve(
        self,
        logical_name: str,
        context: ConnectorContext,
    ) -> Mapping[str, str]:
        if not context.correlation_id.strip():
            raise OpenBaoSecretResolutionError(
                "A correlation ID is required for secret resolution."
            )

        provider_path = self._mappings.get(logical_name)
        if provider_path is None:
            raise OpenBaoSecretResolutionError(
                f"Logical secret {logical_name!r} is not configured."
            )

        required_fields = self._allowed_fields.get(logical_name)
        if not required_fields:
            raise ConnectorConfigurationError(
                f"No approved field contract exists for {logical_name!r}."
            )

        role_id = self._read_credential_file(
            self._role_id_path,
            "RoleID",
        )
        secret_id = self._read_credential_file(
            self._secret_id_path,
            "SecretID",
        )

        token = self._login_approle(
            role_id=role_id,
            secret_id=secret_id,
        )

        try:
            secret_data = self._read_kv_v2(
                provider_path=provider_path,
                token=token,
            )
        finally:
            self._revoke_token(token)

        missing = sorted(required_fields.difference(secret_data))
        if missing:
            raise OpenBaoSecretResolutionError(
                "Resolved secret is missing required fields: "
                + ", ".join(missing)
            )

        return {
            field: str(secret_data[field])
            for field in sorted(required_fields)
        }

    @staticmethod
    def _read_credential_file(path: Path, label: str) -> str:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ConnectorConfigurationError(
                f"{label} file is unavailable."
            ) from error

        if not value:
            raise ConnectorConfigurationError(
                f"{label} file is empty."
            )

        return value

    def _login_approle(
        self,
        *,
        role_id: str,
        secret_id: str,
    ) -> str:
        response = self._request_json(
            path="v1/auth/approle/login",
            method="POST",
            payload={
                "role_id": role_id,
                "secret_id": secret_id,
            },
        )

        try:
            token = response["auth"]["client_token"]
        except (KeyError, TypeError) as error:
            raise OpenBaoSecretResolutionError(
                "OpenBao AppRole authentication returned an invalid response."
            ) from error

        if not isinstance(token, str) or not token:
            raise OpenBaoSecretResolutionError(
                "OpenBao AppRole authentication did not return a token."
            )

        return token

    def _revoke_token(self, token: str) -> None:
        self._request_json(
            path="v1/auth/token/revoke-self",
            method="POST",
            token=token,
            allow_empty=True,
        )

    def _read_kv_v2(
        self,
        *,
        provider_path: str,
        token: str,
    ) -> Mapping[str, object]:
        response = self._request_json(
            path=f"v1/{provider_path.lstrip('/')}",
            method="GET",
            token=token,
        )

        try:
            values = response["data"]["data"]
        except (KeyError, TypeError) as error:
            raise OpenBaoSecretResolutionError(
                "OpenBao returned an invalid KV v2 response."
            ) from error

        if not isinstance(values, Mapping):
            raise OpenBaoSecretResolutionError(
                "OpenBao returned invalid secret data."
            )

        return values

    def _request_json(
        self,
        *,
        path: str,
        method: str,
        payload: Mapping[str, object] | None = None,
        token: str | None = None,
        allow_empty: bool = False,
    ) -> Mapping[str, object]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["X-Vault-Token"] = token
        request = urllib.request.Request(
            f"{self._base_url}/{path.lstrip('/')}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise OpenBaoSecretResolutionError(
                "OpenBao secret resolution failed."
            ) from error
        if not raw:
            if allow_empty:
                return {}
            raise OpenBaoSecretResolutionError(
                "OpenBao returned an empty response."
            )
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OpenBaoSecretResolutionError(
                "OpenBao returned malformed JSON."
            ) from error
        if not isinstance(parsed, Mapping):
            raise OpenBaoSecretResolutionError(
                "OpenBao returned an invalid response."
            )
        return parsed
