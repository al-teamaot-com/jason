"""Opt-in, source-only Owner approval-role separation for a service-originated release.

NOT a Teams sender, signed approval callback, capability registration or release
controller. Existing V4 remains live. A future exact-SHA release must separately
integrate this contract into native issuance, signed callback and host admission.
"""
from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path

_UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRED = frozenset({
    "schema_version", "policy_mode", "organization_id", "microsoft_tenant_id",
    "owner_approver_object_id", "privileged_admin_object_id",
    "release_requester_principal_id", "requester_kind",
    "requires_signed_teams", "requires_native_release_manager",
    "forbid_self_approval", "production_freeze_preserved",
})


class OwnerTeamsRoleError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class OwnerTeamsRolePolicy:
    tenant_id: str
    owner_approver_object_id: str
    privileged_admin_object_id: str
    requester_principal_id: str

    def require_service_originated_release(
        self, *, requester_principal_id: str, requester_kind: str,
        approver_tenant_id: str, approver_object_id: str,
        candidate_sha: str, rollback_sha: str, scope_sha256: str,
        signed_original_decision_verified: bool,
        native_release_eligible: bool,
    ) -> dict[str, str]:
        """Validate an external verifier's facts, never issue approval or deploy.

        Authority still depends on original signed Teams evidence, provider
        identity, native Release Manager and independently reviewed release.
        """
        if (
            requester_kind != "service"
            or requester_principal_id != self.requester_principal_id
            or approver_tenant_id != self.tenant_id
            or approver_object_id != self.owner_approver_object_id
            or approver_object_id == self.privileged_admin_object_id
            or not signed_original_decision_verified
            or not native_release_eligible
            or not isinstance(candidate_sha, str)
            or not isinstance(rollback_sha, str)
            or not isinstance(scope_sha256, str)
            or not _SHA.fullmatch(candidate_sha)
            or not _SHA.fullmatch(rollback_sha)
            or candidate_sha == rollback_sha
            or not _DIGEST.fullmatch(scope_sha256)
        ):
            raise OwnerTeamsRoleError("No signed, eligible, exact service-originated Owner release")
        return {
            "candidate_sha": candidate_sha,
            "rollback_sha": rollback_sha,
            "scope_sha256": scope_sha256,
            "owner_approver_object_id": self.owner_approver_object_id,
            "native_mutation_authorized": "false",
        }


def read_owner_role_policy(path: Path) -> OwnerTeamsRolePolicy:
    """Require strict private versioned policy. No defaults or account fallback."""
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid not in (0, __import__("os").geteuid())
            or not 100 <= info.st_size <= 4096):
        raise OwnerTeamsRoleError("Owner policy must be private and regular")
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) != _REQUIRED:
        raise OwnerTeamsRoleError("Owner policy schema is not exact")
    if (
        data["schema_version"] != "5.0"
        or data["policy_mode"] != "service_requester_regular_owner_teams"
        or data["organization_id"] != "aot"
        or data["requester_kind"] != "service"
        or data["requires_signed_teams"] is not True
        or data["requires_native_release_manager"] is not True
        or data["forbid_self_approval"] is not True
        or data["production_freeze_preserved"] is not True
        or not isinstance(data["release_requester_principal_id"], str)
        or data["release_requester_principal_id"] != "svc-jason-release-manager"
        or any(not isinstance(data[k], str) or not _UUID.fullmatch(data[k])
               for k in ("microsoft_tenant_id", "owner_approver_object_id",
                         "privileged_admin_object_id"))
        or data["owner_approver_object_id"] == data["privileged_admin_object_id"]
    ):
        raise OwnerTeamsRoleError("Owner role separation policy rejected")
    return OwnerTeamsRolePolicy(
        data["microsoft_tenant_id"], data["owner_approver_object_id"],
        data["privileged_admin_object_id"], data["release_requester_principal_id"],
    )
