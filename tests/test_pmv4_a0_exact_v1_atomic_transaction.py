"""Real existing native v1 single signed whole-release -> three A0 effects."""
from datetime import timedelta
from pathlib import Path

import pytest

from tools.pmv4_a0_exact_v1_atomic_transaction import OneOwnerV1ExactRelease
from tools.pmv4_a0_one_release_v1_proof import issue_source_only_existing_v1_proof
from tools.pmv4_a0_atomic_plan_transaction import A0AtomicTransactionDenied
from test_pmv4_a0_atomic_plan_transaction import (
    atomic, ThreeRealDisposableFileEffects,
)
from test_pmv4_a0_atomic_actual_root_components import real_three
from test_pmv4_owner_objective_end_to_end import AT, enrolled
from kernel.signed_owner_release import OWNER_OID

AUTH_ID="owner-mcp-" + "f"*32


def one_proof(env):
    verified = env["verifier"](env["token"])
    assert verified["oid"] == OWNER_OID
    return issue_source_only_existing_v1_proof(
        approval_id=AUTH_ID, signer_key=env["owner_key"],
        verified_owner_oid=verified["oid"], at=AT,
        independent_entra_owner_was_verified=True,
        confirmed_exact_full_plan=True,
    )


def test_shortest_one_existing_v1_owner_signature_no_v2_child_signatures(atomic):
    env, unused_v2, provider, root = atomic
    original_consent_count = len(env["consents"])
    proof = one_proof(env)
    folder=root/"one-original-v1-native-release"
    folder.mkdir(mode=0o700)
    executor=OneOwnerV1ExactRelease(
        directory=folder,
        signed_v1_whole_release=proof,
        pinned_public_key=env["owner_key"].public_key(),
        at=AT+timedelta(seconds=1),
    )
    a=ThreeRealDisposableFileEffects(root)
    outcome=executor.execute(adapters=a, at=AT+timedelta(seconds=1))
    assert outcome["status"]=="three_exact_v1_signed_actions_verified_together"
    assert outcome["owner_approval_id"]==AUTH_ID
    assert outcome["additional_owner_decisions"]==0
    assert len(env["consents"])==original_consent_count
    assert all(a.verify_installed(i) for i in range(3))
    assert executor._read_events()[-1]["action"]=="committed"
    with pytest.raises(A0AtomicTransactionDenied,match="ONE_RELEASE_ALREADY_CLAIMED"):
        executor.execute(adapters=a,at=AT+timedelta(seconds=1))


@pytest.mark.parametrize("fault", [0,1,2])
def test_one_native_v1_signed_release_failure_uses_original_rollback(atomic,fault):
    env, unused_v2, provider, root = atomic
    folder=root/"one-native-signed-release-rollback"
    folder.mkdir(mode=0o700)
    x=OneOwnerV1ExactRelease(
        directory=folder,signed_v1_whole_release=one_proof(env),
        pinned_public_key=env["owner_key"].public_key(),
        at=AT+timedelta(seconds=1),
    )
    a=ThreeRealDisposableFileEffects(root,fault=fault)
    with pytest.raises(InterruptedError):
        x.execute(adapters=a,at=AT+timedelta(seconds=1))
    assert all(a.verify_absent(i) for i in range(3))
    assert x._read_events()[-1]["action"]=="aborted"


def test_expired_signed_whole_plan_does_not_start_native_action(atomic):
    env, _, _, root=atomic
    folder=root/"expired-v1-root"
    folder.mkdir(mode=0o700)
    with pytest.raises(PermissionError):
        OneOwnerV1ExactRelease(
            directory=folder,signed_v1_whole_release=one_proof(env),
            pinned_public_key=env["owner_key"].public_key(),
            at=AT+timedelta(minutes=16),
        )
    assert not (folder/"pmv4-stage-a0-atomic-release.jsonl").exists()


def test_production_root_not_enabled_by_cryptographic_success(atomic):
    env, _, _, root=atomic
    folder=root/"no-v1-prod-boundary"
    folder.mkdir(mode=0o700)
    with pytest.raises(A0AtomicTransactionDenied,match="PRODUCTION_CONSUMER_NOT_DEPLOYED"):
        OneOwnerV1ExactRelease(
            directory=folder,signed_v1_whole_release=one_proof(env),
            pinned_public_key=env["owner_key"].public_key(),
            at=AT+timedelta(seconds=1),production=True,
        )


@pytest.mark.parametrize("fault", [None,0,1,2])
def test_v1_whole_release_runs_actual_root_bootstrap_closure_and_native_A0(
    real_three, fault,
):
    env, old_v2, provider, make_adapter = real_three
    parent=one_proof(env)
    folder=old_v2.directory.parent/"exact-one-v1-native-release"
    folder.mkdir(mode=0o700)
    x=OneOwnerV1ExactRelease(
        directory=folder,signed_v1_whole_release=parent,
        pinned_public_key=env["owner_key"].public_key(),
        at=AT+timedelta(seconds=1),
    )
    a=make_adapter(fault=fault)
    initial_consents=len(env["consents"])
    try:
        if fault is None:
            out=x.execute(adapters=a,at=AT+timedelta(seconds=1))
            assert out["status"]=="three_exact_v1_signed_actions_verified_together"
            assert all(a.verify_installed(i) for i in range(3))
            assert x._read_events()[-1]["action"]=="committed"
        else:
            with pytest.raises(InterruptedError):
                x.execute(adapters=a,at=AT+timedelta(seconds=1))
            assert all(a.verify_absent(i) for i in range(3))
            assert x._read_events()[-1]["action"]=="aborted"
        assert len(env["consents"])==initial_consents
        with pytest.raises(A0AtomicTransactionDenied,match="ONE_RELEASE_ALREADY_CLAIMED"):
            x.execute(adapters=a,at=AT+timedelta(seconds=1))
    finally:
        a.close()
