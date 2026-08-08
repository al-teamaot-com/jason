from __future__ import annotations

import pytest

from connectors.microsoft_graph.credential_binding import (
    MicrosoftCredentialBinding,
    build_credential_resolution_plan,
)


def test_builds_non_secret_resolution_plan() -> None:
    binding = MicrosoftCredentialBinding(
        tenant_id="tenant-123",
        client_id="client-456",
        certificate_secret_name="microsoft.graph.certificate",
        thumbprint_secret_name="microsoft.graph.thumbprint",
    )

    plan = build_credential_resolution_plan(binding)

    assert plan.tenant_id == "tenant-123"
    assert plan.client_id == "client-456"
    assert plan.authority == "https://login.microsoftonline.com/tenant-123"
    assert plan.required_logical_secrets == (
        "microsoft.graph.certificate",
        "microsoft.graph.thumbprint",
    )


def test_rejects_non_microsoft_secret_namespace() -> None:
    with pytest.raises(ValueError, match=r"microsoft\.\*"):
        MicrosoftCredentialBinding(
            tenant_id="tenant-123",
            client_id="client-456",
            certificate_secret_name="graph.certificate",
            thumbprint_secret_name="microsoft.graph.thumbprint",
        )


def test_rejects_noncanonical_authority_host() -> None:
    with pytest.raises(ValueError, match="canonical Microsoft authority"):
        MicrosoftCredentialBinding(
            tenant_id="tenant-123",
            client_id="client-456",
            certificate_secret_name="microsoft.graph.certificate",
            thumbprint_secret_name="microsoft.graph.thumbprint",
            authority_host="https://example.invalid",
        )


def test_does_not_accept_same_logical_secret_for_both_values() -> None:
    with pytest.raises(ValueError, match="must be distinct"):
        MicrosoftCredentialBinding(
            tenant_id="tenant-123",
            client_id="client-456",
            certificate_secret_name="microsoft.graph.credential",
            thumbprint_secret_name="microsoft.graph.credential",
        )
