import pytest

from connectors.constant_contact.import_activity import build_specification
from connectors.constant_contact.import_preflight import preflight
from connectors.constant_contact.import_authorization import ImportAuthorizationError
from connectors.constant_contact.import_dispatch import (
    UnwiredConstantContactImportDispatcher, ImportContractError, ENDPOINT,
)

LIST_ID = "11111111-2222-3333-4444-555555555555"
ACTIVITY = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def specification():
    p = preflight([{"email": "one@example.com",
                    "marketing_consent": "explicit", "consent_evidence": "form receipt"}])
    return build_specification(p, list_ids=[LIST_ID])


class Approval:
    def __init__(self, deny=False):
        self.deny = deny
    def require_exact_signed_approval(self, **kw):
        if self.deny:
            raise ImportAuthorizationError("Teams approval denied")


class Evidence:
    def __init__(self, deny=False):
        self.deny = deny
    def require_current_provider_match(self, **kw):
        if self.deny:
            raise ImportAuthorizationError("Suppression changed")


class Ledger:
    def __init__(self):
        self.claims = set()
        self.activities = {}
    def claim_once(self, *, intent_digest):
        if intent_digest in self.claims:
            raise ImportAuthorizationError("Replay blocked")
        self.claims.add(intent_digest)
    def record_dispatched(self, *, intent_digest, activity_id):
        assert intent_digest in self.claims
        self.activities[intent_digest] = activity_id


class Transport:
    def __init__(self, broken=False):
        self.calls = []
        self.broken = broken
    def request(self, **kwargs):
        self.calls.append(kwargs)
        if self.broken:
            raise ConnectionError("ambiguous HTTP result")
        if kwargs["method"] == "POST":
            return {"activity_id": ACTIVITY, "state": "initialized"}
        return {"activity_id": ACTIVITY, "state": "completed",
                "percent_done": 100, "completed_at": "2026-11-09T20:00:00Z",
                "activity_errors": []}


def adapter(denied=False, blocked=False, broken=False):
    ledger, transport = Ledger(), Transport(broken)
    service = UnwiredConstantContactImportDispatcher(
        approval=Approval(denied), evidence=Evidence(blocked),
        ledger=ledger, transport=transport,
    )
    return service, ledger, transport


def request(service):
    return service.submit_once(requester_id="aot-owner",
        account_binding_sha256="a" * 64, suppression_receipt_sha256="b" * 64,
        specification=specification(), access_token="fake-token")


def test_approved_import_submits_only_once_then_reads_activity():
    svc, ledger, transport = adapter()
    receipt = request(svc)
    assert transport.calls[0]["method"] == "POST"
    assert transport.calls[0]["url"] == ENDPOINT
    assert transport.calls[0]["json"]["list_ids"] == [LIST_ID]
    assert ledger.activities[receipt.intent_digest] == ACTIVITY
    assert svc.read_activity(activity_id=ACTIVITY, access_token="fake-token")["state"] == "activity_complete_unverified"
    with pytest.raises(ImportAuthorizationError, match="Replay"):
        request(svc)
    assert len([x for x in transport.calls if x["method"] == "POST"]) == 1


@pytest.mark.parametrize("denied,blocked", [(True, False), (False, True)])
def test_unapproved_or_suppressed_import_never_reaches_provider(denied, blocked):
    svc, ledger, transport = adapter(denied=denied, blocked=blocked)
    with pytest.raises(ImportAuthorizationError):
        request(svc)
    assert transport.calls == []


def test_ambiguous_post_never_redispatches():
    svc, ledger, transport = adapter(broken=True)
    with pytest.raises(ConnectionError):
        request(svc)
    with pytest.raises(ImportAuthorizationError, match="Replay"):
        request(svc)
    assert len(transport.calls) == 1
    assert len(ledger.claims) == 1


def test_bad_activity_id_cannot_poll():
    svc, ledger, transport = adapter()
    with pytest.raises(ImportContractError):
        svc.read_activity(activity_id="../contacts", access_token="fake-token")
    assert transport.calls == []
