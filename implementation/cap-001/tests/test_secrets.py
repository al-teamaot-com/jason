from __future__ import annotations

from jason_cap_001.secrets import (
    InMemorySecretsProvider,
    SecretProviderStatus,
    SecretRequest,
    SecretResolutionError,
)


def _request(name: str = "autotask.readonly") -> SecretRequest:
    return SecretRequest(
        secret_name=name,
        purpose="historical ticket investigation",
        execution_context_id="ctx-1",
        requester_id="tech-1",
        capability="operations.ticket.investigate",
        correlation_id="corr-1",
        client_id="client-1",
    )


def test_provider_resolves_by_logical_name() -> None:
    provider = InMemorySecretsProvider(
        {
            "autotask.readonly": {
                "username": "synthetic-user",
                "secret": "synthetic-secret",
                "integration_code": "synthetic-code",
                "zone_url": "https://example.invalid",
            }
        }
    )

    assert provider.health() is SecretProviderStatus.HEALTHY
    lease = provider.resolve(_request())
    assert lease.secret_name == "autotask.readonly"
    assert lease.values["username"] == "synthetic-user"
    assert "synthetic-secret" not in repr(lease)
    assert "synthetic-user" not in repr(lease)


def test_missing_secret_fails_closed_without_value_disclosure() -> None:
    provider = InMemorySecretsProvider({})

    try:
        provider.resolve(_request("missing.secret"))
    except SecretResolutionError as exc:
        assert "missing.secret" in str(exc)
    else:
        raise AssertionError("Missing logical secret did not fail closed.")


def test_metadata_returns_field_names_not_values() -> None:
    provider = InMemorySecretsProvider(
        {"autotask.readonly": {"username": "user-value", "secret": "secret-value"}}
    )

    metadata = provider.metadata("autotask.readonly")
    assert metadata.field_names == ("secret", "username")
    assert "secret-value" not in repr(metadata)
    assert "user-value" not in repr(metadata)
