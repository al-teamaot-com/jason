from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from connectors.constant_contact.import_authorization import (
    ExactImportIntent, ImportAuthorizationError,
)
from jason_runtime.constant_contact_teams_approval import (
    ExistingVerifiedPlanGrantAdapter,
)

NOW = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)
PLAN_SHA = "9" * 64
APPROVAL_ID = "planapproval-test"


def intent():
    return ExactImportIntent(
        account_binding_sha256="a" * 64,
        specification_sha256="b" * 64,
        preview_digest="c" * 64,
        suppression_receipt_sha256="d" * 64,
        list_ids=("11111111-2222-3333-4444-555555555555",),
        contact_count=1,
    )


def approved_args():
    i = intent()
    return {
        "work_id": "trusted-work-test",
        "intent_digest": i.digest(),
        "account_binding_sha256": i.account_binding_sha256,
        "specification_sha256": i.specification_sha256,
        "preview_digest": i.preview_digest,
        "suppression_receipt_sha256": i.suppression_receipt_sha256,
        "list_ids": list(i.list_ids),
        "contact_count": i.contact_count,
    }


class Ledger:
    def __init__(self, denied=False, missing=False, revoked=False):
        self.denied, self.missing, self.revoked = denied, missing, revoked
        self.calls = []

    def require_grant(self, step, *, plan_fingerprint, now):
        self.calls.append((step, plan_fingerprint, now))
        if self.denied:
            raise PermissionError("Grant denied")

    def decision_receipt(self, approval_id):
        if self.missing:
            return None
        return {
            "approval_id": approval_id,
            "approver_identity_id": "authenticated-owner",
            "plan_fingerprint": PLAN_SHA,
            "revoked_at": NOW if self.revoked else None,
        }


class Repo:
    def __init__(self, proposal):
        self.proposal = proposal

    def require(self, approval_id):
        assert approval_id == APPROVAL_ID
        return self.proposal


class RequestRepo:
    def __init__(self, request, tampered=False):
        self.request, self.tampered = request, tampered
        self.verifications = []

    def verify_proposal(self, proposal):
        self.verifications.append(proposal.approval_id)
        if self.tampered:
            raise PermissionError("Canonical plan material has changed")

    def steps(self, approval_id):
        assert approval_id == APPROVAL_ID
        return (self.request,)


def make_objects(**changes):
    scope = SimpleNamespace(
        plan_id="plan-1", organization_id="aot", policy_digest="policy",
        allowed_capabilities=frozenset({"marketing.contact.import"}),
        allowed_clients=frozenset(), max_risk=2,
        production_allowed=True, expires_at=NOW + timedelta(minutes=15),
    )
    props = {
        "approval_id": APPROVAL_ID, "organization_id": "aot",
        "requester_id": "aot-owner", "capability": "marketing.contact.import",
        "client_id": None, "scope": scope, "plan_fingerprint": PLAN_SHA,
    }
    props.update(changes)
    request = SimpleNamespace(
        principal_id="aot-owner", organization_id="aot", client_id=None,
        capability_name="marketing.contact.import", permission_mode="execute",
        arguments=approved_args(),
    )
    return SimpleNamespace(**props), request


def adapter(proposal=None, request=None, denied=False, missing=False,
            revoked=False, tampered=False):
    default_proposal, default_request = make_objects()
    ledger = Ledger(denied, missing, revoked)
    requests = RequestRepo(request or default_request, tampered=tampered)
    approval = ExistingVerifiedPlanGrantAdapter(
        ledger=ledger, proposals=Repo(proposal or default_proposal),
        requests=requests, server_owned_approval_id=APPROVAL_ID,
        server_owned_work_id="trusted-work-test", clock=lambda: NOW,
    )
    return approval, ledger, requests


def test_valid_canonical_plan_grant_binds_import_without_conflating_two_digests():
    approval, ledger, requests = adapter()
    assert PLAN_SHA != intent().digest()
    approval.require_exact_signed_approval(
        requester_id="aot-owner", intent=intent(),
    )
    assert requests.verifications == [APPROVAL_ID]
    assert len(ledger.calls) == 1
    assert ledger.calls[0][1] == PLAN_SHA
    assert ledger.calls[0][0].production


@pytest.mark.parametrize("changes", [
    {"requester_id": "other"},
    {"capability": "marketing.contact.search"},
    {"organization_id": "external"},
    {"client_id": "client-a"},
])
def test_proposal_identity_or_scope_change_refused(changes):
    p, _ = make_objects(**changes)
    approval, ledger, _ = adapter(proposal=p)
    with pytest.raises(ImportAuthorizationError, match="mismatch"):
        approval.require_exact_signed_approval(
            requester_id="aot-owner", intent=intent(),
        )
    assert not ledger.calls


@pytest.mark.parametrize("key,value", [
    ("intent_digest", "bad"),
    ("account_binding_sha256", "0" * 64),
    ("suppression_receipt_sha256", "f" * 64),
    ("list_ids", []),
    ("contact_count", 12),
])
def test_modified_import_parameters_never_use_approved_grant(key, value):
    _, req = make_objects()
    req.arguments[key] = value
    approval, ledger, _ = adapter(request=req)
    with pytest.raises(ImportAuthorizationError, match="mismatch"):
        approval.require_exact_signed_approval(
            requester_id="aot-owner", intent=intent(),
        )
    assert not ledger.calls


@pytest.mark.parametrize("flags", [
    {"denied": True}, {"missing": True}, {"revoked": True},
    {"tampered": True},
])
def test_denial_or_changed_canonical_plan_fails_closed(flags):
    approval, _, _ = adapter(**flags)
    with pytest.raises(ImportAuthorizationError):
        approval.require_exact_signed_approval(
            requester_id="aot-owner", intent=intent(),
        )
