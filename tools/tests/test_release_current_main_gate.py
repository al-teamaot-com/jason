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
