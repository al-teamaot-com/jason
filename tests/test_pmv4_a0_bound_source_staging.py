"""Current-main sparse staging shares the one approved atomic A0 transaction.

No production root writes, no sudo, no real Owner issuance in these tests.
"""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_a0_exact_v1_root_release as root
from tools import pmv4_stage_a0_one_owner_review as review
from tools import pmv4_a0_one_release_v1_proof as signer


def test_source_staging_is_signed_in_original_single_owner_release():
    packet = review.exact_contract()
    staging = packet["source_staging"]
    assert packet["expected_existing_pinned_source_files"] == 0
    assert staging == root.SOURCE_STAGE
    assert staging["old_one_shot_audit_reused"] is False
    assert staging["file_count"] == 13
    assert staging["candidate_sha"] == review.SOURCE
    assert staging["archive_sha256"] == root.SPARSE_ARCHIVE_SHA
    assert staging["scope_sha256"] == root.SPARSE_SCOPE
    assert packet["owner_decisions"] == 1
    assert len(packet["ordered_actions"]) == 3
    whole = signer.exact_v1_release_scopes()
    assert whole["manifest"]["source_staging"] == staging
    assert whole["manifest"]["owner_consents"] == 1


def test_root_preflight_accepts_current_pinned_policy_with_consumed_legacy_audit(monkeypatch,tmp_path):
    """Check that new 13-file source is verified but NOT required to exist yet."""
    calls = []
    original = {"scope_sha256":root.SPARSE_SCOPE, "files":[{}]*13}
    archived = b"reviewed current-main immutable archive"
    stage_policy = {
        "candidate_sha":root.CANDIDATE,
        "sparse_scope_sha256":root.SPARSE_SCOPE,
        "archive_sha256":root.SPARSE_ARCHIVE_SHA,
        "archive_path":root.SOURCE_STAGE["archive_path"],
        "lkg_sha":root.LKG,
        "freeze_sha256":root.FREEZE_SHA,
        "promotion_hold_sha256":root.HOLD_SHA,
        "runtime_image_sha256":root.RUNTIME_IMAGE,
        "mcp_image_sha256":root.MCP_IMAGE,
    }
    class Stage:
        REPO=tmp_path/"git"
        def trusted_policy(self): return stage_policy
        def protected_preflight(self,p): return {"runtime_id":"old-runtime"}
        def protected_ci_as_operator(self,*a): return True
        def _load_trusted(self,path,name): return SimpleNamespace(
            git_object=lambda repo:lambda *args:None,
            source_manifest=lambda *args,**kwargs:original)
        def exact_source_archive(self,p,source):
            calls.append(("bound_archive",p["candidate_sha"],p["archive_sha256"]))
            assert p["candidate_sha"]==root.CANDIDATE
            assert p["sparse_scope_sha256"]==root.SPARSE_SCOPE
            assert p["archive_path"]==root.SOURCE_STAGE["archive_path"]
            return original,archived
        def verify_staged_source(self,*a):
            raise AssertionError("must not require already staged source")
    class Bootstrap:
        def validate_plan(self):return ({}, {})
        def readback(self):return {"runtime_id":"old-runtime"}
        def require_empty(self):calls.append(("bootstrap_empty",))
    stage=Stage()
    bootstrap=Bootstrap()
    monkeypatch.setattr(root,"verify_full_integrity",lambda:None)
    monkeypatch.setattr(root,"reviewed_policy",lambda **kwargs:{})
    monkeypatch.setattr(root,"load_trusted",
                        lambda path,*a: bootstrap if path==root.BOOT else (
                            stage if path==root.SPARSE_STAGE else object()))
    monkeypatch.setattr(root,"sha",lambda data:(
        root.FREEZE_SHA if data==b"freeze" else
        root.HOLD_SHA if data==b"hold" else
        root.SPARSE_ARCHIVE_SHA if data==archived else
        __import__("hashlib").sha256(data).hexdigest()))
    freeze=tmp_path/"freeze";freeze.write_bytes(b"freeze")
    hold=tmp_path/"hold";hold.write_bytes(b"hold")
    monkeypatch.setattr(root,"FREEZE",freeze)
    monkeypatch.setattr(root,"HOLD",hold)
    monkeypatch.setattr(root,"SOURCE",tmp_path/root.CANDIDATE)
    monkeypatch.setattr(root,"MISSING_FILE",tmp_path/root.CANDIDATE/"tools/one.py")
    journal=tmp_path/"journal"/"audit.jsonl";journal.parent.mkdir(mode=0o755)
    journal.parent.chmod(0o755)
    monkeypatch.setattr(root,"JOURNAL",journal)
    # Exercise trusted-parent metadata without touching an actual root journal.
    actual_lstat=Path.lstat
    def fake_lstat(path):
        stat=actual_lstat(path)
        if path==journal.parent:
            return SimpleNamespace(st_mode=stat.st_mode,st_uid=0)
        return stat
    monkeypatch.setattr(Path,"lstat",fake_lstat)
    # These production target baselines are inaccessible to unprivileged
    # test users on hardened hosts; model their required empty state only.
    protected_targets={"/var/lib/jason/pmv4-shadow",
                       "/usr/local/lib/jason/pmv4-trusted",
                       "/etc/jason/pmv4-shadow"}
    actual_exists=Path.exists
    actual_symlink=Path.is_symlink
    monkeypatch.setattr(Path,"exists",lambda path,*a,**kw:
                        False if str(path) in protected_targets
                        else actual_exists(path,*a,**kw))
    monkeypatch.setattr(Path,"is_symlink",lambda path:
                        False if str(path) in protected_targets
                        else actual_symlink(path))
    ctx=root.read_root_preflight()
    assert ctx["original"] is original
    assert ctx["source_archive"]==archived
    assert calls==[("bootstrap_empty",),
                   ("bound_archive",root.CANDIDATE,root.SPARSE_ARCHIVE_SHA)]


@pytest.mark.parametrize("fail_after_stage",[False,True])
def test_one_exact_proof_stages_source_before_helper_and_rolls_back(fail_after_stage,monkeypatch):
    actions=[]
    proof={"approval_id":"owner-mcp-"+"a"*32,
           "proof_sha256":"b"*64,"full_manifest_sha256":"c"*64}
    baseline={"runtime_id":"old-runtime","mcp_id":"old-mcp"}
    stage=SimpleNamespace(
        stage_root_copy=lambda parent,scope,blob:actions.append("stage13"),
        verify_staged_source=lambda *a:actions.append("verify13"),
        protected_preflight=lambda *a:baseline,
    )
    def publish(*a):
        if fail_after_stage:
            raise RuntimeError("injected root helper failure")
        actions.append("publish-helper")
    bootstrap=SimpleNamespace(
        validate_plan=lambda:({},{"file":b"helper"}),
        publish=publish,
        verify_targets=lambda *a:actions.append("verify-helper"),
        readback=lambda:baseline,
    )
    ctx={"stage":stage,"bootstrap":bootstrap,"original":{"files":[{}]*13},
         "source_archive":b"fixture","baseline":baseline,"sparse":{}}
    monkeypatch.setattr(root,"trusted_entry",lambda:{})
    monkeypatch.setattr(root,"root_release_lock",nullcontext)
    monkeypatch.setattr(root,"read_root_preflight",lambda:ctx)
    monkeypatch.setattr(root,"verify_proof",lambda *a,**kw:proof)
    monkeypatch.setattr(root,"audit_append",
                        lambda action,step,*a:actions.append((action,step)))
    monkeypatch.setattr(root,"build_recovery_context",lambda:ctx)
    monkeypatch.setattr(root,"revert_all",
                        lambda c,p:actions.append("reverse-rollback"))
    monkeypatch.setattr(root,"close_source",
                        lambda c:actions.append("close-source") or {"after":{}})
    monkeypatch.setattr(root,"load_native_exact_source",
                        lambda *a:(object(),object(),{},{}))
    engine=SimpleNamespace(
        _verify_objects=lambda *a,**kw:actions.append("verify-native"),
        _events=lambda j:[{"hash":"d"*64}],
    )
    monkeypatch.setattr(root,"native_install_under_outer_lock",
                        lambda *a:(engine,"journal",{}))
    monkeypatch.setattr(root,"verify_all_stage_postflights",
                        lambda p:actions.append("all-postflights"))
    if fail_after_stage:
        with pytest.raises(RuntimeError,match="injected"):
            root.execute()
        assert "stage13" in actions
        assert "reverse-rollback" in actions
        assert "close-source" not in actions
    else:
        root.execute()
        assert actions.index("stage13") < actions.index("verify13")
        assert actions.index("verify13") < actions.index("publish-helper")
        assert actions.index("publish-helper") < actions.index("close-source")
        assert ("committed",-1) in actions
        assert "reverse-rollback" not in actions
