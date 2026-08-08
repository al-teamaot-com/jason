from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jason_openclaw.connector import OpenClawConnector
from jason_openclaw.ingress import GovernedOpenClawIngress


class Dispatcher:
    def __init__(self):
        self.calls = []

    def dispatch(self, request):
        self.calls.append(request)
        return {"ok": True}


class Authority:
    def evaluate(self, request):
        return "allowed"


class Policy:
    def __init__(self, decision="allowed"):
        self.decision = decision

    def evaluate(self, request):
        return self.decision


class Audit:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


class Replay:
    def __init__(self):
        self.seen = set()

    def claim(self, request_id):
        if request_id in self.seen:
            return False
        self.seen.add(request_id)
        return True


class Authenticator:
    def __init__(self, allowed=True):
        self.allowed = allowed

    def authenticate(self, envelope):
        if not self.allowed:
            raise ValueError("bad signature")
        return "machine-openclaw-prod"


@dataclass(frozen=True)
class DelegationResult:
    valid: bool
    reason_code: str


class DelegationValidator:
    def __init__(self, *, valid=True, reason="DELEGATION_VALID"):
        self.valid = valid
        self.reason = reason
        self.requests = []

    def validate(self, request):
        self.requests.append(request)
        return DelegationResult(self.valid, self.reason)


def envelope(principal_id="svc-openclaw-gateway", delegation_id=None):
    now = datetime.now(timezone.utc)
    value = {
        "request_id": "req-1",
        "correlation_id": "corr-1",
        "capability": "autotask.ticket.get",
        "requested_mode": "observe",
        "arguments": {"ticket_id": "1"},
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=2)).isoformat(),
        "nonce": "nonce-1",
        "principal": {
            "principal_id": principal_id,
            "channel": "openclaw",
            "external_user_id": "openclaw-machine-1",
            "organization_id": "aot",
            "client_id": "client-1",
        },
    }
    if delegation_id is not None:
        value["delegation_id"] = delegation_id
    return value


def build(*, auth=True, policy="allowed", bindings=None, delegation=None):
    dispatcher = Dispatcher()
    audit = Audit()
    connector = OpenClawConnector(
        dispatcher,
        Authority(),
        audit,
        Replay(),
        Policy(policy),
    )
    ingress = GovernedOpenClawIngress(
        connector=connector,
        authenticator=Authenticator(auth),
        audit=audit,
        machine_principal_bindings=(
            bindings
            if bindings is not None
            else {"machine-openclaw-prod": "svc-openclaw-gateway"}
        ),
        delegation_validator=delegation,
    )
    return ingress, dispatcher, audit


def test_authenticated_fresh_request_reaches_dispatch():
    ingress, dispatcher, audit = build()
    result = ingress.handle(envelope())
    assert result["status"] == "completed"
    assert len(dispatcher.calls) == 1
    assert audit.events[0][0] == "openclaw.transport_authenticated"


def test_bad_transport_identity_never_reaches_dispatch():
    ingress, dispatcher, _ = build(auth=False)
    result = ingress.handle(envelope())
    assert result["error_code"] == "transport_authentication_failed"
    assert dispatcher.calls == []


def test_expired_request_never_reaches_dispatch():
    ingress, dispatcher, _ = build()
    value = envelope()
    now = datetime.now(timezone.utc)
    value["issued_at"] = (now - timedelta(minutes=10)).isoformat()
    value["expires_at"] = (now - timedelta(minutes=5)).isoformat()
    result = ingress.handle(value)
    assert result["error_code"] == "request_expired"
    assert dispatcher.calls == []


def test_machine_identity_cannot_assert_human_without_delegation():
    ingress, dispatcher, audit = build()
    result = ingress.handle(envelope("person-al"))
    assert result["error_code"] == "delegation_required"
    assert dispatcher.calls == []
    assert audit.events[-1][1]["reason"] == "delegation_required"


def test_valid_delegation_allows_human_principal():
    delegation = DelegationValidator()
    ingress, dispatcher, audit = build(delegation=delegation)
    result = ingress.handle(envelope("person-al", "dlg-1"))
    assert result["status"] == "completed"
    assert len(dispatcher.calls) == 1
    assert delegation.requests[0].delegator_id == "person-al"
    assert delegation.requests[0].delegate_id == "svc-openclaw-gateway"
    assert audit.events[0][1]["delegation_id"] == "dlg-1"


def test_invalid_delegation_fails_closed():
    delegation = DelegationValidator(valid=False, reason="DELEGATION_SCOPE_MISMATCH")
    ingress, dispatcher, _ = build(delegation=delegation)
    result = ingress.handle(envelope("person-al", "dlg-bad"))
    assert result["error_code"] == "delegation_scope_mismatch"
    assert dispatcher.calls == []


def test_unbound_machine_identity_fails_closed():
    ingress, dispatcher, _ = build(bindings={})
    result = ingress.handle(envelope())
    assert result["error_code"] == "machine_principal_binding_missing"
    assert dispatcher.calls == []


def test_policy_denial_never_reaches_dispatch():
    ingress, dispatcher, _ = build(policy="denied")
    result = ingress.handle(envelope())
    assert result["error_code"] == "policy_denied"
    assert dispatcher.calls == []


def test_policy_can_require_human_approval():
    ingress, dispatcher, _ = build(policy="approval_required")
    result = ingress.handle(envelope())
    assert result["status"] == "approval_required"
    assert dispatcher.calls == []
