from datetime import datetime, timedelta, timezone

from autonomous_remediation.playbook_autonomy_approval import (
    PlaybookAutonomyApproval, SQLitePlaybookAutonomyApprovalStore,
)
from jason_runtime.vulscan_v2_owner_promotion_gate import (
    V2_PLAYBOOK_ID, V2_PLAYBOOK_VERSION, V2_POLICY_ID, V2_TEAMS_CAPABILITY,
    VulscanV2OwnerPromotionGate,
)

NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)
OWNER = "person-entra-verified-owner"


def approved(**changes):
    values = dict(
        approval_id="v2-owner-approval-1",
        playbook_id=V2_PLAYBOOK_ID,
        playbook_version=V2_PLAYBOOK_VERSION,
        policy_id=V2_POLICY_ID,
        allowed_capabilities=(V2_TEAMS_CAPABILITY,),
        approved_by=OWNER,
        approved_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=7),
        status="approved",
    )
    values.update(changes)
    return PlaybookAutonomyApproval(**values)


def guard(store, *, owner_ok=True, recipient_ok=True):
    return VulscanV2OwnerPromotionGate(
        approval_store=store,
        owner_authorized=lambda identity: owner_ok and identity == OWNER,
        recipient_identity_ready=lambda: recipient_ok,
        now=lambda: NOW,
    )


def test_absent_authority_defaults_disabled(tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotion.db")
    assert guard(store)() is False


def test_exact_owner_version_and_send_scope_pass_read_only(tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotion.db")
    store.put(approved())
    assert guard(store)() is True
    assert guard(store, recipient_ok=False)() is False
    assert guard(store, owner_ok=False)() is False


def test_wrong_version_wrong_scope_or_wrong_owner_never_promotes(tmp_path):
    cases = (
        dict(playbook_version="1.0.0"),
        dict(policy_id="playbook-autonomy:other"),
        dict(approved_by="other-owner"),
        dict(allowed_capabilities=(V2_TEAMS_CAPABILITY, "service.ticket.update")),
        dict(allowed_capabilities=("service.ticket.note.create",)),
        dict(expires_at=NOW - timedelta(minutes=1)),
        dict(status="revoked"),
    )
    for i, changes in enumerate(cases):
        store = SQLitePlaybookAutonomyApprovalStore(tmp_path / f"{i}.db")
        store.put(approved(**changes))
        assert guard(store)() is False


def test_revoke_invalidates_standing_activation(tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotion.db")
    store.put(approved())
    assert guard(store)() is True
    store.revoke("v2-owner-approval-1", revoked_by=OWNER,
                 reason="testing-revocation")
    assert guard(store)() is False


def test_store_unavailable_fails_closed():
    class Missing:
        def find_scope_approved(self, **kwargs):
            raise OSError("governance store unavailable")
    assert guard(Missing())() is False
