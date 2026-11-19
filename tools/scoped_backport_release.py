#!/usr/bin/env python3
"""Reusable, fail-closed scoped-backport source admission and trusted release core.

This module is SOURCE ONLY until installed by an authenticated, exact-SHA,
root-attested Production Manager release. It NEVER grants authority, installs
root code, performs Docker operations, unfreezes production, or writes providers.

A candidate MUST be a reviewed, immutable rollback-descendant snapshot, and
a published manifest MUST be in the currently protected main Git tree.
The root release adapter MUST revalidate these proofs, production controls,
the Owner's *signed one-use* exact transaction, image IDs and rollback.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Protocol

from implementation.kernel.signed_owner_release import (
    OwnerReleaseProofDenied, verify_exact_owner_release,
)

_SHA = re.compile(r"^[0-9a-f]{40}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REF = re.compile(r"^refs/heads/prep/[a-z0-9-]{5,100}$")
_ORIGIN = frozenset({
    "https://github.com/al-teamaot-com/jason.git",
    "https://github.com/al-teamaot-com/jason",
    "git@github.com:al-teamaot-com/jason.git",
})
_PROFILE = "governed-scoped-backport-v1"
REPO = "al-teamaot-com/jason"
RELEASE_MANIFEST = "config/scoped-backport-m365-release.json"
GROUP_PROFILE = "aot-group-admin-exact-pilot-v1"
AOT_TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
AOT_CLIENT = "client-aot-internal"
PROTECTED = ("jason-pmv4-ticket-core", "jason-pmv4-shadow-gateway",
             "jason-teams-gateway", "openbao")
ENV = {"JASON_M365_GROUP_ADMIN_PROFILE": GROUP_PROFILE}
ROLLBACK_ENV = {"JASON_M365_GROUP_ADMIN_PROFILE": ""}
GROUP_BIND_DESTINATIONS = tuple(
    f"/run/jason-secrets/openbao/microsoft-group-{role}/{field}"
    for role in ("read", "write") for field in ("role_id", "secret_id")
)
GROUP_SOURCE_MODULES = frozenset({
    "implementation/connectors/microsoft_graph/group_executor.py",
    "implementation/runtime_service/src/jason_runtime/microsoft_group_admin.py",
    "implementation/runtime_service/src/jason_runtime/microsoft_group_admin_activation.py",
    "implementation/orchestrator/microsoft_group_admin_catalog.py",
    "tools/microsoft_group_admin_identity_bootstrap.py",
})
M365_ALLOWED_PATHS = frozenset({
    '.github/workflows/security-regressions.yml',
    'config/microsoft_graph/group-admin-release.json',
    'config/microsoft_graph/pilots/aot-group-admin-20261112.json',
    'docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md',
    'docs/engineering/providers/Microsoft-365-Governed-Operations-20261112.md',
    'docs/operations/AOT-M365-Group-Admin-Pilot-20261112.md',
    'docs/operations/AOT-M365-Group-Admin-Release-20261112.md',
    'docs/operations/AOT-M365-LKG-Backport-Release-20261119.md',
    'implementation/connectors/core/openbao_secrets.py',
    'implementation/connectors/microsoft_graph/governed_operations.py',
    'implementation/connectors/microsoft_graph/group_executor.py',
    'implementation/connectors/microsoft_graph/group_preflight.py',
    'implementation/connectors/microsoft_graph/group_reader.py',
    'implementation/connectors/microsoft_graph/service_catalog.py',
    'implementation/connectors/microsoft_graph/test_governed_operations.py',
    'implementation/connectors/microsoft_graph/test_group_executor.py',
    'implementation/connectors/microsoft_graph/test_group_pilot_manifest.py',
    'implementation/connectors/microsoft_graph/test_group_preflight.py',
    'implementation/connectors/microsoft_graph/test_group_reader.py',
    'implementation/connectors/tests/test_openbao_secrets.py',
    'implementation/mcp_service/src/jason_mcp/server.py',
    'implementation/mcp_service/tests/test_microsoft_group_admin_mcp.py',
    'implementation/orchestrator/microsoft_group_admin_catalog.py',
    'implementation/orchestrator/tests/test_microsoft_group_admin_catalog.py',
    'implementation/runtime_service/src/jason_runtime/composition.py',
    'implementation/runtime_service/src/jason_runtime/microsoft_group_admin.py',
    'implementation/runtime_service/src/jason_runtime/microsoft_group_admin_activation.py',
    'implementation/runtime_service/tests/test_composition.py',
    'implementation/runtime_service/tests/test_microsoft_group_admin.py',
    'implementation/runtime_service/tests/test_microsoft_group_admin_activation.py',
    'infrastructure/jason-mcp/production-deploy.sh',
    'infrastructure/jason-runtime/compose.yaml',
    'infrastructure/jason-runtime/production-deploy.sh',
    'infrastructure/microsoft_graph/Dockerfile.mcp-lkg-overlay',
    'infrastructure/microsoft_graph/Dockerfile.runtime-lkg-overlay',
    'infrastructure/microsoft_graph/README.md',
    'tools/deploy_live_container.py',
    'tools/microsoft_group_admin_identity_bootstrap.py',
    'tools/microsoft_group_admin_release_profile.py',
    'tools/provider_secret_provision.py',
    'tools/tests/test_microsoft_group_admin_identity_bootstrap.py',
    'tools/tests/test_microsoft_group_admin_release.py',
    'tools/tests/test_provider_secret_provision.py',
})

M_FIELDS = frozenset({
    "schema_version", "profile", "repository", "component",
    "tenant_id", "client_id", "candidate_sha", "rollback_sha",
    "reviewed_feature_sha", "snapshot_ref", "changed_files",
    "scope_sha256", "runtime_image_id", "mcp_image_id",
    "rollback_runtime_image_id", "rollback_mcp_image_id",
    "freeze_sha256", "runtime_settings", "mcp_settings",
    "rollback_settings", "additional_readonly_mount_destinations",
    "protected_services", "root_signed_approval_required",
    "separate_provider_mutation_approval_required",
})
O_FIELDS = frozenset({
    "schema_version", "profile", "status", "release_id", "candidate_sha",
    "rollback_sha", "protected_main_sha", "scope_sha256", "manifest_sha256",
    "runtime_image_id", "mcp_image_id", "rollback_runtime_image_id",
    "rollback_mcp_image_id", "freeze_sha256", "runtime_settings",
    "mcp_settings", "rollback_settings", "additional_readonly_mount_destinations",
    "protected_services", "tenant_id", "client_id",
    "one_transaction_only", "separate_owner_approval_required",
    "provider_mutations_authorized", "native_release_installed",
})


class ScopedBackportDenied(PermissionError):
    pass


def deny(code: str) -> None:
    raise ScopedBackportDenied("SCOPED_BACKPORT_" + code)


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False).encode("utf-8")


def digest(value: Mapping[str, Any]) -> str:
    return sha256(canonical(value)).hexdigest()


def require_hash(value: object, name: str) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        deny(name + "_SHA256_INVALID")
    return value


def require_sha(value: object, name: str) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        deny(name + "_REVISION_INVALID")
    return value


def require_image(value: object, name: str) -> str:
    if type(value) is not str or not _IMAGE.fullmatch(value):
        deny(name + "_IMAGE_INVALID")
    return value


def validate_manifest(data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(data, Mapping) or set(data) != M_FIELDS:
        deny("MANIFEST_SCHEMA")
    m = dict(data)
    if (m["schema_version"] != "1.0" or m["profile"] != _PROFILE
            or m["repository"] != REPO or m["component"] != "aot-m365-group-admin"
            or m["tenant_id"] != AOT_TENANT or m["client_id"] != AOT_CLIENT
            or m["runtime_settings"] != ENV or m["mcp_settings"] != ENV
            or m["rollback_settings"] != ROLLBACK_ENV
            or m["additional_readonly_mount_destinations"] != list(GROUP_BIND_DESTINATIONS)
            or m["protected_services"] != list(PROTECTED)
            or m["root_signed_approval_required"] is not True
            or m["separate_provider_mutation_approval_required"] is not True):
        deny("MANIFEST_SCOPE_EXPANSION")
    for name in ("candidate_sha", "rollback_sha", "reviewed_feature_sha"):
        require_sha(m[name], name.upper())
    if m["candidate_sha"] == m["rollback_sha"]:
        deny("SAME_REVISION")
    for name in ("runtime_image_id", "mcp_image_id",
                 "rollback_runtime_image_id", "rollback_mcp_image_id"):
        require_image(m[name], name.upper())
    for name in ("scope_sha256", "freeze_sha256"):
        require_hash(m[name], name.upper())
    if not isinstance(m["snapshot_ref"], str) or not _REF.fullmatch(m["snapshot_ref"]):
        deny("SNAPSHOT_REF_INVALID")
    paths = m["changed_files"]
    if (not isinstance(paths, list) or not paths
            or paths != sorted(set(paths))
            or not all(isinstance(p, str) and p and not p.startswith("/")
                       and ".." not in Path(p).parts for p in paths)
            or frozenset(paths) != M365_ALLOWED_PATHS
            or not GROUP_SOURCE_MODULES.issubset(set(paths))):
        deny("SOURCE_PATH_SCOPE_INVALID")
    # An immutable named snapshot is the single source of the active image pair.
    return m


def _git(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", "-c", f"safe.directory={repo}", "-C", str(repo),
                           *args], capture_output=True, check=False, timeout=30)
    if proc.returncode:
        deny("GIT_EVIDENCE_UNAVAILABLE")
    return proc.stdout


def _ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    p = subprocess.run(["git", "-c", f"safe.directory={repo}",
                        "-C", str(repo), "merge-base",
                        "--is-ancestor", ancestor, descendant],
                       capture_output=True, timeout=20, check=False)
    return p.returncode == 0


# A scoped release is pinned to immutable *reviewed* source, not the
# repository's unrelated daily engineering merges. When protected main has
# advanced, its exact reviewed root code, manifest, Graph implementation
# and systemd units must remain byte-identical to the pinned source commit.
# No branch-force, source substitution, tag drift or relaxed production gate.
SCOPED_MAIN_IMMUTABLE_PATHS = frozenset((
    RELEASE_MANIFEST,
    "tools/scoped_backport_release.py",
    "tools/scoped_backport_release_request.py",
    "tools/scoped_backport_native_root.py",
    "tools/scoped_backport_native_host.py",
    "tools/scoped_backport_native_recovery.py",
    "tools/scoped_backport_owner_local_approval.py",
    "tools/deploy_live_container.py",
    "implementation/kernel/signed_owner_release.py",
    "infrastructure/scoped-backport-release/jason-scoped-backport-recovery.service",
    "infrastructure/scoped-backport-release/jason-scoped-backport-recovery.timer",
    "infrastructure/scoped-backport-release/jason-scoped-backport-requests.path",
    "infrastructure/scoped-backport-release/jason-scoped-backport-requests.service",
)) | GROUP_SOURCE_MODULES


def confirm_protected_main_lineage(repo: Path, *, pinned: str,
                                   current: str) -> None:
    if current == pinned:
        return
    if (not _SHA.fullmatch(current) or
            not _ancestor(repo, pinned, current)):
        deny("PROTECTED_MAIN_MOVED")
    for path in sorted(SCOPED_MAIN_IMMUTABLE_PATHS):
        if _git(repo, "show", pinned + ":" + path) != _git(
                repo, "show", current + ":" + path):
            deny("PINNED_SCOPED_SOURCE_CHANGED_ON_MAIN")


def source_admission(repo: Path, *, trusted_main_sha: str,
                     manifest_path: str = RELEASE_MANIFEST) -> dict[str, Any]:
    """Read-only, exact protected-main + frozen snapshot proof.

    Root host repeats this inside the native transaction; it does not accept
    a candidate's self-declared main SHA as release authorization.
    """
    main = require_sha(trusted_main_sha, "MAIN")
    origin = _git(repo, "remote", "get-url", "origin").decode().strip()
    if origin not in _ORIGIN:
        deny("ORIGIN_NOT_AOT")
    remote = _git(repo, "ls-remote", "origin", "refs/heads/main").decode().strip().split()
    if (len(remote) != 2 or remote[1] != "refs/heads/main"
            or not _SHA.fullmatch(remote[0])):
        deny("PROTECTED_MAIN_REMOTE_INVALID")
    confirm_protected_main_lineage(repo, pinned=main, current=remote[0])
    try:
        m = validate_manifest(json.loads(_git(repo, "show", main + ":" + manifest_path)))
    except (ValueError, UnicodeError) as exc:
        raise ScopedBackportDenied("SCOPED_BACKPORT_MANIFEST_UNREADABLE") from exc
    remote_snapshot = _git(repo, "ls-remote", "origin", m["snapshot_ref"]).decode().strip().split()
    if remote_snapshot != [m["candidate_sha"], m["snapshot_ref"]]:
        deny("SNAPSHOT_REF_MOVED")
    if not _ancestor(repo, m["rollback_sha"], m["candidate_sha"]):
        deny("SNAPSHOT_NOT_DESCENDANT_OF_ROLLBACK")
    if not _ancestor(repo, m["reviewed_feature_sha"], main):
        deny("FEATURE_NOT_PROTECTED_MAIN")
    actual_paths = _git(repo, "diff", "--no-renames", "--name-only",
                        m["rollback_sha"], m["candidate_sha"]).decode().splitlines()
    if sorted(actual_paths) != m["changed_files"]:
        deny("CHANGED_PATHS_DRIFTED")
    actual_scope = sha256(_git(repo, "diff", "--binary",
                               m["rollback_sha"], m["candidate_sha"])).hexdigest()
    if actual_scope != m["scope_sha256"]:
        deny("SCOPE_SHA256_DRIFT")
    # Avoid silently substituting old group code with new unrelated MCP changes.
    for path in sorted(GROUP_SOURCE_MODULES):
        if (_git(repo, "show", m["candidate_sha"] + ":" + path)
                != _git(repo, "show", m["reviewed_feature_sha"] + ":" + path)
                or _git(repo, "show", m["candidate_sha"] + ":" + path)
                != _git(repo, "show", main + ":" + path)):
            deny("REVIEWED_GROUP_SOURCE_MISMATCH")
    return {
        "status": "source_admitted_not_production_eligible",
        "production_changes": False,
        "candidate_sha": m["candidate_sha"],
        "rollback_sha": m["rollback_sha"],
        "protected_main_sha": main,
        "scope_sha256": actual_scope,
        "manifest_sha256": digest(m),
        "changed_file_count": len(actual_paths),
    }


def make_offer(manifest: Mapping[str, Any], *, main_sha: str) -> dict[str, Any]:
    m = validate_manifest(manifest)
    main = require_sha(main_sha, "MAIN")
    offer = {
        "schema_version": "1.0", "profile": _PROFILE,
        "status": "source_only_not_production_eligible",
        "release_id": "release-" + m["candidate_sha"][:16],
        "candidate_sha": m["candidate_sha"], "rollback_sha": m["rollback_sha"],
        "protected_main_sha": main, "scope_sha256": m["scope_sha256"],
        "manifest_sha256": digest(m),
        "runtime_image_id": m["runtime_image_id"], "mcp_image_id": m["mcp_image_id"],
        "rollback_runtime_image_id": m["rollback_runtime_image_id"],
        "rollback_mcp_image_id": m["rollback_mcp_image_id"],
        "freeze_sha256": m["freeze_sha256"],
        "runtime_settings": m["runtime_settings"], "mcp_settings": m["mcp_settings"],
        "rollback_settings": m["rollback_settings"],
        "additional_readonly_mount_destinations": m["additional_readonly_mount_destinations"],
        "protected_services": m["protected_services"],
        "tenant_id": m["tenant_id"], "client_id": m["client_id"],
        "one_transaction_only": True, "separate_owner_approval_required": True,
        "provider_mutations_authorized": False,
        "native_release_installed": False,
    }
    return validate_offer(offer)


def validate_offer(offer: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(offer, Mapping) or set(offer) != O_FIELDS:
        deny("OFFER_SCHEMA")
    o = dict(offer)
    if (o["schema_version"] != "1.0" or o["profile"] != _PROFILE
            or o["status"] != "source_only_not_production_eligible"
            or o["release_id"] != "release-" + require_sha(o["candidate_sha"], "CANDIDATE")[:16]
            or o["tenant_id"] != AOT_TENANT or o["client_id"] != AOT_CLIENT
            or o["runtime_settings"] != ENV or o["mcp_settings"] != ENV
            or o["rollback_settings"] != ROLLBACK_ENV
            or o["additional_readonly_mount_destinations"] != list(GROUP_BIND_DESTINATIONS)
            or o["protected_services"] != list(PROTECTED)
            or o["one_transaction_only"] is not True
            or o["separate_owner_approval_required"] is not True
            or o["provider_mutations_authorized"] is not False
            or o["native_release_installed"] is not False):
        deny("OFFER_AUTHORITY_OR_SCOPE")
    require_sha(o["rollback_sha"], "ROLLBACK")
    require_sha(o["protected_main_sha"], "PROTECTED_MAIN")
    for name in ("runtime_image_id", "mcp_image_id", "rollback_runtime_image_id",
                 "rollback_mcp_image_id"):
        require_image(o[name], name.upper())
    for name in ("manifest_sha256", "scope_sha256", "freeze_sha256"):
        require_hash(o[name], name.upper())
    return o


class TrustedScopedBackportHost(Protocol):
    """Only an independently root-attested native adapter may implement this."""
    def enforce_installed_root_trust(self) -> None: ...
    def release_lock(self, offer: Mapping[str, Any]) -> AbstractContextManager[Any]: ...
    def freshly_validate_live_scope(self, offer: Mapping[str, Any]) -> None: ...
    def ensure_breaker_closed_and_workers_quiescent(self) -> None: ...
    def deny_unresolved_attempt(self, offer: Mapping[str, Any]) -> None: ...
    def owner_public_key(self) -> Any: ...
    def consumed_approvals(self) -> frozenset[str]: ...
    def snapshot_protected(self) -> Mapping[str, Any]: ...
    def record_intent(self, offer: Mapping[str, Any], decision: Mapping[str, Any]) -> None: ...
    def consume_owner_proof(self, approval_id: str) -> None: ...
    def frozen_transaction(self, offer: Mapping[str, Any],
                           decision: Mapping[str, Any]) -> AbstractContextManager[Any]: ...
    def promote_exact(self, target: str, image: str, revision: str,
                      environment: Mapping[str, str], readonly_mounts: tuple[str, ...]) -> None: ...
    def verify_protected_unchanged(self, before: Mapping[str, Any]) -> None: ...
    def verify_candidate_pair(self, offer: Mapping[str, Any]) -> None: ...
    def record_outcome(self, offer: Mapping[str, Any], outcome: str, error: str = "") -> None: ...
    def restore_pair_exact(self, offer: Mapping[str, Any]) -> None: ...
    def verify_rollback(self, offer: Mapping[str, Any]) -> None: ...
    def verify_freeze_restored(self, offer: Mapping[str, Any]) -> None: ...
    def open_breaker(self, reason: str) -> None: ...


def governed_promote(offer: Mapping[str, Any], signed_owner_proof: Mapping[str, Any],
                     *, host: TrustedScopedBackportHost) -> dict[str, Any]:
    """Existing signed Owner proof + native protected pair promotion & rollback.

    NO host implementation is shipped by this code. An uninstalled source-only
    module cannot access production. Simulation tests use a deliberately fake
    host; they are not a production authorization or operational rollback.
    """
    o = validate_offer(offer)
    host.enforce_installed_root_trust()
    with host.release_lock(o):
        host.freshly_validate_live_scope(o)
        host.ensure_breaker_closed_and_workers_quiescent()
        host.deny_unresolved_attempt(o)
        try:
            decision = verify_exact_owner_release(
                signed_owner_proof, public_key=host.owner_public_key(),
                expected_candidate_sha=o["candidate_sha"],
                expected_rollback_sha=o["rollback_sha"],
                expected_release_id=o["release_id"],
                expected_scope_sha256=o["scope_sha256"],
                expected_manifest_sha256=o["manifest_sha256"],
                expected_freeze_sha256=o["freeze_sha256"],
                at=datetime.now(timezone.utc),
                consumed_ids=host.consumed_approvals())
        except OwnerReleaseProofDenied as exc:
            raise ScopedBackportDenied("SCOPED_BACKPORT_OWNER_PROOF_REJECTED") from exc
        before = host.snapshot_protected()
        host.record_intent(o, decision)
        host.consume_owner_proof(decision["approval_id"])
        mutation_attempted = False
        try:
            with host.frozen_transaction(o, decision):
                try:
                    mutation_attempted = True
                    binds = tuple(o["additional_readonly_mount_destinations"])
                    host.promote_exact("jason-runtime", o["runtime_image_id"],
                                       o["candidate_sha"], ENV, binds)
                    host.verify_protected_unchanged(before)
                    host.promote_exact("jason-mcp-pilot", o["mcp_image_id"],
                                       o["candidate_sha"], ENV, binds)
                    host.verify_candidate_pair(o)
                    host.verify_protected_unchanged(before)
                    host.record_outcome(o, "production_pair_verified")
                except BaseException as exc:
                    try:
                        host.restore_pair_exact(o)
                        host.verify_rollback(o)
                        host.verify_protected_unchanged(before)
                        host.record_outcome(o, "rollback_verified",
                                            error=type(exc).__name__)
                    except BaseException as restore_error:
                        host.open_breaker("SCOPED_BACKPORT_ROLLBACK_UNVERIFIED")
                        host.record_outcome(o, "rollback_unverified",
                                            error=type(restore_error).__name__)
                        raise ScopedBackportDenied(
                            "SCOPED_BACKPORT_ROLLBACK_UNVERIFIED") from restore_error
                    raise
        except BaseException:
            if not mutation_attempted:
                host.record_outcome(o, "failed_before_mutation")
            raise
        finally:
            try:
                host.verify_freeze_restored(o)
            except BaseException as exc:
                host.open_breaker("SCOPED_BACKPORT_FREEZE_RESTORE_UNVERIFIED")
                raise ScopedBackportDenied(
                    "SCOPED_BACKPORT_FREEZE_RESTORE_UNVERIFIED") from exc
        return {
            "status": "production_pair_verified",
            "release_id": o["release_id"],
            "candidate_sha": o["candidate_sha"],
            "rollback_sha": o["rollback_sha"],
            "approval_id": decision["approval_id"],
            "provider_mutations_authorized": False,
            "protected_services_unchanged": True,
        }
