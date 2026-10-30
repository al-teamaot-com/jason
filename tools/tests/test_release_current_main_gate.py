"""Release admission regressions: no stale/manual promotion may drop recent work."""

import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_release_manager_host_runner import runner, SHA_A, SHA_B


def record(candidate=SHA_A, baseline=SHA_B):
    return {
        "release_id": "release-test",
        "state": "production_eligible",
        "release_candidate": {"candidate_sha": candidate},
        "rollback_sha": baseline,
    }


def test_current_main_descendant_candidate_admitted(monkeypatch, tmp_path):
    ancestry = Mock(return_value=subprocess.CompletedProcess(["git"], 0))
    monkeypatch.setattr(runner, "authoritative_auto_promotion_head", lambda repo: SHA_A)
    monkeypatch.setattr(runner.subprocess, "run", ancestry)
    runner.require_current_protected_release_source(tmp_path, record())
    args = ancestry.call_args.args[0]
    assert args == ["git", "merge-base", "--is-ancestor", SHA_B, SHA_A]
    assert ancestry.call_args.kwargs["cwd"] == tmp_path


def test_stale_prepared_candidate_rejected_even_if_owner_approved(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "authoritative_auto_promotion_head", lambda repo: SHA_B)
    ancestry = Mock(side_effect=AssertionError("stale candidate must not reach baseline check"))
    monkeypatch.setattr(runner.subprocess, "run", ancestry)
    with pytest.raises(runner.ReleaseManagerError, match="behind protected main"):
        runner.require_current_protected_release_source(tmp_path, record())
    ancestry.assert_not_called()


def test_non_descendant_candidate_cannot_replace_current_production(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "authoritative_auto_promotion_head", lambda repo: SHA_A)
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 1))
    with pytest.raises(runner.ReleaseManagerError, match="does not descend"):
        runner.require_current_protected_release_source(tmp_path, record())


@pytest.mark.parametrize("bad_candidate,bad_baseline", [("bad", SHA_B), (SHA_A, "bad")])
def test_non_immutable_candidate_or_baseline_is_rejected(monkeypatch, tmp_path, bad_candidate, bad_baseline):
    monkeypatch.setattr(runner, "authoritative_auto_promotion_head",
                        Mock(side_effect=AssertionError("must reject before network call")))
    with pytest.raises(runner.ReleaseManagerError, match="SHA is invalid"):
        runner.require_current_protected_release_source(
            tmp_path, record(candidate=bad_candidate, baseline=bad_baseline)
        )


def test_both_manual_and_automatic_promotion_are_gated_before_mutation(monkeypatch, tmp_path):
    sentinel_lock = object()
    calls = []
    monkeypatch.setattr(runner, "acquire_production_transaction_lock",
                        lambda repo, root, item: (calls.append("lock"), sentinel_lock)[1])
    monkeypatch.setattr(runner, "release_production_transaction_lock",
                        lambda handle: calls.append("unlock"))
    monkeypatch.setattr(runner, "require_current_manual_scope_review",
                        lambda repo, root, item: None)
    monkeypatch.setattr(runner, "require_current_protected_release_source",
                        lambda repo, item: (_ for _ in ()).throw(
                            runner.ReleaseManagerError("superseded candidate")
                        ))
    monkeypatch.setattr(runner, "require_host_reconciler_ready",
                        Mock(side_effect=AssertionError("must not mutate host")))
    monkeypatch.setattr(runner, "reconcile_stopped_rollback_retention",
                        Mock(side_effect=AssertionError("must not touch containers")))
    with pytest.raises(runner.ReleaseManagerError, match="superseded candidate"):
        runner.deploy_production(tmp_path, tmp_path, record())
    assert calls == ["lock", "unlock"]


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_owner_release_freeze_fails_closed_for_any_existing_marker(tmp_path, kind):
    marker = tmp_path / "production-deployment-freeze"
    if kind == "file":
        marker.write_text("owner ordered all production deployments halted")
    elif kind == "directory":
        marker.mkdir()
    else:
        marker.symlink_to(tmp_path / "nonexistent-target")
    with pytest.raises(runner.ReleaseManagerError, match="manual and automatic promotions"):
        runner.require_owner_production_deployment_unfrozen(tmp_path)


def test_owner_release_freeze_denies_before_acquiring_production_lock(monkeypatch, tmp_path):
    (tmp_path / "production-deployment-freeze").touch()
    acquire = Mock(side_effect=AssertionError("production lock must not be acquired"))
    source = Mock(side_effect=AssertionError("no network/source reads permitted"))
    mutation = Mock(side_effect=AssertionError("no production state may change"))
    monkeypatch.setattr(runner, "acquire_production_transaction_lock", acquire)
    monkeypatch.setattr(runner, "require_current_protected_release_source", source)
    monkeypatch.setattr(runner, "reconcile_stopped_rollback_retention", mutation)
    with pytest.raises(runner.ReleaseManagerError, match="owner production deployment freeze"):
        runner.deploy_production(tmp_path, tmp_path, record())
    acquire.assert_not_called()
    source.assert_not_called()
    mutation.assert_not_called()


def test_freeze_created_while_waiting_for_lock_still_denies(monkeypatch, tmp_path):
    acquired = []
    sentinel = object()

    def acquire(repo, state_root, item):
        acquired.append("lock")
        (state_root / "production-deployment-freeze").touch()
        return sentinel

    monkeypatch.setattr(runner, "acquire_production_transaction_lock", acquire)
    monkeypatch.setattr(runner, "release_production_transaction_lock",
                        lambda lock: acquired.append("unlock"))
    side = Mock(side_effect=AssertionError("must not attempt source or mutation"))
    monkeypatch.setattr(runner, "require_current_protected_release_source", side)
    monkeypatch.setattr(runner, "reconcile_stopped_rollback_retention", side)
    with pytest.raises(runner.ReleaseManagerError, match="freeze is active"):
        runner.deploy_production(tmp_path, tmp_path, record())
    assert acquired == ["lock", "unlock"]
    side.assert_not_called()


def test_manual_mode_incident_hold_is_distinct_from_global_owner_freeze(tmp_path):
    # The existing owner-approved manual mode must not accidentally become
    # permanently blocked merely because unattended promotions are paused.
    (tmp_path / "auto-promotion-incident-hold").write_text("automated only")
    runner.require_owner_production_deployment_unfrozen(tmp_path)


def test_owner_freeze_does_not_require_undoing_emergency_baseline_recovery(tmp_path):
    (tmp_path / "production-deployment-freeze").touch()
    source = (tmp_path.parent / "release_manager_host_runner.py")
    # Source contract: all-deployments freeze belongs to deploy_production only.
    # Baseline recovery has a separate reviewed authority and must remain viable.
    from pathlib import Path
    controller = (Path(__file__).resolve().parents[1] / "release_manager_host_runner.py").read_text()
    recover = controller[controller.index("def recover_missing_last_known_good("):
                         controller.index("\ndef ", controller.index("def recover_missing_last_known_good(") + 5)]
    assert "require_owner_production_deployment_unfrozen" not in recover
