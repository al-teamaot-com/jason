from __future__ import annotations

import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from connectors.core.contracts import (
    ConnectorContext,
    ConnectorCredentialUnavailableError,
    ConnectorTransportError,
)
from connectors.core.openbao_secrets import (
    OpenBaoAuthenticationError,
    OpenBaoSecretResolver,
    OpenBaoTransportError,
)


def _context() -> ConnectorContext:
    return ConnectorContext(
        correlation_id="corr-safe-diagnostic",
        principal_id="principal-1",
        organization_id="org-1",
        client_id=None,
        capability="autotask.ticket.get",
    )


def test_provider_http_status_is_bounded_in_error_code() -> None:
    error = ConnectorTransportError(
        "provider returned a protected response",
        status_code=403,
        provider_error_message="must not be surfaced by orchestration",
    )

    assert error.error_code == "PROVIDER_HTTP_STATUS_403"
    assert error.status_code == 403


def test_missing_bootstrap_file_is_classified_before_network_access() -> None:
    network_contacted = False

    def opener(*args, **kwargs):
        nonlocal network_contacted
        network_contacted = True
        raise AssertionError("network must not be contacted")

    with TemporaryDirectory() as directory:
        root = Path(directory)
        resolver = OpenBaoSecretResolver(
            base_url="http://openbao.test:8200",
            role_id_path=root / "missing-role-id",
            secret_id_path=root / "missing-secret-id",
            opener=opener,
        )

        with pytest.raises(ConnectorCredentialUnavailableError) as exc_info:
            resolver.resolve("autotask.readonly", _context())

    assert exc_info.value.error_code == "CONNECTOR_CREDENTIAL_UNAVAILABLE"
    assert network_contacted is False


def test_approle_http_failure_is_classified_as_auth_failure() -> None:
    def opener(request, timeout):
        del timeout
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=None,
        )

    with TemporaryDirectory() as directory:
        root = Path(directory)
        role_id = root / "role-id"
        secret_id = root / "secret-id"
        role_id.write_text("role-value", encoding="utf-8")
        secret_id.write_text("secret-value", encoding="utf-8")
        resolver = OpenBaoSecretResolver(
            base_url="http://openbao.test:8200",
            role_id_path=role_id,
            secret_id_path=secret_id,
            opener=opener,
        )

        with pytest.raises(OpenBaoAuthenticationError) as exc_info:
            resolver.resolve("autotask.readonly", _context())

    assert exc_info.value.error_code == "OPENBAO_AUTH_FAILED"
    assert "role-value" not in str(exc_info.value)
    assert "secret-value" not in str(exc_info.value)


def test_openbao_network_failure_remains_transport_failure() -> None:
    def opener(request, timeout):
        del request, timeout
        raise urllib.error.URLError("connection refused")

    with TemporaryDirectory() as directory:
        root = Path(directory)
        role_id = root / "role-id"
        secret_id = root / "secret-id"
        role_id.write_text("role-value", encoding="utf-8")
        secret_id.write_text("secret-value", encoding="utf-8")
        resolver = OpenBaoSecretResolver(
            base_url="http://openbao.test:8200",
            role_id_path=role_id,
            secret_id_path=secret_id,
            opener=opener,
        )

        with pytest.raises(OpenBaoTransportError) as exc_info:
            resolver.resolve("autotask.readonly", _context())

    assert exc_info.value.error_code == "OPENBAO_TRANSPORT_FAILURE"
    assert "connection refused" not in str(exc_info.value)
