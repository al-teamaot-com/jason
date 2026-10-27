"""Manual Production Manager scope review must fail closed before production mutation."""
import pytest

from test_release_manager_host_runner import runner, SHA_A, SHA_B


def record():
    return {
        "release_id": "release-manual-123",
        "state": "production_eligible",
        "rollback_sha": SHA_B,
        "release_candidate": {"candidate_sha": SHA_A},
    }


def reviewed_record():
    item = record()
    item["manual_scope_review"] = {
        "schema_version": "1.0",
        "candidate_sha": SHA_A,
        "baseline_sha": SHA_B,
        "scope_sha256": "c" * 64,
        "included_prs": [42],
        "included_commits": [],
        "acknowledged_prs": [87],
        "acknowledged_worktrees": [],
    }
    return item


def test_missing_manual_review_blocks_before_any_mutation(monkeypatch, tmp_path):
    changes = []
    lock = object()
    monkeypatch.setattr(runner, "require_owner_production_deployment_unfrozen", lambda p: None)
    monkeypatch.setattr(runner, "acquire_production_transaction_lock",
                        lambda repo, state, item: (changes.append("locked"), lock)[1])
    monkeypatch.setattr(runner, "release_production_transaction_lock",
                        lambda value: changes.append("unlocked"))
    def mutate(*args, **kwargs):
        raise AssertionError("unreviewed release must not modify production")
    monkeypatch.setattr(runner, "reconcile_stopped_rollback_retention", mutate)
    monkeypatch.setattr(runner, "require_current_protected_release_source", mutate)
    with pytest.raises(runner.ReleaseManagerError, match="scope.*missing|review is missing"):
        runner.deploy_production(tmp_path, tmp_path, record())
    assert changes == ["locked", "unlocked"]


def test_valid_review_is_recomputed_under_lock(monkeypatch, tmp_path):
    observed = []
    def review(repo, root, item, **kwargs):
        observed.append(kwargs)
        return {"status": "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED",
                "scope_sha256": "c" * 64}
    monkeypatch.setattr(runner, "manual_release_scope_review", review)
    runner.require_current_manual_scope_review(tmp_path, tmp_path, reviewed_record())
    assert observed[0]["include_prs"] == (42,)
    assert observed[0]["acknowledged_prs"] == (87,)


def test_changed_overlaps_invalidate_earlier_scope_review(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "manual_release_scope_review",
                        lambda *args, **kwargs: {
                            "status": "BLOCKED_SCOPE", "scope_sha256": "d" * 64
                        })
    with pytest.raises(runner.ReleaseManagerError, match="scope changed"):
        runner.require_current_manual_scope_review(tmp_path, tmp_path, reviewed_record())


def test_modified_scope_digest_invalidates_earlier_review(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "manual_release_scope_review",
                        lambda *args, **kwargs: {
                            "status": "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED",
                            "scope_sha256": "d" * 64,
                        })
    with pytest.raises(runner.ReleaseManagerError, match="scope changed"):
        runner.require_current_manual_scope_review(tmp_path, tmp_path, reviewed_record())


def test_scope_review_for_different_sha_is_rejected(monkeypatch, tmp_path):
    item = reviewed_record()
    item["manual_scope_review"]["candidate_sha"] = SHA_B
    monkeypatch.setattr(runner, "manual_release_scope_review",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("mismatch must deny before source reads")
                        ))
    with pytest.raises(runner.ReleaseManagerError, match="different release"):
        runner.require_current_manual_scope_review(tmp_path, tmp_path, item)


def test_manual_source_review_never_substitutes_owner_deployment_authorization(monkeypatch, tmp_path):
    # Source review can be green; the separate Owner freeze is authoritative.
    monkeypatch.setattr(runner, "require_current_manual_scope_review",
                        lambda *args: (_ for _ in ()).throw(
                            AssertionError("freeze must gate before reviewing source")
                        ))
    (tmp_path / "production-deployment-freeze").touch()
    with pytest.raises(runner.ReleaseManagerError, match="owner production deployment freeze"):
        runner.deploy_production(tmp_path, tmp_path, reviewed_record())
