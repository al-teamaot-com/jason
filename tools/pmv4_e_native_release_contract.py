#!/usr/bin/env python3
"""Strict typed Stage E *source* manifest for the existing native root release.

This is a schema/byte attestor, not a second Release Manager, signer, root
installer, service mutator, or production-ready assertion.  A future approved
native root callback must independently verify the protected live policy and
the exact one-use authenticated Owner signature bound to these bytes.
The Compose component release manifest is intentionally never used.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from tools import pmv4_e_exact_release_packet as packet

MODE = "owner-signed-native-systemd-stage-e"
COMPONENT = "jason-pmv4-e-six-unit-controlplane"
PROTECTED = (
    "jason-mcp-pilot",
    "jason-pmv4-shadow-gateway",
    "jason-pmv4-ticket-core",
    "jason-runbook-management-read.service",
    "jason-runtime",
    "jason-teams-gateway",
    "openbao",
)
MANIFEST_FIELDS = frozenset({
    "schema_version", "release_mode", "release_class", "repository",
    "action", "component_id", "candidate_sha", "rollback_sha",
    "source_scope_sha256", "source_manifest_sha256",
    "source_candidate_policy_sha256", "prior_root_policy_sha256",
    "freeze_sha256", "reviewed_file_count", "new_systemd_file_count",
    "legacy_source_input_count", "protected_services",
    "provider_scope", "requires_root_preflight", "requires_signed_owner",
    "standing_authority", "production_freeze_override",
    "protected_restart_allowed",
})
PROVIDER_NONE = {
    "provider": "none", "profile": "", "tenant_id": "",
    "scope_id": "", "application_id": "", "client_id": "",
}


class StageEManifestDenied(PermissionError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise StageEManifestDenied("PMV4_E_NATIVE_MANIFEST_" + reason)


def validate(manifest: Mapping[str, Any], scope: Mapping[str, Any],
             *, source_root: Path = packet.ROOT) -> dict[str, Any]:
    """Verify exact file bytes, six triggers, rollback and no-provider scope.

    Only SOURCE validity is proven. This never verifies root ownership, active
    controller, CI, breaker, production freeze, Entra Owner, or live systemd.
    """
    require(type(manifest) is dict and set(manifest) == MANIFEST_FIELDS,
            "UNREVIEWED_FIELDS")
    require(type(scope) is dict, "SCOPE_NOT_AN_OBJECT")
    require(manifest["schema_version"] == "1.0"
            and manifest["release_mode"] == MODE
            and manifest["release_class"] == "high-risk"
            and manifest["repository"] == "al-teamaot-com/jason"
            and manifest["action"] == packet.ACTION
            and manifest["component_id"] == COMPONENT,
            "RELEASE_IDENTITY_MISMATCH")
    require(manifest["prior_root_policy_sha256"] ==
            packet.EXPECTED_PRIOR_ROOT_POLICY
            and manifest["freeze_sha256"] == packet.EXPECTED_FREEZE,
            "PROTECTED_POLICY_NOT_PINNED")
    require(manifest["protected_services"] == list(PROTECTED)
            and manifest["provider_scope"] == PROVIDER_NONE,
            "PROTECTED_OR_PROVIDER_SCOPE_CHANGED")
    require(manifest["requires_root_preflight"] is True
            and manifest["requires_signed_owner"] is True
            and manifest["standing_authority"] is False
            and manifest["production_freeze_override"] is False
            and manifest["protected_restart_allowed"] is False,
            "SECURITY_GATE_DISABLED")
    source_sha, rollback_sha = manifest["candidate_sha"], manifest["rollback_sha"]
    # The packet's own SHA validators also reject same candidate and rollback.
    try:
        reviewed = packet.prepare(
            root=source_root, candidate_sha=source_sha,
            rollback_sha=rollback_sha,
        )
    except (packet.StageEReleasePacketDenied, TypeError, ValueError) as exc:
        raise StageEManifestDenied("PMV4_E_NATIVE_MANIFEST_SOURCE_UNVERIFIED") from exc
    require(reviewed["source_scope"] == scope
            and reviewed["source_scope_sha256"] == manifest["source_scope_sha256"]
            and reviewed["source_manifest_sha256"] ==
                manifest["source_manifest_sha256"],
            "REVIEWED_SCOPE_OR_SOURCE_DIGEST_MISMATCH")
    require(manifest["reviewed_file_count"] == reviewed["reviewed_files"]
            and manifest["reviewed_file_count"] == len(packet.REVIEWED_PATHS)
            and manifest["new_systemd_file_count"] == 12
            and manifest["legacy_source_input_count"] == 12
            and reviewed["reviewed_systemd_new_files"] == 12
            and reviewed["reviewed_systemd_old_inputs"] == 12,
            "EXACT_FILES_NOT_PINNED")
    require(manifest["source_candidate_policy_sha256"] ==
            scope["source_candidate_policy_sha256"],
            "SOURCE_POLICY_CANDIDATE_MISMATCH")
    require(scope["action"] == packet.ACTION
            and scope["protected_runtime_mcp_restart_allowed"] is False
            and scope["provider_writes_allowed"] is False
            and scope["production_freeze_override_allowed"] is False,
            "EXACT_ACTION_OR_SAFETY_DRIFT")
    return {
        "status": "stage_e_typed_source_manifest_verified_no_production_authority",
        "action": packet.ACTION,
        "candidate_sha": source_sha,
        "rollback_sha": rollback_sha,
        "scope_sha256": reviewed["source_scope_sha256"],
        "manifest_sha256": sha256(packet.canonical(manifest)).hexdigest(),
        "source_files_verified": reviewed["reviewed_files"],
        "production_release_ready": False,
        "root_accepted": False,
        "owner_proof_issued": False,
        "production_mutations": False,
    }


def draft(*, candidate_sha: str, rollback_sha: str,
          source_root: Path = packet.ROOT) -> dict[str, Any]:
    """Prepare exact action bytes WITHOUT issuing authority or root trust."""
    reviewed = packet.prepare(
        root=source_root, candidate_sha=candidate_sha,
        rollback_sha=rollback_sha,
    )
    scope = reviewed["source_scope"]
    manifest = {
        "schema_version": "1.0",
        "release_mode": MODE,
        "release_class": "high-risk",
        "repository": "al-teamaot-com/jason",
        "action": packet.ACTION,
        "component_id": COMPONENT,
        "candidate_sha": candidate_sha,
        "rollback_sha": rollback_sha,
        "source_scope_sha256": reviewed["source_scope_sha256"],
        "source_manifest_sha256": reviewed["source_manifest_sha256"],
        "source_candidate_policy_sha256":
            scope["source_candidate_policy_sha256"],
        "prior_root_policy_sha256": packet.EXPECTED_PRIOR_ROOT_POLICY,
        "freeze_sha256": packet.EXPECTED_FREEZE,
        "reviewed_file_count": reviewed["reviewed_files"],
        "new_systemd_file_count": 12,
        "legacy_source_input_count": 12,
        "protected_services": list(PROTECTED),
        "provider_scope": dict(PROVIDER_NONE),
        "requires_root_preflight": True,
        "requires_signed_owner": True,
        "standing_authority": False,
        "production_freeze_override": False,
        "protected_restart_allowed": False,
    }
    verified = validate(manifest, scope, source_root=source_root)
    return {
        **verified,
        "manifest": manifest,
        "source_scope": scope,
        "signed_owner_proof": None,
        "approved_root_bootstrap": False,
    }
