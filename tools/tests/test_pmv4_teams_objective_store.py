"""Protected receipts and restart semantics in disposable storage only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import os
from pathlib import Path
import tempfile

import pytest

from test_pmv4_teams_objective_admission import case, NOW
from tools.pmv4_teams_objective_admission import TeamsObjectiveDenied, plan_digest
from tools.pmv4_teams_objective_store import RootObjectiveStore


@pytest.fixture
def store_case(case):
    original, envelope, sign, verify = case
    with tempfile.TemporaryDirectory(prefix="jason-objective-root-test-", dir="/tmp") as temp:
        root = Path(temp)
        root.chmod(0o700)
        store = RootObjectiveStore(root=root, production=False)
        staged = store.stage(approval_id=original["approval_id"], material=original["material"],
            at=NOW - timedelta(seconds=10), policy_digest="b" * 64,
            allowed_components=frozenset({"documentation-publisher"}),
            allowed_requesters=frozenset({"jason-release-manager"}),
            native_preflight=lambda candidate: True)
        store.record_delivery(approval_id=staged["approval_id"],
            provider_message_id=original["provider_message_id"], policy_digest="b" * 64,
            allowed_components=frozenset({"documentation-publisher"}))
        envelope["interaction"]["selections"]["card_challenge"] = staged["card_instance_challenge"]
        sign()
        yield store, staged, envelope, verify.ports


def claim(store_case, index, **options):
    store, staged, envelope, ports = store_case
    return store.claim(approval_id=staged["approval_id"], step_index=index,
        signed_envelope=envelope, at=NOW, verify_ports=ports,
        native_preflight=lambda *args: True, **options)


def native_verified(c):
    args = c["step_material"]["arguments"]
    return dict(status="verified", approval_id=c["approval_id"],
        plan_fingerprint=c["plan_fingerprint"], step_index=c["step_index"],
        claim_id=c["claim_id"], candidate_sha=args["candidate_sha"],
        scope_sha256=args["scope_sha256"], manifest_sha256=args["manifest_sha256"])


def finish(store_case, index):
    store, staged, _, _ = store_case
    return store.complete_from_native_readback(approval_id=staged["approval_id"],
        step_index=index, native_readback=native_verified)


def test_one_original_human_decision_reaches_verified_complete_after_restart(store_case):
    store, staged, _, _ = store_case
    first = claim(store_case, 0)
    assert first["already_verified"] is False
    decision_path = store.root / staged["approval_id"] / "verified-decision.json"
    original_decision = decision_path.read_bytes()
    finish(store_case, 0)
    restarted = RootObjectiveStore(root=store.root, production=False)
    next_case = (restarted, *store_case[1:])
    second = claim(next_case, 1)
    finish(next_case, 1)
    assert first["claim_id"] != second["claim_id"]
    assert decision_path.read_bytes() == original_decision
    assert restarted.status(approval_id=staged["approval_id"])["state"] == "verified_complete"
    assert claim(next_case, 0)["already_verified"] is True


def test_uncertain_native_outcome_requires_readback_before_retry(store_case):
    store, staged, _, _ = store_case
    claim(store_case, 0)
    restarted = (RootObjectiveStore(root=store.root, production=False), *store_case[1:])
    with pytest.raises(TeamsObjectiveDenied, match="INDETERMINATE"):
        claim(restarted, 0)
    assert store.status(approval_id=staged["approval_id"])["state"] == "indeterminate"
    finish(restarted, 0)
    assert claim(restarted, 0)["already_verified"] is True


def test_concurrent_root_step_has_only_one_native_claim(store_case):
    def attempt():
        try:
            claim(store_case, 0)
            return "claimed"
        except TeamsObjectiveDenied:
            return "denied"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["claimed", "denied"]


def test_native_failure_does_not_create_success(store_case):
    store, staged, _, _ = store_case
    claim(store_case, 0)
    with pytest.raises(TeamsObjectiveDenied, match="NATIVE_OUTCOME_NOT_VERIFIED"):
        store.complete_from_native_readback(approval_id=staged["approval_id"], step_index=0,
            native_readback=lambda c: dict(native_verified(c), status="rolled_back"))
    assert store.status(approval_id=staged["approval_id"])["state"] == "indeterminate"


def test_current_root_revocation_blocks_next_step_without_new_human_decision(store_case):
    store, staged, _, _ = store_case
    claim(store_case, 0); finish(store_case, 0)
    store.revoke_from_root(approval_id=staged["approval_id"], verified_revocation_sha256="5" * 64)
    with pytest.raises(TeamsObjectiveDenied, match="ROOT_PLAN_REVOKED"):
        claim(store_case, 1)
    assert store.status(approval_id=staged["approval_id"])["state"] == "revoked"


def test_native_preflight_failure_writes_no_decision_or_claim(store_case):
    store, staged, envelope, ports = store_case
    with pytest.raises(TeamsObjectiveDenied, match="NATIVE_PREFLIGHT"):
        store.claim(approval_id=staged["approval_id"], step_index=0, signed_envelope=envelope,
            at=NOW, verify_ports=ports, native_preflight=lambda *args: False)
    directory = store.root / staged["approval_id"]
    assert not (directory / "verified-decision.json").exists()
    assert not list(directory.glob("claim-*.json"))


def test_root_store_production_mode_cannot_be_enabled_from_worktree(store_case):
    store, _, _, _ = store_case
    with pytest.raises(TeamsObjectiveDenied, match="INSTALLED_ROOT_STORE_REQUIRED"):
        RootObjectiveStore(root=store.root, production=True)


def test_foreign_or_hardlinked_enrollment_is_rejected(store_case):
    store, staged, _, _ = store_case
    enrollment = store.root / staged["approval_id"] / "enrollment.json"
    os.link(enrollment, store.root / "foreign-hardlink")
    with pytest.raises(TeamsObjectiveDenied, match="ROOT_FILE_IDENTITY"):
        claim(store_case, 0)
