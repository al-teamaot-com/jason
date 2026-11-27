#!/usr/bin/env python3
"""Versioned coordinated profile extension of the native scoped-backport controller.

No CLI or production host implementation lives here. The root-installed
controller must independently pin the profile and manifest, attest its own
immutable source, and provide the existing durable native transaction ports.
The legacy M365 v1 source, policy, and dispatch remain unchanged.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
from hashlib import sha256
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol

from implementation.kernel.signed_owner_release_v2 import (
    OwnerReleaseProofDenied, verify_exact_owner_release,
)
from tools.scoped_backport_release import (
    REPO, _ORIGIN, _git, _ancestor, canonical, digest, require_sha,
    require_hash, require_image, deny,
)

# Fixed native container identities, not a caller-selected shell/command API.
# Additional environment or mount operations need a separately reviewed typed
# operation profile. They are intentionally NOT accepted by this first profile.
TARGET_ORDER = ("jason-runtime", "jason-mcp-pilot", "jason-teams-gateway")
ALWAYS_PROTECTED = ("jason-pmv4-ticket-core", "jason-pmv4-shadow-gateway", "openbao")
SHADOW = "jason-pmv4-shadow-gateway"
TARGET_FIELDS = {
    "name", "projection", "candidate_image", "rollback_image",
    "rollback_revision", "rollback_container_id",
}
PROJECTION_FIELDS = {
    "candidate_sha", "rollback_sha", "snapshot_ref", "changed_files",
    "patch_sha256",
}
MANIFEST_FIELDS = {
    "schema_version", "profile", "repository", "protected_main_sha",
    "reviewed_feature_sha", "candidate_sha", "rollback_sha", "release_id",
    "freeze_sha256", "projections", "targets", "protected_services",
    "provider_writes_allowed", "standing_authority", "scope_sha256",
}
PROFILE_FIELDS = {
    "schema_version", "profile", "allowed_targets", "manifest_sha256",
    "root_signed_approval_required", "preserve_freeze",
}
NORMAL_MANIFEST_FIELDS = (MANIFEST_FIELDS - {"freeze_sha256"}) | {"release_policy_sha256"}
NORMAL_PROFILE_FIELDS = (PROFILE_FIELDS - {"preserve_freeze"}) | {"preserve_release_policy"}
_REF = re.compile(r"refs/heads/prep/[a-z0-9-]{5,100}\Z")
_SLUG = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _exact(obj: Any, fields: set[str], code: str) -> None:
    if not isinstance(obj, Mapping) or set(obj) != fields:
        deny(code)


def binding_field(m: Mapping[str, Any]) -> str:
    if m.get("schema_version") == "2.0":
        return "freeze_sha256"
    if m.get("schema_version") == "3.0":
        return "release_policy_sha256"
    deny("COORDINATED_BINDING_VERSION")


def binding(m: Mapping[str, Any]) -> dict[str, str]:
    field = binding_field(m)
    return {field: m[field]}


def proof_binding(m: Mapping[str, Any]) -> dict[str, str]:
    field = binding_field(m)
    return {"expected_" + field: m[field]}


def _scope(m: Mapping[str, Any]) -> dict[str, Any]:
    fields = NORMAL_MANIFEST_FIELDS if m.get("schema_version") == "3.0" else MANIFEST_FIELDS
    return {k: m[k] for k in fields - {"scope_sha256"}}


def _names(names: Any) -> tuple[str, ...]:
    if not isinstance(names, list) or not names or not all(isinstance(x, str) for x in names):
        deny("COORDINATED_TARGET_LIST")
    result = tuple(names)
    if result != tuple(n for n in TARGET_ORDER if n in result):
        deny("COORDINATED_TARGET_ORDER_OR_SCOPE")
    return result


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    fields = NORMAL_MANIFEST_FIELDS if isinstance(manifest, Mapping) and manifest.get("schema_version") == "3.0" else MANIFEST_FIELDS
    _exact(manifest, fields, "COORDINATED_MANIFEST_SCHEMA")
    m = dict(manifest)
    if (
        m["schema_version"] not in ("2.0", "3.0") or m["repository"] != REPO
        or not isinstance(m["profile"], str) or not _SLUG.fullmatch(m["profile"])
        or m["provider_writes_allowed"] is not False
        or m["standing_authority"] is not False
    ):
        deny("COORDINATED_MANIFEST_AUTHORITY")
    for key in ("protected_main_sha", "reviewed_feature_sha", "candidate_sha", "rollback_sha"):
        require_sha(m[key], key.upper())
    if m["candidate_sha"] == m["rollback_sha"]:
        deny("COORDINATED_SAME_REVISION")
    if m["release_id"] != "release-" + m["candidate_sha"][:16]:
        deny("COORDINATED_RELEASE_ID")
    require_hash(m[binding_field(m)], "EXACT_RELEASE_POLICY_BINDING")
    require_hash(m["scope_sha256"], "SCOPE")
    projections = m["projections"]
    if not isinstance(projections, dict) or not 1 <= len(projections) <= len(TARGET_ORDER):
        deny("COORDINATED_PROJECTIONS")
    for name, p in projections.items():
        if not isinstance(name, str) or not _SLUG.fullmatch(name):
            deny("COORDINATED_PROJECTION_ID")
        _exact(p, PROJECTION_FIELDS, "COORDINATED_PROJECTION_SCHEMA")
        require_sha(p["candidate_sha"], "PROJECTION_CANDIDATE")
        require_sha(p["rollback_sha"], "PROJECTION_ROLLBACK")
        require_hash(p["patch_sha256"], "PROJECTION_PATCH")
        if (p["candidate_sha"] == p["rollback_sha"]
                or not isinstance(p["snapshot_ref"], str)
                or not _REF.fullmatch(p["snapshot_ref"])):
            deny("COORDINATED_PROJECTION_LINEAGE")
        paths = p["changed_files"]
        if (not isinstance(paths, list) or not 1 <= len(paths) <= 2000
                or not all(isinstance(x, str) and x and "\x00" not in x
                           and "\\" not in x and "\n" not in x
                           and not PurePosixPath(x).is_absolute()
                           and ".." not in PurePosixPath(x).parts
                           and str(PurePosixPath(x)) == x for x in paths)
                or paths != sorted(set(paths))):
            deny("COORDINATED_CHANGED_PATHS")
    if not isinstance(m["targets"], list) or not m["targets"]:
        deny("COORDINATED_TARGETS")
    for t in m["targets"]:
        _exact(t, TARGET_FIELDS, "COORDINATED_TARGET_SCHEMA")
        if t["name"] not in TARGET_ORDER or t["projection"] not in projections:
            deny("COORDINATED_UNKNOWN_TARGET")
        require_image(t["candidate_image"], "CANDIDATE")
        require_image(t["rollback_image"], "ROLLBACK")
        require_sha(t["rollback_revision"], "TARGET_ROLLBACK")
        if (t["candidate_image"] == t["rollback_image"]
                or not isinstance(t["rollback_container_id"], str)
                or not _HEX.fullmatch(t["rollback_container_id"])):
            deny("COORDINATED_ROLLBACK_IDENTITY")
    names = _names([t["name"] for t in m["targets"]])
    if set(projections) != {t["projection"] for t in m["targets"]}:
        deny("COORDINATED_UNUSED_PROJECTION")
    anchor = projections[m["targets"][0]["projection"]]
    if (m["candidate_sha"], m["rollback_sha"]) != (anchor["candidate_sha"], anchor["rollback_sha"]):
        deny("COORDINATED_SIGNED_ANCHOR")
    protected = sorted(set(ALWAYS_PROTECTED) | (set(TARGET_ORDER) - set(names)))
    if m["protected_services"] != protected:
        deny("COORDINATED_PROTECTED_PEER_SCOPE")
    if digest(_scope(m)) != m["scope_sha256"]:
        deny("COORDINATED_SCOPE_DIGEST")
    return m


def validate_profile(profile: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Profile is independently root-pinned, never sourced from a request."""
    m = validate_manifest(manifest)
    normal = m["schema_version"] == "3.0"
    _exact(profile, NORMAL_PROFILE_FIELDS if normal else PROFILE_FIELDS, "COORDINATED_PROFILE_SCHEMA")
    p = dict(profile)
    if (p["schema_version"] != m["schema_version"] or p["profile"] != m["profile"]
            or _names(p["allowed_targets"]) != tuple(t["name"] for t in m["targets"])
            or p["root_signed_approval_required"] is not True
            or p["preserve_release_policy" if normal else "preserve_freeze"] is not True
            or p["manifest_sha256"] != digest(m)):
        deny("COORDINATED_ROOT_PROFILE_SCOPE")
    return p


def source_admission(repo: Path, manifest: Mapping[str, Any],
                     profile: Mapping[str, Any]) -> dict[str, Any]:
    """Repeat immutable source evidence checks; cannot stage or authorize."""
    m = validate_manifest(manifest)
    validate_profile(profile, m)
    if _git(repo, "remote", "get-url", "origin").decode().strip() not in _ORIGIN:
        deny("COORDINATED_ORIGIN")
    remote = _git(repo, "ls-remote", "origin", "refs/heads/main").decode().strip().split()
    if (len(remote) != 2 or remote[1] != "refs/heads/main"
            or not re.fullmatch(r"[0-9a-f]{40}", remote[0])):
        deny("COORDINATED_PROTECTED_MAIN_MOVED")
    # An unrelated main merge must not invalidate an independently reviewed
    # component. Deny rewritten history or changes to the exact source scope.
    if remote[0] != m["protected_main_sha"]:
        if not _ancestor(repo, m["protected_main_sha"], remote[0]):
            deny("COORDINATED_PROTECTED_MAIN_REWRITTEN")
        affected = set().union(*(set(p["changed_files"]) for p in m["projections"].values()))
        changed = set(_git(repo, "diff", "--no-renames", "--name-only",
                           m["protected_main_sha"], remote[0]).decode().splitlines())
        if affected & changed:
            deny("COORDINATED_REVIEWED_SOURCE_CHANGED_ON_MAIN")
    if not _ancestor(repo, m["reviewed_feature_sha"], m["protected_main_sha"]):
        deny("COORDINATED_FEATURE_NOT_MAIN")
    for p in m["projections"].values():
        if (_git(repo, "ls-remote", "origin", p["snapshot_ref"]).decode().strip().split()
                != [p["candidate_sha"], p["snapshot_ref"]]):
            deny("COORDINATED_PROJECTION_REF_MOVED")
        if not _ancestor(repo, p["rollback_sha"], p["candidate_sha"]):
            deny("COORDINATED_PROJECTION_NOT_DESCENDANT")
        paths = _git(repo, "diff", "--no-renames", "--name-only",
                     p["rollback_sha"], p["candidate_sha"]).decode().splitlines()
        patch = _git(repo, "diff", "--binary", p["rollback_sha"], p["candidate_sha"])
        if sorted(paths) != p["changed_files"] or sha256(patch).hexdigest() != p["patch_sha256"]:
            deny("COORDINATED_PROJECTION_SCOPE_DRIFT")
    # Different image labels are valid only when the baseline's actual
    # build-input closure is identical. The only such alternate baseline
    # currently reviewed is the Teams Gateway; arbitrary equivalence is denied.
    for t in m["targets"]:
        p = m["projections"][t["projection"]]
        if t["rollback_revision"] != p["rollback_sha"]:
            if t["name"] != "jason-teams-gateway":
                deny("COORDINATED_TARGET_SOURCE_BASELINE")
            delta = _git(repo, "diff", "--name-only", t["rollback_revision"],
                         p["rollback_sha"], "--", "infrastructure/jason-teams-gateway",
                         "infrastructure/openclaw-jason-bridge")
            if delta.strip():
                deny("COORDINATED_GATEWAY_BUILD_INPUT_DRIFT")
    return {
        "status": "coordinated_source_admitted_not_production_eligible",
        "release_id": m["release_id"], "manifest_sha256": digest(m),
        "scope_sha256": m["scope_sha256"], "targets": [t["name"] for t in m["targets"]],
        "production_mutations": False, "owner_approval_recorded": False,
    }


class CoordinatedNativeHost(Protocol):
    """Ports on the existing root-native controller, not request callbacks."""
    def enforce_installed_root_trust(self, profile: Mapping[str, Any]) -> None: ...
    def release_lock(self, manifest: Mapping[str, Any]) -> AbstractContextManager[Any]: ...
    def freshly_validate_live_scope(self, manifest: Mapping[str, Any]) -> None: ...
    def ensure_breaker_closed_and_workers_quiescent(self) -> None: ...
    def deny_unresolved_attempt(self, manifest: Mapping[str, Any]) -> None: ...
    def owner_public_key(self) -> Any: ...
    def consumed_approvals(self) -> frozenset[str]: ...
    def snapshot_protected(self) -> Mapping[str, Any]: ...
    def record_intent(self, manifest: Mapping[str, Any], decision: Mapping[str, Any],
                      protected: Mapping[str, Any]) -> None: ...
    def consume_owner_proof(self, approval_id: str) -> None: ...
    def frozen_transaction(self, manifest: Mapping[str, Any],
                           decision: Mapping[str, Any]) -> AbstractContextManager[Any]: ...
    def promote_exact_target(self, manifest: Mapping[str, Any], target: Mapping[str, Any]) -> None: ...
    def verify_protected_unchanged(self, before: Mapping[str, Any]) -> None: ...
    def verify_candidate_targets(self, manifest: Mapping[str, Any]) -> None: ...
    def publish_component_readback(self, manifest: Mapping[str, Any],
                                   decision: Mapping[str, Any]) -> None: ...
    def verify_component_readback(self, manifest: Mapping[str, Any], *, frozen: bool) -> None: ...
    def restore_exact_target(self, manifest: Mapping[str, Any], target: Mapping[str, Any]) -> None: ...
    def verify_rollback(self, manifest: Mapping[str, Any]) -> None: ...
    def clear_component_readback(self, manifest: Mapping[str, Any]) -> None: ...
    def verify_freeze_restored(self, manifest: Mapping[str, Any]) -> None: ...
    def record_outcome(self, manifest: Mapping[str, Any], outcome: str, error: str = "") -> None: ...
    def open_breaker(self, reason: str) -> None: ...


def _rollback(host: CoordinatedNativeHost, m: Mapping[str, Any],
              before: Mapping[str, Any]) -> None:
    # Always restore in reverse order. The native port must be idempotent and
    # check the original container ID, image and source before removing a
    # candidate. It must refuse a foreign live or rollback container.
    for t in reversed(m["targets"]):
        host.restore_exact_target(m, t)
    host.verify_rollback(m)
    host.clear_component_readback(m)
    host.verify_protected_unchanged(before)


def governed_promote(manifest: Mapping[str, Any], profile: Mapping[str, Any],
                     signed_owner_proof: Mapping[str, Any], *,
                     host: CoordinatedNativeHost) -> dict[str, Any]:
    """Generalized exact, serialized, one-use native scoped transaction.

    The root host independently verifies source, profile, signed intent,
    baseline, every image, capacity, all native control readers and release mode.
    Nothing here grants authority or changes the current v1 release path.
    """
    m = validate_manifest(manifest)
    p = validate_profile(profile, m)
    host.enforce_installed_root_trust(p)
    with host.release_lock(m):
        host.freshly_validate_live_scope(m)
        host.ensure_breaker_closed_and_workers_quiescent()
        host.deny_unresolved_attempt(m)
        try:
            decision = verify_exact_owner_release(
                signed_owner_proof, public_key=host.owner_public_key(),
                expected_candidate_sha=m["candidate_sha"],
                expected_rollback_sha=m["rollback_sha"],
                expected_release_id=m["release_id"],
                expected_scope_sha256=m["scope_sha256"],
                expected_manifest_sha256=digest(m),
                **proof_binding(m),
                at=datetime.now(timezone.utc), consumed_ids=host.consumed_approvals(),
            )
        except OwnerReleaseProofDenied:
            deny("COORDINATED_OWNER_PROOF_REJECTED")
        before = host.snapshot_protected()
        if set(before) != set(m["protected_services"]):
            deny("COORDINATED_PROTECTED_SNAPSHOT")
        host.record_intent(m, decision, before)
        host.consume_owner_proof(decision["approval_id"])
        mutation_attempted = False
        rolled_back = False
        try:
            with host.frozen_transaction(m, decision):
                try:
                    for t in m["targets"]:
                        mutation_attempted = True
                        host.promote_exact_target(m, t)
                        host.verify_protected_unchanged(before)
                    host.verify_candidate_targets(m)
                    host.publish_component_readback(m, decision)
                    host.verify_component_readback(m, frozen=False)
                    host.verify_protected_unchanged(before)
                except BaseException:
                    try:
                        _rollback(host, m, before)
                        rolled_back = True
                    except BaseException as exc:
                        host.open_breaker("SCOPED_BACKPORT_COORDINATED_ROLLBACK_UNVERIFIED")
                        host.record_outcome(m, "rollback_unverified", type(exc).__name__)
                        raise
                    raise
            # Commit success only after the exact release mode has been
            # independently reverified and the steady-state readers agree.
            host.verify_freeze_restored(m)
            host.verify_component_readback(m, frozen=True)
            host.verify_protected_unchanged(before)
            host.record_outcome(m, "production_components_verified")
        except BaseException as exc:
            # After exiting the frozen window, a postflight or freeze
            # failure is an unresolved transaction. Preserve evidence and
            # let the existing root crash-recovery worker restore under lock;
            # never silently reopen the freeze or manufacture a second grant.
            if mutation_attempted and not rolled_back:
                host.open_breaker("SCOPED_BACKPORT_COORDINATED_POSTFLIGHT_UNVERIFIED")
                host.record_outcome(m, "recovery_required", type(exc).__name__)
            elif rolled_back:
                try:
                    host.verify_freeze_restored(m)
                    host.record_outcome(m, "rollback_verified", type(exc).__name__)
                except BaseException:
                    host.open_breaker("SCOPED_BACKPORT_COORDINATED_FREEZE_UNVERIFIED")
                    host.record_outcome(m, "recovery_required", type(exc).__name__)
                    raise
            else:
                try:
                    host.verify_freeze_restored(m)
                    host.record_outcome(m, "failed_before_mutation", type(exc).__name__)
                except BaseException:
                    host.open_breaker("SCOPED_BACKPORT_COORDINATED_FREEZE_UNVERIFIED")
                    host.record_outcome(m, "recovery_required", type(exc).__name__)
                    raise
            raise
        return {
            "status": "production_components_verified", "release_id": m["release_id"],
            "manifest_sha256": digest(m), "approval_id": decision["approval_id"],
            "targets": [t["name"] for t in m["targets"]],
            "protected_services_unchanged": True, "provider_writes_authorized": False,
        }
