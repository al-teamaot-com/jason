from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import (
    OpenBaoSecretResolutionError,
    OpenBaoSecretResolver,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _context() -> ConnectorContext:
    return ConnectorContext(
        correlation_id="corr-123",
        principal_id="user-1",
        organization_id="org-1",
        client_id=None,
        capability="autotask.ticket.get",
    )


def _resolver(
    *,
    opener,
    role_id_path: Path,
    secret_id_path: Path,
) -> OpenBaoSecretResolver:
    return OpenBaoSecretResolver(
        base_url="http://openbao.test:8200",
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
        opener=opener,
    )


def test_resolves_autotask_secret_without_exposing_extra_fields() -> None:
    requests: list[Any] = []

    def opener(request, timeout):
        requests.append(request)

        if request.full_url.endswith("/v1/auth/approle/login"):
            return FakeResponse(
                {
                    "auth": {
                        "client_token": "temporary-token",
                    }
                }
            )

        if request.full_url.endswith(
            "/v1/secret/data/connectors/autotask/production/read-only"
        ):
            return FakeResponse(
                {
                    "data": {
                        "data": {
                            "username": "api-user",
                            "secret": "api-secret",
                            "integration_code": "integration-code",
                            "unexpected": "must-not-be-returned",
                        }
                    }
                }
            )

        if request.full_url.endswith("/v1/auth/token/revoke-self"):
            return FakeResponse({})

        raise AssertionError(f"Unexpected request: {request.full_url}")

    with TemporaryDirectory() as directory:
        root = Path(directory)
        role_id = root / "role-id"
        secret_id = root / "secret-id"
        role_id.write_text("role-value\n", encoding="utf-8")
        secret_id.write_text("secret-id-value\n", encoding="utf-8")

        resolver = _resolver(
            opener=opener,
            role_id_path=role_id,
            secret_id_path=secret_id,
        )

        values = resolver.resolve(
            "autotask.readonly",
            _context(),
        )

    assert values == {
        "integration_code": "integration-code",
        "secret": "api-secret",
        "username": "api-user",
    }

    login_request = requests[0]
    login_body = json.loads(login_request.data.decode("utf-8"))

    assert login_body == {
        "role_id": "role-value",
        "secret_id": "secret-id-value",
    }

    secret_request = requests[1]
    assert secret_request.headers["X-vault-token"] == "temporary-token"

    revoke_request = requests[2]
    assert revoke_request.full_url.endswith("/v1/auth/token/revoke-self")
    assert revoke_request.headers["X-vault-token"] == "temporary-token"


def test_unknown_logical_secret_fails_closed() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)

        resolver = _resolver(
            opener=lambda *args, **kwargs: None,
            role_id_path=root / "role-id",
            secret_id_path=root / "secret-id",
        )

        with pytest.raises(
            OpenBaoSecretResolutionError,
            match="not configured",
        ):
            resolver.resolve(
                "unknown.secret",
                _context(),
            )


def test_missing_required_field_fails_without_value_disclosure() -> None:
    def opener(request, timeout):
        if request.full_url.endswith("/v1/auth/approle/login"):
            return FakeResponse(
                {
                    "auth": {
                        "client_token": "temporary-token",
                    }
                }
            )

        if request.full_url.endswith("/v1/auth/token/revoke-self"):
            return FakeResponse({})

        return FakeResponse(
            {
                "data": {
                    "data": {
                        "username": "api-user",
                        "secret": "super-sensitive-secret",
                    }
                }
            }
        )

    with TemporaryDirectory() as directory:
        root = Path(directory)
        role_id = root / "role-id"
        secret_id = root / "secret-id"
        role_id.write_text("role-value", encoding="utf-8")
        secret_id.write_text("secret-id-value", encoding="utf-8")

        resolver = _resolver(
            opener=opener,
            role_id_path=role_id,
            secret_id_path=secret_id,
        )

        with pytest.raises(OpenBaoSecretResolutionError) as exc_info:
            resolver.resolve(
                "autotask.readonly",
                _context(),
            )

    message = str(exc_info.value)

    assert "integration_code" in message
    assert "super-sensitive-secret" not in message
    assert "temporary-token" not in message


def test_missing_correlation_id_is_denied_before_provider_access() -> None:
    provider_called = False

    def opener(request, timeout):
        nonlocal provider_called
        provider_called = True
        raise AssertionError("Provider must not be called.")

    context = ConnectorContext(
        correlation_id="",
        principal_id="user-1",
        organization_id="org-1",
        client_id=None,
        capability="autotask.ticket.get",
    )

    with TemporaryDirectory() as directory:
        root = Path(directory)

        resolver = _resolver(
            opener=opener,
            role_id_path=root / "role-id",
            secret_id_path=root / "secret-id",
        )

        with pytest.raises(
            OpenBaoSecretResolutionError,
            match="correlation ID",
        ):
            resolver.resolve(
                "autotask.readonly",
                context,
            )

    assert provider_called is False
