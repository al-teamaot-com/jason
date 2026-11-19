"""Production-release scope, exact Owner binding and paired rollback simulations.

All tests are source-only and use fake host ports; no running service or
production credential is touched.
"""
from __future__ import annotations
from contextlib import nullcontext
from datetime import datetime, timezone, timedelta
import copy
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from implementation.kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, issue_exact_owner_release,
)
from tools import scoped_backport_release as sb

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / sb.RELEASE_MANIFEST).read_text())
MAIN = "b44772f78fd71bc054f952967e1bd78bccf0b17c"


def offer():
    return sb.make_offer(MANIFEST, main_sha=MAIN)


def signed(o, *, key=None, candidate=None, at=None, approval="owner-mcp-" + "9" * 32):
    key = key or Ed25519PrivateKey.generate()
    oid, principal = next(iter(EXACT_OWNER_OAUTH_SUBJECTS.items()))
    proof = issue_exact_owner_release(
        approval_id=approval, release_id=o["release_id"],
        candidate_sha=candidate or o["candidate_sha"],
        rollback_sha=o["rollback_sha"], scope_sha256=o["scope_sha256"],
        manifest_sha256=o["manifest_sha256"],
        freeze_sha256=o["freeze_sha256"], verified_tenant_id=sb.AOT_TENANT,
        verified_owner_oid=oid, verified_principal=principal,
        verified_organization_id="aot", confirmed_decision="approve",
        at=at or datetime.now(timezone.utc), private_key=key)
    return key, proof


class FakeHost:
    def __init__(self, key, *, fail_at=None):
        self.key = key
        self.fail_at = fail_at
        self.actions = []
        self.breaker = False
        self.consumed = set()
        self.rollback_count = 0
        self.live = {"jason-runtime": "baseline",
                     "jason-mcp-pilot": "baseline"}
        self.external = {"jason-pmv4-ticket-core": "unchanged",
                         "jason-pmv4-shadow-gateway": "unchanged",
                         "openbao": "unchanged",
                         "jason-teams-gateway": "unchanged"}
        self.protected_before = dict(self.external)
        self.freeze_restored = True

    def _act(self, label):
        self.actions.append(label)
        if self.fail_at == label:
            self.fail_at = None  # one bounded fault; rollback must run cleanly
            raise RuntimeError("injected_" + label)

    def enforce_installed_root_trust(self): self._act("trust")
    def release_lock(self, o):
        self._act("lock")
        return nullcontext()
    def freshly_validate_live_scope(self, o): self._act("live")
    def ensure_breaker_closed_and_workers_quiescent(self): self._act("gate")
    def deny_unresolved_attempt(self, o): self._act("prior")
    def owner_public_key(self): return self.key.public_key()
    def consumed_approvals(self): return frozenset(self.consumed)
    def snapshot_protected(self): return dict(self.external)
    def record_intent(self, o, decision): self._act("intent")
    def consume_owner_proof(self, approval_id):
        self._act("consume")
        self.consumed.add(approval_id)
    def frozen_transaction(self, o, decision):
        self._act("freeze")
        self.freeze_restored = False
        return nullcontext()
    def promote_exact(self, target, image, revision, env, mounts):
        self._act("promote_" + target)
        assert env == sb.ENV
        assert mounts == sb.GROUP_BIND_DESTINATIONS
        self.live[target] = image
    def verify_protected_unchanged(self, before):
        self._act("verify_other")
        assert self.external == before
    def verify_candidate_pair(self, o):
        self._act("verify_pair")
        assert self.live == {
            "jason-runtime": o["runtime_image_id"],
            "jason-mcp-pilot": o["mcp_image_id"]}
    def record_outcome(self, o, outcome, error=""):
        self.actions.append("outcome_" + outcome)
    def restore_pair_exact(self, o):
        self._act("rollback")
        self.rollback_count += 1
        self.live = {"jason-runtime": o["rollback_runtime_image_id"],
                     "jason-mcp-pilot": o["rollback_mcp_image_id"]}
    def verify_rollback(self, o):
        self._act("verify_rollback")
        assert self.live == {"jason-runtime": o["rollback_runtime_image_id"],
                             "jason-mcp-pilot": o["rollback_mcp_image_id"]}
    def verify_freeze_restored(self, o):
        self.freeze_restored = True
        self._act("freeze_restored")
    def open_breaker(self, reason):
        self.actions.append("breaker_" + reason)
        self.breaker = True


def test_manifest_and_offer_are_exactly_scoped():
    m = sb.validate_manifest(MANIFEST)
    assert m["candidate_sha"] == "87dfd07ae67d2d9994c029184bd39ebab5baebbf"
    o = offer()
    assert o["release_id"] == "release-87dfd07ae67d2d99"
    assert o["provider_mutations_authorized"] is False
    assert o["native_release_installed"] is False
    assert o["protected_services"] == list(sb.PROTECTED)
    assert o["runtime_settings"] == {"JASON_M365_GROUP_ADMIN_PROFILE": sb.GROUP_PROFILE}
    assert o["rollback_settings"] == sb.ROLLBACK_ENV


@pytest.mark.parametrize("field,value", [
    ("tenant_id", "other-tenant"),
    ("client_id", "other-client"),
    ("runtime_settings", {"JASON_M365_GROUP_ADMIN_PROFILE": "all"}),
    ("mcp_settings", {}),
    ("rollback_settings", {}),
    ("root_signed_approval_required", False),
    ("separate_provider_mutation_approval_required", False),
    ("additional_readonly_mount_destinations", []),
    ("protected_services", ["openbao"]),
    ("scope_sha256", "bad"),
    ("runtime_image_id", "jason-runtime:latest"),
    ("snapshot_ref", "refs/heads/main"),
    ("changed_files", ["../wrong.py"]),
])
def test_manifest_refuses_scope_mutation(field, value):
    m = copy.deepcopy(MANIFEST)
    m[field] = value
    with pytest.raises(sb.ScopedBackportDenied):
        sb.validate_manifest(m)


@pytest.mark.parametrize("field,value", [
    ("provider_mutations_authorized", True),
    ("native_release_installed", True),
    ("separate_owner_approval_required", False),
    ("tenant_id", "wrong"),
    ("runtime_settings", {"JASON_M365_GROUP_ADMIN_PROFILE": ""}),
    ("mcp_image_id", "bogus"),
    ("rollback_settings", {"JASON_M365_GROUP_ADMIN_PROFILE": "enabled"}),
])
def test_offer_is_not_arbitrary_authority(field, value):
    o = offer()
    o[field] = value
    with pytest.raises(sb.ScopedBackportDenied):
        sb.validate_offer(o)


def test_valid_owner_proof_pair_promotion():
    o = offer()
    key, proof = signed(o)
    host = FakeHost(key)
    result = sb.governed_promote(o, proof, host=host)
    assert result["status"] == "production_pair_verified"
    assert host.live["jason-runtime"] == o["runtime_image_id"]
    assert host.live["jason-mcp-pilot"] == o["mcp_image_id"]
    assert host.external == host.protected_before
    assert host.rollback_count == 0
    assert not host.breaker
    assert "consume" in host.actions and "outcome_production_pair_verified" in host.actions


@pytest.mark.parametrize("fail_at", ["promote_jason-runtime", "promote_jason-mcp-pilot",
                                     "verify_other", "verify_pair"])
def test_midflight_error_rolls_back_both_and_preserves_other_services(fail_at):
    o = offer()
    key, proof = signed(o)
    host = FakeHost(key, fail_at=fail_at)
    with pytest.raises(RuntimeError):
        sb.governed_promote(o, proof, host=host)
    assert host.rollback_count == 1
    assert host.live["jason-runtime"] == o["rollback_runtime_image_id"]
    assert host.live["jason-mcp-pilot"] == o["rollback_mcp_image_id"]
    assert host.external == host.protected_before
    assert host.freeze_restored
    assert not host.breaker
    assert "outcome_rollback_verified" in host.actions


def test_rollback_failure_opens_breaker_and_cannot_claim_success():
    o = offer()
    key, proof = signed(o)
    host = FakeHost(key, fail_at="rollback")
    original = host.promote_exact
    def fail_mcp(target, *args):
        if target == "jason-mcp-pilot":
            raise RuntimeError("MCP_FAILED")
        return original(target, *args)
    host.promote_exact = fail_mcp
    with pytest.raises(sb.ScopedBackportDenied, match="ROLLBACK_UNVERIFIED"):
        sb.governed_promote(o, proof, host=host)
    assert host.breaker
    assert host.live["jason-runtime"] == o["runtime_image_id"]
    assert host.freeze_restored


def test_freeze_restore_failure_opens_breaker():
    o = offer()
    key, proof = signed(o)
    host = FakeHost(key, fail_at="freeze_restored")
    with pytest.raises(sb.ScopedBackportDenied, match="FREEZE_RESTORE_UNVERIFIED"):
        sb.governed_promote(o, proof, host=host)
    assert host.breaker


def test_untrusted_host_is_rejected_before_promotion():
    o = offer()
    key, proof = signed(o)
    host = FakeHost(key, fail_at="trust")
    with pytest.raises(RuntimeError, match="injected_trust"):
        sb.governed_promote(o, proof, host=host)
    assert not any(a.startswith("promote_") for a in host.actions)


def test_replay_owner_proof_is_denied_before_second_mutation():
    o = offer()
    key, proof = signed(o)
    host = FakeHost(key)
    sb.governed_promote(o, proof, host=host)
    previous = host.actions[:]
    with pytest.raises(sb.ScopedBackportDenied, match="OWNER_PROOF_REJECTED"):
        sb.governed_promote(o, proof, host=host)
    assert not any(a.startswith("promote_") for a in host.actions[len(previous):])


def test_wrong_sha_owner_proof_cannot_authorize():
    o = offer()
    key = Ed25519PrivateKey.generate()
    changed = dict(o, candidate_sha="2" * 40, release_id="release-" + "2" * 16)
    key, proof = signed(changed, key=key)
    host = FakeHost(key)
    with pytest.raises(sb.ScopedBackportDenied, match="OWNER_PROOF_REJECTED"):
        sb.governed_promote(o, proof, host=host)
    assert not any(a.startswith("promote_") for a in host.actions)


def test_expired_owner_proof_cannot_authorize():
    o = offer()
    key, proof = signed(o, at=datetime.now(timezone.utc) - timedelta(hours=6))
    host = FakeHost(key)
    with pytest.raises(sb.ScopedBackportDenied, match="OWNER_PROOF_REJECTED"):
        sb.governed_promote(o, proof, host=host)


def test_provider_mutation_never_inferred_from_release():
    o = offer()
    key, proof = signed(o)
    host = FakeHost(key)
    result = sb.governed_promote(o, proof, host=host)
    assert result["provider_mutations_authorized"] is False
    assert not any("graph_post" in a for a in host.actions)


# CI checks out a shallow source tree. The source-admission unit tests use
# deterministic immutable Git evidence rather than depending on unrelated
# historic commit availability or remote GitHub network conditions. This does
# NOT change actual production source_admission, which always checks remote.
SYNTHETIC_DIFF = b"reviewed-fixed-source-diff"
SYNTHETIC_SCOPE = __import__("hashlib").sha256(SYNTHETIC_DIFF).hexdigest()


def _source_git_with_pinned_main(monkeypatch, manifest):
    original = sb._git
    frozen = dict(manifest)
    def git(repo, *args):
        if args == ("remote", "get-url", "origin"):
            return b"https://github.com/al-teamaot-com/jason.git\n"
        if args == ("ls-remote", "origin", "refs/heads/main"):
            return (MAIN + "\trefs/heads/main\n").encode()
        if args == ("show", MAIN + ":" + sb.RELEASE_MANIFEST):
            return json.dumps(frozen).encode()
        if args == ("ls-remote", "origin", frozen["snapshot_ref"]):
            return (frozen["candidate_sha"] + "\t" + frozen["snapshot_ref"] + "\n").encode()
        if args == ("diff", "--no-renames", "--name-only",
                    frozen["rollback_sha"], frozen["candidate_sha"]):
            return ("\n".join(MANIFEST["changed_files"]) + "\n").encode()
        if args == ("diff", "--binary",
                    frozen["rollback_sha"], frozen["candidate_sha"]):
            return SYNTHETIC_DIFF
        if len(args) == 2 and args[0] == "show" and ":" in args[1]:
            revision, path = args[1].split(":", 1)
            if (revision in {frozen["candidate_sha"], frozen["reviewed_feature_sha"], MAIN}
                    and path in sb.GROUP_SOURCE_MODULES):
                return ("immutable-reviewed:" + path).encode()
        raise AssertionError("unexpected simulated Git request: " + repr(args))
    monkeypatch.setattr(sb, "_git", git)
    monkeypatch.setattr(sb, "_ancestor", lambda repo, left, right:
                        (left, right) in {
                            (frozen["rollback_sha"], frozen["candidate_sha"]),
                            (frozen["reviewed_feature_sha"], MAIN)})
    return original


def test_source_admission_using_deterministic_immutable_git_evidence(monkeypatch):
    m = copy.deepcopy(MANIFEST)
    m["scope_sha256"] = SYNTHETIC_SCOPE
    _source_git_with_pinned_main(monkeypatch, m)
    proof = sb.source_admission(ROOT, trusted_main_sha=MAIN)
    assert proof["status"] == "source_admitted_not_production_eligible"
    assert proof["changed_file_count"] == 43
    assert proof["scope_sha256"] == SYNTHETIC_SCOPE
    assert proof["production_changes"] is False


def test_source_ref_move_is_denied_even_with_manifest(monkeypatch):
    m = copy.deepcopy(MANIFEST)
    m["scope_sha256"] = SYNTHETIC_SCOPE
    _source_git_with_pinned_main(monkeypatch, m)
    patched = sb._git
    def git(repo, *args):
        if args == ("ls-remote", "origin", MANIFEST["snapshot_ref"]):
            return (("e" * 40) + "\t" + MANIFEST["snapshot_ref"] + "\n").encode()
        return patched(repo, *args)
    monkeypatch.setattr(sb, "_git", git)
    with pytest.raises(sb.ScopedBackportDenied, match="SNAPSHOT_REF_MOVED"):
        sb.source_admission(ROOT, trusted_main_sha=MAIN)


def test_manifest_changed_paths_are_detected(monkeypatch):
    m = copy.deepcopy(MANIFEST)
    m["changed_files"] = sorted(m["changed_files"] + ["wrong.py"])
    _source_git_with_pinned_main(monkeypatch, m)
    with pytest.raises(sb.ScopedBackportDenied, match="SOURCE_PATH_SCOPE_INVALID"):
        sb.source_admission(ROOT, trusted_main_sha=MAIN)


def test_manifest_unreviewed_diff_is_detected(monkeypatch):
    m = copy.deepcopy(MANIFEST)
    m["scope_sha256"] = "d" * 64
    _source_git_with_pinned_main(monkeypatch, m)
    with pytest.raises(sb.ScopedBackportDenied, match="SCOPE_SHA256_DRIFT"):
        sb.source_admission(ROOT, trusted_main_sha=MAIN)


def test_snapshot_does_not_descend_from_rollback_is_denied(monkeypatch):
    m = copy.deepcopy(MANIFEST)
    m["scope_sha256"] = SYNTHETIC_SCOPE
    _source_git_with_pinned_main(monkeypatch, m)
    monkeypatch.setattr(sb, "_ancestor", lambda *args: False)
    with pytest.raises(sb.ScopedBackportDenied, match="SNAPSHOT_NOT_DESCENDANT"):
        sb.source_admission(ROOT, trusted_main_sha=MAIN)


def test_main_mismatch_is_denied(monkeypatch):
    _source_git_with_pinned_main(monkeypatch, MANIFEST)
    with pytest.raises(sb.ScopedBackportDenied, match="PROTECTED_MAIN_MOVED"):
        sb.source_admission(ROOT, trusted_main_sha="f" * 40)
