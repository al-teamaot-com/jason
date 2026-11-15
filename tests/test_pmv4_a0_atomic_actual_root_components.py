"""Isolated UID0: real bootstrap, one Git source closure, native Stage A0.

Source-only disposable temp-mapped trust paths. No live host writes,
no real Owner OAuth, sudo is CI only. Tests all three actual code paths with
one simulated Entra Owner parent/three derived machine proofs.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import os
from pathlib import Path
import stat
import subprocess

import pytest

from implementation.mcp_service.src.jason_mcp.pmv4_bounded_owner_bridge import (
    authorize_one_bounded_objective_from_mcp,
)
from kernel.signed_owner_release import OWNER_PRINCIPAL, canonical
from orchestrator.pmv4_objective_scope import issue_proved_objective_step
from tools.pmv4_a0_atomic_plan_transaction import (
    A0AtomicSandboxTransaction, A0AtomicTransactionDenied,
)
from tools import pmv4_stage_a_packet as packet
from tools import pmv4_stage_a_admission as admission
from tools import pmv4_stage_a_native_install as native
from tools import pmv4_a0_closure_bootstrap_root as bootstrap
from tools import pmv4_stage_a0_root_source_closure as closure
from tools.pmv4_bounded_plan_journal import BoundedPlanJournal
from tools.pmv4_current_grant_attestation import issue_current_grant_attestation
from tools.pmv4_stage_a0_one_owner_review import (
    SOURCE, build_reviewed_plan, FREEZE as FROZEN_SHA, HOLD as HOLD_SHA,
    MISSING_SHA,
)
from test_pmv4_owner_objective_end_to_end import AT, APPROVAL_ID, enrolled, observed


FREEZE_BYTES = (
    b'{"reason": "2026-10-27 owner ordered stop all production deployments pending Production Manager acceptance", '
    b'"release_exception": "none approved", "remove_only_after": '
    b'"new explicit exact-SHA owner unfreeze decision", "schema_version": "1.0", '
    b'"scope": "manual-and-automatic-production-promotions", "status": "active"}\n'
)
HOLD_BYTES = (
    b"supervised exact-SHA release 508dadf673f025e970f607b2cf5e87ee020aa556; "
    b"hold unattended selector only\n"
)


class ActualA0Components:
    def __init__(self, *, env, journal, candidate, root, repo, scope,
                 manifest, freeze, hold, native_host, old_lock, monkeypatch,
                 fault=None):
        self.env, self.journal, self.candidate = env, journal, candidate
        self.root, self.repo, self.scope = root, repo, scope
        self.manifest, self.freeze, self.hold = manifest, freeze, hold
        self.native_host, self.old_lock = native_host, old_lock
        self.monkeypatch, self.fault = monkeypatch, fault
        self.applied = []
        reviewed_source = Path(__file__).resolve().parents[1]
        self.blobs = {
            str(root / "helper.py"):
                (reviewed_source / "tools/pmv4_stage_a0_root_source_closure.py").read_bytes(),
            str(root / "policy.json"):
                (reviewed_source / "config/pmv4-stage-a0/root-source-closure-policy-review.json").read_bytes(),
        }
        assert sha256(self.blobs[str(root / "helper.py")]).hexdigest() == bootstrap.FILES[
            "/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py"][1]
        assert sha256(self.blobs[str(root / "policy.json")]).hexdigest() == bootstrap.FILES[
            "/etc/jason-owner-release/pmv4-stage-a0-root-source-closure.json"][1]
        self._held = {}
        self._native_proof = None
        self.exact_file = root / "source" / SOURCE / "tools" / "pmv4_host_install_contract.py"
        self.exact_file.parent.mkdir(parents=True)
        self.payload = subprocess.check_output([
            "git", "-C", str(repo), "show",
            SOURCE + ":tools/pmv4_host_install_contract.py",
        ])
        assert sha256(self.payload).hexdigest() == MISSING_SHA
        self.monkeypatch.setattr(bootstrap, "FILES", {
            name: (Path(name).name, sha256(data).hexdigest(),
                   len(data), 0o444 if name.endswith("helper.py") else 0o400)
            for name, data in self.blobs.items()
        })
        self.monkeypatch.setattr(bootstrap, "LEDGER", self.root / "root-ledger")
        self.monkeypatch.setattr(bootstrap, "readback", lambda: {"safe": "unchanged"})

    def installer(self):
        return native.NativeStageAInstaller(
            production=False, sandbox=self.native_host,
            old_lock=self.old_lock, owner_metadata=False,
            root_health=lambda: {
                "preflight_evidence_satisfied":True,
                "stage_a_empty_baseline_verified":True,
                "root_only_target_parent_verification_needed":False,
                "breaker_state":"closed", "installation_ready":False,
                "production_install_authorized":False,
                "runtime_healthy":True, "mcp_running":True,
                "worker_scan_fresh":True,
                "freeze_sha256":FROZEN_SHA,
                "promotion_hold_sha256":HOLD_SHA,
            },
            at=AT + timedelta(seconds=5),
        )

    def _retain_inode(self, path: Path):
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        self._held[path] = fd

    def _same_inode(self, path: Path):
        fd = self._held.get(path)
        if fd is None or path.is_symlink() or not path.exists():
            return False
        a = os.fstat(fd)
        b = path.lstat()
        return (a.st_dev, a.st_ino, a.st_nlink) == (
            b.st_dev, b.st_ino, b.st_nlink
        ) and b.st_uid == 0

    def apply(self, index, evidence):
        self.applied.append(index)
        if index == 0:
            bootstrap.publish(self.blobs, {"safe": "unchanged"})
            for p in [Path(x) for x in self.blobs] + [bootstrap.LEDGER]:
                self._retain_inode(p)
        elif index == 1:
            closure._write_one_exact(
                self.exact_file, self.payload, test_only=True,
            )
            self._retain_inode(self.exact_file)
        elif index == 2:
            if "signed_v1_whole" in evidence:
                # Same original native Stage A0 create/journal machinery,
                # but the *one complete* v1 release signature authorizes this
                # exact three-operation atomic objective, not a separately
                # authenticated per-stage v1 grant. Sandbox-only acceptance.
                self._native_proof = evidence["signed_v1_whole"]
                actual = self.installer()
                binding = {
                    "source_sha":SOURCE,
                    "scope_sha256":self.scope["scope_sha256"],
                    "owner_approval_id":self._native_proof["payload"]["approval_id"],
                    "manifest_sha256":sha256(canonical(self.manifest)).hexdigest(),
                    "freeze_sha256":FROZEN_SHA,
                    "signed_proof_sha256":sha256(canonical(self._native_proof)).hexdigest(),
                }
                journal = actual._journal(SOURCE)
                with actual._legacy_lock():
                    actual._trusted_journal_parent()
                    actual._assert_parents()
                    if journal.exists():
                        raise PermissionError("native receipt already claimed")
                    actual._append(journal,"prepared",binding)
                    def after_step(label):
                        if self.fault == 2 and label.startswith("file:"):
                            raise InterruptedError("actual native file interruption")
                    actual._create(self.repo,self.scope,journal,binding,after_step)
                    actual._verify_objects(self.scope,partial=False)
                    actual._append(journal,"verified_installed",binding)
                return {"status":"native_installed_original_engine", "mode":"one_whole_v1"}
            self._native_proof = evidence["signed_step"]
            args = {
                "repo":self.repo, "candidate_sha":SOURCE,
                "scope":self.scope, "manifest":self.manifest,
                "signed_proof":self._native_proof,
                "freeze_path":self.freeze,
                "ci_check":lambda sha:sha == SOURCE,
                "bounded_plan_evidence":{
                    "objective":self.env["objective"],
                    "action_index":2,
                    "signed_parent":self.journal.signed_parent,
                    "ledger":self.env["ledger"],
                    "pinned_public_key":self.env["owner_key"].public_key(),
                    "hold_path":self.hold,
                    "plan_journal":self.journal,
                    "current_grant_attestation":evidence["current_signed_grant"],
                },
            }
            after_step = None
            if self.fault == 2:
                def after_step(label):
                    if label.startswith("file:"):
                        raise InterruptedError("native file crash")
            out = self.installer().install(**args, after_step=after_step)
            return out
        if self.fault == index:
            raise InterruptedError("simulated component postflight crash")
        return {"status":"installed", "index":index}

    def verify_installed(self, index):
        if index == 0:
            try:
                bootstrap.verify_targets(self.blobs)
                return (all(self._same_inode(Path(p)) for p in self.blobs)
                        and self._same_inode(bootstrap.LEDGER))
            except Exception:
                return False
        if index == 1:
            return (self._same_inode(self.exact_file)
                    and self.exact_file.read_bytes() == self.payload
                    and stat.S_IMODE(self.exact_file.stat().st_mode) == 0o444)
        if index == 2:
            try:
                self.installer()._verify_objects(self.scope, partial=False)
                rows = self.installer()._events(self.installer()._journal(SOURCE))
                return bool(rows and rows[-1]["event"] == "verified_installed")
            except Exception:
                return False
        return False

    def rollback_exact(self, index):
        if index == 0:
            if not self.verify_installed(0):
                raise PermissionError("bootstrap foreign replacement")
            for dest in self.blobs:
                Path(dest).unlink()
            bootstrap.LEDGER.rmdir()
        elif index == 1:
            if not self.verify_installed(1):
                raise PermissionError("immutable root source foreign replacement")
            self.exact_file.unlink()
        elif index == 2:
            if self._native_proof is None:
                raise PermissionError("native proof unavailable")
            return self.installer().recover_empty(
                scope=self.scope,
                confirmed_approval_id=(self._native_proof["payload"].get("approval_id")
                                       or self._native_proof["payload"].get("parent_approval_id")),
                confirmed_proof_sha256=sha256(canonical(self._native_proof)).hexdigest(),
            )
        else:
            raise ValueError("foreign action")
        return {"status":"exact_rollback", "index":index}

    def verify_absent(self, index):
        if index == 0:
            return (not any(Path(x).exists() for x in self.blobs)
                    and not bootstrap.LEDGER.exists())
        if index == 1:
            return not self.exact_file.exists() and not self.exact_file.is_symlink()
        if index == 2:
            return all(not self.installer()._map(x).exists()
                       for x in (packet.ROOT, packet.ETC, packet.HOST_CODE))
        return False

    def close(self):
        for fd in self._held.values():
            os.close(fd)
        self._held.clear()


@pytest.fixture
def real_three(enrolled, tmp_path, monkeypatch, request):
    if os.geteuid() != 0:
        pytest.skip("true disposable CI root test only")
    env = enrolled
    assert sha256(FREEZE_BYTES).hexdigest() == FROZEN_SHA
    assert sha256(HOLD_BYTES).hexdigest() == HOLD_SHA
    obj = build_reviewed_plan(expires_at=AT + timedelta(minutes=30))
    env["objective"] = obj
    root = tmp_path / "exact-native-root"
    root.mkdir(mode=0o700)
    d = tmp_path / "trusted-plan-journal"
    d.mkdir(mode=0o700)
    a = tmp_path / "atomic-journal"
    a.mkdir(mode=0o700)
    repo = tmp_path / "protected-git-source"
    main = Path(__file__).resolve().parents[1]
    subprocess.check_call([
        "git", "-c", "safe.directory=" + str(main), "-C", str(main),
        "worktree", "add", "--detach", str(repo), SOURCE,
    ], stdout=subprocess.DEVNULL)
    def cleanup_repo():
        subprocess.run([
            "git", "-c", "safe.directory=" + str(main), "-C", str(main),
            "worktree", "remove", "--force", str(repo),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    request.addfinalizer(cleanup_repo)
    scope = packet.build_scope(repo, SOURCE)
    assert scope["scope_sha256"] == obj.actions[2].scope_sha256
    freeze = tmp_path / "exact-fixture-freeze"
    hold = tmp_path / "exact-fixture-hold"
    freeze.write_bytes(FREEZE_BYTES)
    hold.write_bytes(HOLD_BYTES)
    manifest = admission.exact_stage_a_manifest(scope, FROZEN_SHA)
    assert sha256(canonical(manifest)).hexdigest() == obj.actions[2].artifact_sha256
    host = tmp_path / "mapped-native-host"
    host.mkdir(mode=0o700)
    for parent in ("usr/local/lib/jason", "var/lib/jason", "etc/jason"):
        (host / parent).mkdir(parents=True)
    lock = tmp_path / "legacy-test-lock"
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    issued = authorize_one_bounded_objective_from_mcp(
        bearer_token=env["token"],
        verified_owner_principal=OWNER_PRINCIPAL,
        verified_organization="aot",
        verify_entra_bearer=env["verifier"],
        exact_owner_consent=lambda facts:env["consents"].append(facts) or True,
        protected_main_check=lambda sha:sha == SOURCE,
        objective=obj, ledger=env["ledger"],
        signing_key=env["owner_key"], approval_id=APPROVAL_ID,
        affirmative_decision="approve_exact_one_pmv4_objective", at=AT,
    )
    parent = issued["signed_parent"]
    journal = BoundedPlanJournal(
        directory=d, objective=obj,
        signed_parent=parent,
        pinned_public_key=env["owner_key"].public_key(),
        owner_ledger=env["ledger"], at=AT,
    )
    tx = A0AtomicSandboxTransaction(
        directory=a, objective=obj, signed_parent=parent,
        pinned_public_key=env["owner_key"].public_key(),
        bounded_journal=journal,
    )
    def provider(index, prior):
        signed = issue_proved_objective_step(
            objective=obj, ledger=env["ledger"], signed_parent=parent,
            signing_key=env["owner_key"],
            pinned_public_key=env["owner_key"].public_key(),
            action_index=index, observed=observed(obj,index),
            verified_prior_steps=prior, at=AT,
        )
        grant = issue_current_grant_attestation(
            objective=obj, signed_parent=parent, ledger=env["ledger"],
            signer_private_key=env["owner_key"],
            pinned_public_key=env["owner_key"].public_key(),
            action_index=index, at=AT,
        )
        return {"signed_step":signed, "current_signed_grant":grant}
    def adapter(fault=None):
        return ActualA0Components(
            env=env, journal=journal, candidate=SOURCE, root=root, repo=repo,
            scope=scope, manifest=manifest, freeze=freeze, hold=hold,
            native_host=host, old_lock=lock, monkeypatch=monkeypatch, fault=fault,
        )
    return env, tx, provider, adapter


@pytest.mark.parametrize("failure", [None, 0, 1, 2])
def test_atomic_real_3_components_root_mode_isolated(real_three, failure):
    env, tx, provide, make_adapter = real_three
    a = make_adapter(fault=failure)
    try:
        if failure is None:
            outcome = tx.execute(adapters=a, stage_provider=provide,
                                 at=AT+timedelta(seconds=1))
            assert outcome["status"] == "three_exact_stage_actions_verified_together"
            assert all(a.verify_installed(i) for i in range(3))
            assert tx._read_events()[-1]["action"] == "committed"
            assert len(env["consents"]) == 1
        else:
            with pytest.raises(InterruptedError):
                tx.execute(adapters=a, stage_provider=provide,
                           at=AT+timedelta(seconds=1))
            assert all(a.verify_absent(i) for i in range(3))
            assert tx._read_events()[-1]["action"] == "aborted"
            assert len(env["consents"]) == 1
        with pytest.raises(A0AtomicTransactionDenied,
                           match="ONE_RELEASE_ALREADY_CLAIMED"):
            tx.execute(adapters=a, stage_provider=provide,
                       at=AT+timedelta(seconds=1))
    finally:
        a.close()
