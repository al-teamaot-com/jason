from dataclasses import dataclass

import pytest

from connectors.microsoft_graph.user_directory import MicrosoftGraphUserDirectoryReader


@dataclass
class Tokens:
    token: str = "token-value"
    tenant_seen: str | None = None

    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str:
        self.tenant_seen = microsoft_tenant_id
        return self.token


@dataclass
class Transport:
    response: dict
    call: dict | None = None

    def request(self, **kwargs):
        self.call = kwargs
        return dict(self.response)


def reader(response):
    tokens = Tokens()
    transport = Transport(response)
    return MicrosoftGraphUserDirectoryReader(tokens=tokens, transport=transport), tokens, transport


def test_resolves_mail_for_exact_authenticated_object():
    directory, tokens, transport = reader({
        "id": "object-1",
        "mail": "al@teamaot.com",
        "userPrincipalName": "al@teamaot.com",
        "accountEnabled": True,
    })

    email = directory.resolve_email(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
    )

    assert email == "al@teamaot.com"
    assert tokens.tenant_seen == "tenant-1"
    assert transport.call["method"] == "GET"
    assert transport.call["url"] == "https://graph.microsoft.com/v1.0/users/object-1"
    assert transport.call["params"] == {"$select": "id,mail,userPrincipalName,accountEnabled"}
    assert transport.call["headers"]["Authorization"] == "Bearer token-value"


def test_falls_back_to_upn_when_mail_is_empty():
    directory, _, _ = reader({
        "id": "object-1",
        "mail": None,
        "userPrincipalName": "user@teamaot.com",
        "accountEnabled": True,
    })
    assert directory.resolve_email(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
    ) == "user@teamaot.com"


def test_identity_mismatch_fails_closed():
    directory, _, _ = reader({
        "id": "different-object",
        "mail": "other@teamaot.com",
        "accountEnabled": True,
    })
    with pytest.raises(PermissionError):
        directory.resolve_email(
            microsoft_tenant_id="tenant-1",
            microsoft_object_id="object-1",
        )


def test_disabled_account_fails_closed():
    directory, _, _ = reader({
        "id": "object-1",
        "mail": "user@teamaot.com",
        "accountEnabled": False,
    })
    with pytest.raises(PermissionError):
        directory.resolve_email(
            microsoft_tenant_id="tenant-1",
            microsoft_object_id="object-1",
        )


def test_missing_address_returns_none():
    directory, _, _ = reader({
        "id": "object-1",
        "mail": None,
        "userPrincipalName": None,
        "accountEnabled": True,
    })
    assert directory.resolve_email(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
    ) is None
