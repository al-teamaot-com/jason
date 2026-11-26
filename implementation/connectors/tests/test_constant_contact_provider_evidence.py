import pytest

from connectors.constant_contact.import_activity import build_specification
from connectors.constant_contact.import_preflight import preflight
from connectors.constant_contact.import_authorization import ImportAuthorizationError
from connectors.constant_contact.provider_evidence import (
    ConstantContactProviderEvidence, MAX_VERIFIED_CONTACTS,
)

LIST_ID = "11111111-2222-3333-4444-555555555555"
ACCOUNT = "aot1234567890"


def spec(count=1):
    p = preflight([
        {"email": f"contact{i}@example.com", "marketing_consent": "explicit",
         "consent_evidence": f"opt-in proof {i}"} for i in range(count)
    ])
    return build_specification(p, list_ids=[LIST_ID])


class Provider:
    def __init__(self):
        self.account = ACCOUNT
        self.list_name = "Approved AOT List"
        self.exists = False
        self.permission = "explicit"
        self.memberships = []
        self.paginated = False
        self.invalid_account = False
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["method"] == "GET"
        assert kwargs["url"].startswith("https://api.cc.email/v3/")
        if kwargs["url"].endswith("/account/summary"):
            return {"encoded_account_id": self.account}
        if "/contact_lists/" in kwargs["url"]:
            return {"list_id": LIST_ID, "name": self.list_name}
        if kwargs["url"].endswith("/contacts"):
            assert kwargs["params"]["status"] == "all"
            assert kwargs["params"]["include"] == "list_memberships"
            email = kwargs["params"]["email"]
            return {
                "_links": {"next": {"href": "/v3/contacts?cursor=next"}} if self.paginated else {},
                "contacts": ([{
                    "email_address": {
                        "address": email,
                        "permission_to_send": self.permission,
                    },
                    "list_memberships": list(self.memberships),
                }] if self.exists else []),
            }
        raise AssertionError("Unexpected Constant Contact endpoint")


def verifier(provider):
    return ConstantContactProviderEvidence(
        transport=provider, access_token="test-only-token",
        expected_encoded_account_id=ACCOUNT,
        minimum_interval_seconds=0,
    )


def test_exact_account_list_and_suppression_digest_binds_live_provider():
    provider = Provider()
    service = verifier(provider)
    snapshot = service.snapshot(spec())
    assert snapshot.contact_count == 1
    assert len(snapshot.account_binding_sha256) == 64
    assert len(snapshot.suppression_receipt_sha256) == 64
    service.require_current_provider_match(
        account_binding_sha256=snapshot.account_binding_sha256,
        specification=spec(), suppression_receipt_sha256=snapshot.suppression_receipt_sha256,
    )
    assert [c["method"] for c in provider.calls] == ["GET"] * 6
    assert all(c["url"].startswith("https://api.cc.email/v3/") for c in provider.calls)


def test_account_or_target_list_changed_fails_closed():
    provider = Provider()
    service = verifier(provider)
    provider.account = "other1234567890"
    with pytest.raises(ImportAuthorizationError, match="account changed"):
        service.snapshot(spec())
    provider.account = ACCOUNT
    provider.list_name = ""
    with pytest.raises(ImportAuthorizationError, match="list not verified"):
        service.snapshot(spec())


@pytest.mark.parametrize("permission", [
    "unsubscribed", "temp_hold", "deleted", "not_set", "pending_confirmation", "unknown",
])
def test_never_import_existing_suppressed_or_unknown(permission):
    provider = Provider()
    provider.permission = permission
    provider.exists = True
    with pytest.raises(ImportAuthorizationError, match="suppressed"):
        verifier(provider).snapshot(spec())
    assert all(call["method"] == "GET" for call in provider.calls)


def test_changed_membership_invalidates_original_suppression_receipt():
    provider = Provider()
    service = verifier(provider)
    before = service.snapshot(spec())
    provider.exists = True
    provider.memberships = [LIST_ID]
    with pytest.raises(ImportAuthorizationError, match="changed"):
        service.require_current_provider_match(
            account_binding_sha256=before.account_binding_sha256,
            specification=spec(), suppression_receipt_sha256=before.suppression_receipt_sha256,
        )


def test_paginated_exact_contact_search_is_not_sufficient_to_import():
    provider = Provider()
    provider.paginated = True
    with pytest.raises(ImportAuthorizationError, match="incomplete"):
        verifier(provider).snapshot(spec())


def test_large_pilot_import_fails_before_any_provider_read():
    provider = Provider()
    with pytest.raises(ImportAuthorizationError, match="bounded"):
        verifier(provider).snapshot(spec(MAX_VERIFIED_CONTACTS + 1))
    assert provider.calls == []


def test_list_membership_readback_is_per_contact_and_requires_current_account():
    provider = Provider()
    service = verifier(provider)
    assert service.readback_memberships(spec())[0]["status"] == "not_verified"
    provider.exists = True
    provider.memberships = [LIST_ID]
    assert service.readback_memberships(spec())[0]["status"] == "verified"
    provider.account = "attacker12345678"
    with pytest.raises(ImportAuthorizationError, match="account changed"):
        service.readback_memberships(spec())



def test_existing_contact_not_on_target_list_requires_separate_reconsent():
    provider = Provider()
    provider.exists = True
    provider.permission = "explicit"
    provider.memberships = []
    with pytest.raises(ImportAuthorizationError, match="list-specific re-consent"):
        verifier(provider).snapshot(spec())
