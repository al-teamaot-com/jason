import pytest

from connectors.constant_contact.import_activity import build_specification
from connectors.constant_contact.import_preflight import preflight
from connectors.constant_contact.import_authorization import (
    ImportAuthorizationError, prepare_authorized_claim,
)

LIST_ID = "11111111-2222-3333-4444-555555555555"
ACCOUNT = "a" * 64
SUPPRESSION = "b" * 64


def spec():
    p = preflight([{
        "email": "one@example.com", "marketing_consent": "explicit",
        "consent_evidence": "signed evidence",
    }])
    return build_specification(p, list_ids=[LIST_ID])


class Evidence:
    def __init__(self, reject=False):
        self.reject = reject
        self.calls = []
    def require_current_provider_match(self, **kwargs):
        self.calls.append(kwargs)
        if self.reject:
            raise ImportAuthorizationError("Provider suppression evidence changed")


class Approvals:
    def __init__(self, reject=False):
        self.reject = reject
        self.intents = []
    def require_exact_signed_approval(self, **kwargs):
        self.intents.append(kwargs["intent"])
        if self.reject:
            raise ImportAuthorizationError("Missing signed Teams approval")


class Ledger:
    def __init__(self):
        self.claims = set()
    def claim_once(self, *, intent_digest):
        if intent_digest in self.claims:
            raise ImportAuthorizationError("Replay blocked")
        self.claims.add(intent_digest)


def execute(approval=None, evidence=None, ledger=None, **overrides):
    values = {
        "requester_id": "aot-owner",
        "account_binding_sha256": ACCOUNT,
        "suppression_receipt_sha256": SUPPRESSION,
        "specification": spec(),
        "approvals": approval or Approvals(),
        "provider": evidence or Evidence(),
        "ledger": ledger or Ledger(),
    }
    values.update(overrides)
    return prepare_authorized_claim(**values)


def test_exact_approval_then_one_time_claim():
    ledger, approval, evidence = Ledger(), Approvals(), Evidence()
    first = execute(approval, evidence, ledger)
    assert len(first.intent_digest) == 64
    assert len(approval.intents) == 1
    assert approval.intents[0].specification_sha256 == first.specification.sha256
    with pytest.raises(ImportAuthorizationError, match="Replay"):
        execute(approval, evidence, ledger)


def test_denied_approval_never_claims():
    ledger = Ledger()
    with pytest.raises(ImportAuthorizationError, match="signed Teams"):
        execute(Approvals(reject=True), Evidence(), ledger)
    assert not ledger.claims


def test_suppression_mismatch_never_requests_approval():
    approvals = Approvals()
    with pytest.raises(ImportAuthorizationError, match="suppression"):
        execute(approvals, Evidence(reject=True), Ledger())
    assert approvals.intents == []


def test_invalid_account_binding_rejected():
    with pytest.raises(ImportAuthorizationError, match="digests"):
        execute(account_binding_sha256="missing")


def test_intent_change_when_suppression_receipt_changes():
    first = execute()
    second = execute(suppression_receipt_sha256="c" * 64)
    assert first.intent_digest != second.intent_digest
