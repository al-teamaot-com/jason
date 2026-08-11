from __future__ import annotations

from datetime import datetime, timezone

import pytest

from management_api.identity_exchange import (
    ExternalIdentity,
    ExternalIdentityBinding,
    ManagementIdentityExchange,
    ManagementIdentityExchangeDenied,
)


class BindingRepo:
    def __init__(self, binding=None):
        self.binding = binding
        self.calls = []

    def get_binding(self, *, issuer, subject, tenant_id):
        self.calls.append((issuer, subject, tenant_id))
        return self.binding


class Signer:
    def __init__(self):
        self.claims = None

    def sign(self, claims):
        self.claims = dict(claims)
        return "signed-management-token"


def identity():
    return ExternalIdentity(
        issuer="https://login.example/tenant/v2.0",
        subject="external-user-123",
        tenant_id="tenant-aot",
        authentication_assurance="mfa",
    )


def binding(status="active"):
    return ExternalIdentityBinding(
        issuer="https://login.example/tenant/v2.0",
        subject="external-user-123",
        tenant_id="tenant-aot",
        principal_id="person-al",
        organization_id="aot",
        status=status,
    )


def test_exchange_uses_governed_binding_for_jason_scope():
    repo = BindingRepo(binding())
    signer = Signer()
    service = ManagementIdentityExchange(
        bindings=repo,
        signer=signer,
        issuer="https://jason.internal/identity",
        audience="jason-management-api",
    )
    now = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)

    token = service.exchange(identity(), ttl_seconds=120, now=now)

    assert token.principal_id == "person-al"
    assert token.organization_id == "aot"
    assert token.token == "signed-management-token"
    assert signer.claims["sub"] == "person-al"
    assert signer.claims["organization_id"] == "aot"
    assert signer.claims["authentication_assurance"] == "mfa"
    assert signer.claims["exp"] - signer.claims["iat"] == 120


def test_exchange_denies_unbound_identity():
    service = ManagementIdentityExchange(
        bindings=BindingRepo(None),
        signer=Signer(),
        issuer="https://jason.internal/identity",
        audience="jason-management-api",
    )

    with pytest.raises(ManagementIdentityExchangeDenied):
        service.exchange(identity())


def test_exchange_denies_inactive_binding():
    service = ManagementIdentityExchange(
        bindings=BindingRepo(binding(status="disabled")),
        signer=Signer(),
        issuer="https://jason.internal/identity",
        audience="jason-management-api",
    )

    with pytest.raises(ManagementIdentityExchangeDenied):
        service.exchange(identity())


def test_exchange_caps_token_lifetime():
    service = ManagementIdentityExchange(
        bindings=BindingRepo(binding()),
        signer=Signer(),
        issuer="https://jason.internal/identity",
        audience="jason-management-api",
        maximum_ttl_seconds=300,
    )

    with pytest.raises(ManagementIdentityExchangeDenied):
        service.exchange(identity(), ttl_seconds=301)


def test_exchange_caller_cannot_supply_jason_scope():
    service = ManagementIdentityExchange(
        bindings=BindingRepo(binding()),
        signer=Signer(),
        issuer="https://jason.internal/identity",
        audience="jason-management-api",
    )

    with pytest.raises(TypeError):
        service.exchange(
            identity(),
            principal_id="attacker",
            organization_id="other-org",
        )
