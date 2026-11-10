import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pmv3_work_engine", ROOT / "tools/pmv3_work_engine.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


NOW = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)


def test_success_runs_without_repeat_prompt():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-1", "build"))
    calls = []

    def handler(item, key):
        calls.append((item["id"], key))
        return module.Outcome("complete", receipt="ok-1")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    assert state["items"]["PMV3-1"]["phase"] == "complete"
    assert state["metrics"]["completed"] == 1
    assert len(calls) == 1


def test_transient_failure_retries_with_bounded_backoff():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-2", "transport"))
    calls = []

    def handler(item, key):
        calls.append(item["attempts"])
        if len(calls) == 1:
            return module.Outcome("retry", reason="HTTP transport failed")
        return module.Outcome("complete", receipt="ok-2")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    item = state["items"]["PMV3-2"]
    assert item["phase"] == "retry_wait"
    due = module.parse_time(item["next_attempt_at"])
    assert due == NOW + timedelta(seconds=30)

    module.execute_cycle(state, facts={}, handler=handler, now=due)
    assert state["items"]["PMV3-2"]["phase"] == "complete"
    assert len(calls) == 2


def test_waiting_dependency_wakes_automatically():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-3", "merge", dependency="checks_passed"))

    def handler(item, key):
        return module.Outcome("complete", receipt="ok-3")

    module.execute_cycle(state, facts={"checks_passed": False}, handler=handler, now=NOW)
    assert state["items"]["PMV3-3"]["phase"] == "waiting"

    module.execute_cycle(
        state,
        facts={"checks_passed": True},
        handler=handler,
        now=NOW + timedelta(minutes=1),
    )
    assert state["items"]["PMV3-3"]["phase"] == "complete"


def test_blocked_item_does_not_consume_other_capacity():
    state = module.empty_state()
    first = module.make_item("PMV3-4", "external", priority=1)
    first["phase"] = "failed_external"
    first["reason"] = "credentials required"
    module.admit(state, first)
    module.admit(state, module.make_item("PMV3-5", "independent", priority=2))

    def handler(item, key):
        return module.Outcome("complete", receipt="ok-5")

    module.execute_cycle(state, facts={}, handler=handler, capacity=1, now=NOW)
    assert state["items"]["PMV3-4"]["phase"] == "failed_external"
    assert state["items"]["PMV3-5"]["phase"] == "complete"


def test_crash_recovery_does_not_duplicate_completed_action():
    state = module.empty_state()
    item = module.make_item("PMV3-6", "deploy-candidate")
    module.admit(state, item)
    key = module.action_key("PMV3-6", "deploy-candidate", 1)
    state["items"]["PMV3-6"]["phase"] = "running"
    state["receipts"][key] = {
        "item_id": "PMV3-6",
        "receipt": "already-done",
        "recorded_at": module.iso(NOW),
    }
    called = False

    def handler(item, action_key):
        nonlocal called
        called = True
        return module.Outcome("complete", receipt="duplicate")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW + timedelta(minutes=2))
    assert state["items"]["PMV3-6"]["phase"] == "complete"
    assert called is False


def test_interrupted_action_without_receipt_is_readmitted():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-7", "recover", idempotent=True))
    state["items"]["PMV3-7"]["phase"] = "running"

    def handler(item, key):
        return module.Outcome("complete", receipt="ok-7")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    assert state["items"]["PMV3-7"]["phase"] == "complete"
    assert state["items"]["PMV3-7"]["attempts"] == 1


def test_external_authority_is_not_retried():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-8", "approval"))

    def handler(item, key):
        return module.Outcome(
            "external",
            reason="owner approval required",
            retry_class="owner_approval_required",
        )

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    assert state["items"]["PMV3-8"]["phase"] == "failed_external"
    assert state["items"]["PMV3-8"]["attempts"] == 1


def test_progress_percentage_measures_whole_inventory():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-9", "a"))
    module.admit(state, module.make_item("PMV3-10", "b"))
    state["items"]["PMV3-9"]["phase"] = "complete"
    assert module.progress_percent(state) == 50


def test_approval_required_work_does_not_run_without_teams():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "PMV3-11", "release", approval_required=True, approval_request_id="REQ-11"
    ))
    called = False

    def handler(item, key):
        nonlocal called
        called = True
        return module.Outcome("complete", receipt="should-not-run")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    assert called is False
    assert state["items"]["PMV3-11"]["phase"] == "runnable"
    assert state["metrics"]["runnable"] == 0


def test_non_teams_approval_is_rejected():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "PMV3-12", "release", approval_required=True, approval_request_id="REQ-12"
    ))
    try:
        module.record_teams_approval(
            state, "PMV3-12",
            request_id="REQ-12", decision="approve",
            actor_id="person-al", tenant_id="tenant-aot", receipt_id="receipt-12",
            verified=True, channel="ssh",
        )
    except ValueError as exc:
        assert "Teams" in str(exc)
    else:
        raise AssertionError("SSH approval must be rejected")


def test_verified_exact_teams_approval_allows_exact_work():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "PMV3-13", "release", approval_required=True, approval_request_id="REQ-13"
    ))
    module.record_teams_approval(
        state, "PMV3-13",
        request_id="REQ-13", decision="approve",
        actor_id="person-al", tenant_id="tenant-aot", receipt_id="receipt-13",
        verified=True,
    )

    def handler(item, key):
        return module.Outcome("complete", receipt="done-13")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    assert state["items"]["PMV3-13"]["phase"] == "complete"


def test_teams_deny_never_allows_execution():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "PMV3-14", "release", approval_required=True, approval_request_id="REQ-14"
    ))
    module.record_teams_approval(
        state, "PMV3-14",
        request_id="REQ-14", decision="deny",
        actor_id="person-al", tenant_id="tenant-aot", receipt_id="receipt-14",
        verified=True,
    )
    called = False

    def handler(item, key):
        nonlocal called
        called = True
        return module.Outcome("complete", receipt="should-not-run")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    assert called is False
    assert state["items"]["PMV3-14"]["phase"] == "runnable"


def test_mismatched_teams_request_cannot_approve():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "PMV3-15", "release", approval_required=True, approval_request_id="REQ-15"
    ))
    try:
        module.record_teams_approval(
            state, "PMV3-15",
            request_id="REQ-WRONG", decision="approve",
            actor_id="person-al", tenant_id="tenant-aot", receipt_id="receipt-15",
            verified=True,
        )
    except ValueError as exc:
        assert "mismatch" in str(exc)
    else:
        raise AssertionError("mismatched Teams request must be rejected")



def test_interrupted_non_idempotent_action_waits_for_reconciliation():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-16", "non-idempotent", idempotent=False))
    state["items"]["PMV3-16"]["phase"] = "running"
    called = False

    def handler(item, key):
        nonlocal called
        called = True
        return module.Outcome("complete", receipt="must-not-run")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    item = state["items"]["PMV3-16"]
    assert called is False
    assert item["phase"] == "waiting"
    assert item["dependency"] == "reconciliation_required"
    assert item["reason"] == "indeterminate_execution_requires_reconciliation"


def test_validation_failure_is_bounded_retryable():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-17", "validate"))
    calls = []

    def handler(item, key):
        calls.append(item["attempts"])
        if len(calls) == 1:
            return module.Outcome("retry", reason="regression test failed")
        return module.Outcome("complete", receipt="validation-ok")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    due = module.parse_time(state["items"]["PMV3-17"]["next_attempt_at"])
    assert state["items"]["PMV3-17"]["phase"] == "retry_wait"
    module.execute_cycle(state, facts={}, handler=handler, now=due)
    assert state["items"]["PMV3-17"]["phase"] == "complete"
    assert len(calls) == 2


# Owner-directed retirement of the mandatory Teams approval channel. These
# tests exercise the trusted-adapter boundary without accepting raw chat text.
def _owner_verification(item, *, decision="approve", **overrides):
    proof = {
        "issuer": "jason_entra_owner_authority",
        "authentication": "entra_oauth_bearer",
        "identity_status": "active",
        "owner_identity_id": "person-al",
        "microsoft_tenant_id": module.OWNER_TENANT_ID,
        "microsoft_object_id": module.OWNER_ENTRA_OBJECT_ID,
        "request_id": item["approval_request_id"],
        "action_scope_sha256": module.owner_approval_scope(item),
        "decision": decision,
        "receipt_id": "entra-verified-receipt-" + item["id"],
        "proof_sha256": "a" * 64,
    }
    proof.update(overrides)
    return proof


def test_verified_authenticated_owner_not_teams_can_release_exact_work():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "OWNER-A1", "read-only-release-pilot", approval_required=True,
        approval_request_id="owner-req-A1"))
    item = state["items"]["OWNER-A1"]
    module.record_authenticated_owner_approval(
        state, "OWNER-A1",
        presented_evidence={"opaque_signed_decision_reference": "test"},
        verified_decision=lambda ignored: _owner_verification(item),
    )
    assert module.approval_satisfied(item) is True
    executed = []
    module.execute_cycle(
        state, facts={},
        handler=lambda work, key: (
            executed.append(key) or module.Outcome("complete", receipt="test")
        ),
        now=NOW,
    )
    assert len(executed) == 1
    assert item["phase"] == "complete"
    assert item["approval"]["channel"] == "authenticated_owner"


def test_authenticated_owner_requires_separate_trusted_verifier():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "OWNER-A2", "release", approval_required=True, approval_request_id="A2"))
    try:
        module.record_authenticated_owner_approval(
            state, "OWNER-A2", presented_evidence={"verified": True},
            verified_decision=None,
        )
    except ValueError as exc:
        assert "verifier" in str(exc)
    else:
        raise AssertionError("missing verifier accepted")
    assert not module.approval_satisfied(state["items"]["OWNER-A2"])


def test_authenticated_owner_rejects_wrong_identity_tenant_scope_and_unverified():
    for field, invalid in (
        ("issuer", "untrusted_chat"),
        ("authentication", "chat_text"),
        ("identity_status", "inactive"),
        ("owner_identity_id", "person-anyone"),
        ("microsoft_object_id", "c848022d-e13b-4457-84b0-e2f5c00dcaf6"),
        ("microsoft_tenant_id", "00000000-0000-0000-0000-000000000000"),
        ("request_id", "different"),
        ("action_scope_sha256", "f" * 64),
        ("proof_sha256", "not-a-digest"),
        ("decision", "maybe"),
    ):
        state = module.empty_state()
        module.admit(state, module.make_item(
            "OWNER-A3", "release", approval_required=True, approval_request_id="A3"))
        item = state["items"]["OWNER-A3"]
        try:
            module.record_authenticated_owner_approval(
                state, "OWNER-A3",
                presented_evidence={"untrusted": "raw"},
                verified_decision=lambda ignored: _owner_verification(
                    item, **{field: invalid}),
            )
        except ValueError as exc:
            assert "not exact" in str(exc)
        else:
            raise AssertionError(field + " was unexpectedly accepted")
        assert not module.approval_satisfied(item)


def test_authenticated_owner_deny_never_dispatches():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "OWNER-A4", "release", approval_required=True, approval_request_id="A4"))
    item = state["items"]["OWNER-A4"]
    module.record_authenticated_owner_approval(
        state, "OWNER-A4", presented_evidence={},
        verified_decision=lambda ignored: _owner_verification(item, decision="deny"))
    assert module.approval_satisfied(item) is False
    called = []
    module.execute_cycle(
        state, facts={},
        handler=lambda work, key: (
            called.append(key) or module.Outcome("complete", receipt="invalid")),
        now=NOW)
    assert not called


def test_authenticated_owner_approval_replay_across_work_items_is_rejected():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "OWNER-A5", "release", approval_required=True, approval_request_id="A5"))
    module.admit(state, module.make_item(
        "OWNER-A6", "release", approval_required=True, approval_request_id="A6"))
    one, two = state["items"]["OWNER-A5"], state["items"]["OWNER-A6"]
    module.record_authenticated_owner_approval(
        state, "OWNER-A5", presented_evidence={},
        verified_decision=lambda _: _owner_verification(one, receipt_id="same-receipt"))
    try:
        module.record_authenticated_owner_approval(
            state, "OWNER-A6", presented_evidence={},
            verified_decision=lambda _: _owner_verification(two, receipt_id="same-receipt"))
    except ValueError as exc:
        assert "replay" in str(exc)
    else:
        raise AssertionError("duplicate verified receipt accepted")
    assert not module.approval_satisfied(two)


def test_authenticated_owner_approval_invalidated_by_action_change():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "OWNER-A7", "action-1", approval_required=True, approval_request_id="A7"))
    item = state["items"]["OWNER-A7"]
    module.record_authenticated_owner_approval(
        state, "OWNER-A7", presented_evidence={},
        verified_decision=lambda _: _owner_verification(item))
    assert module.approval_satisfied(item) is True
    item["action"] = "action-2"
    assert module.approval_satisfied(item) is False
    item["action"] = "action-1"
    item["generation"] = 2
    assert module.approval_satisfied(item) is False


def test_authenticated_owner_rejects_unsafe_owner_evidence_without_request():
    state = module.empty_state()
    module.admit(state, module.make_item(
        "OWNER-A8", "release", approval_required=True))
    try:
        module.record_authenticated_owner_approval(
            state, "OWNER-A8", presented_evidence={},
            verified_decision=lambda _: {"verified": True})
    except ValueError as exc:
        assert "request id" in str(exc)
    else:
        raise AssertionError("missing request ID accepted")
