from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from connectors.constant_contact.import_authorization import (
    ExactImportIntent, ImportAuthorizationError,
)
from jason_runtime.constant_contact_teams_approval import (
    ExistingTeamsPlanGrantAdapter,
)

NOW = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)


def intent():
    return ExactImportIntent(
        account_binding_sha256="a"*64,
        specification_sha256="b"*64,
        preview_digest="c"*64,
        suppression_receipt_sha256="d"*64,
        list_ids=("11111111-2222-3333-4444-555555555555",),
        contact_count=1,
    )


class Ledger:
    def __init__(self, denied=False):
        self.denied = denied
        self.calls = []
    def require_grant(self, step, *, plan_fingerprint, now):
        self.calls.append((step, plan_fingerprint, now))
        if self.denied:
            raise PermissionError("revoked")


class Repo:
    def __init__(self, proposal):
        self.proposal = proposal
    def require(self, approval_id):
        assert approval_id == "planapproval-test"
        return self.proposal


def make_proposal(**kwargs):
    scope = SimpleNamespace(
        plan_id="plan-1", organization_id="aot", policy_digest="policy",
        allowed_capabilities=frozenset({"marketing.contact.import"}),
        allowed_clients=frozenset(), max_risk=5,
        production_allowed=True, expires_at=NOW+timedelta(minutes=15),
    )
    values = {
        "approval_id": "planapproval-test", "organization_id": "aot",
        "requester_id": "aot-owner", "capability": "marketing.contact.import",
        "scope": scope, "plan_fingerprint": intent().digest(),
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def adapter(proposal=None, denied=False):
    ledger = Ledger(denied)
    return ExistingTeamsPlanGrantAdapter(
        ledger=ledger, proposals=Repo(proposal or make_proposal()),
        server_owned_approval_id="planapproval-test", clock=lambda: NOW,
    ), ledger


def test_exact_existing_teams_grant_is_required():
    approval, ledger = adapter()
    approval.require_exact_signed_approval(requester_id="aot-owner", intent=intent())
    assert len(ledger.calls) == 1
    assert ledger.calls[0][1] == intent().digest()
    assert ledger.calls[0][0].production is True


@pytest.mark.parametrize("mutations", [
    {"requester_id": "other"},
    {"capability": "marketing.contact.search"},
    {"plan_fingerprint": "wrong"},
    {"organization_id": "external"},
])
def test_mismatched_server_proposal_refused(mutations):
    approval, ledger = adapter(make_proposal(**mutations))
    with pytest.raises(ImportAuthorizationError, match="mismatch"):
        approval.require_exact_signed_approval(requester_id="aot-owner", intent=intent())
    assert not ledger.calls


def test_revoked_expired_or_missing_grant_denied():
    approval, ledger = adapter(denied=True)
    with pytest.raises(ImportAuthorizationError, match="missing or expired"):
        approval.require_exact_signed_approval(requester_id="aot-owner", intent=intent())
