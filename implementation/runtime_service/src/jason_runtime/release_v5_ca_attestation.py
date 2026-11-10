"""Read-only V5 CA/MFA enforcement evidence gate.

The Entra 'acrs' claim alone does not prove MFA happened. This root-owned
attestation is separately obtained by an approved Microsoft Entra policy read,
pinned by SHA256 in the V5 policy, never authored by the browser callback.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from .release_v5_aot_policy import (
    AotV5BrowserPolicy,
)


def verify_root_ca_enforcement_receipt(
    path: str | Path, *, browser_policy: AotV5BrowserPolicy,
    now: datetime,
) -> str:
    if browser_policy.mfa_profile=="existing_admin_role_mfa":
        return _verify_existing_admin_role_mfa_receipt(
            path,browser_policy=browser_policy,now=now)
    if browser_policy.mfa_profile!="auth_context":
        raise PermissionError("V5_MFA_PROFILE_NOT_REVIEWED")
    source=Path(path)
    try:
        info=source.lstat()
        raw=source.read_bytes()
        data=json.loads(raw)
    except (OSError,UnicodeError,ValueError,TypeError) as exc:
        raise PermissionError("V5_ENFORCED_CA_POLICY_ATTESTATION_MISSING") from exc
    if (source.is_symlink() or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid not in {0,os.geteuid()}
            or info.st_gid not in {0,os.getegid()}
            or not 50 <= len(raw) <= 8192
            or sha256(raw).hexdigest()
                != browser_policy.ca_enforcement_receipt_sha256
            or not isinstance(data,dict)
            or set(data)!={
                "schema_version","tenant_id","admin_oid",
                "browser_client_id","auth_context_id",
                "enforcement","verified_by","provider_policy_id",
                "provider_read_evidence_sha256","checked_at",
            }):
        raise PermissionError("V5_ENFORCED_CA_POLICY_ATTESTATION_NOT_REVIEWED")
    try:
        instant=datetime.fromisoformat(str(data["checked_at"]))
    except (TypeError,ValueError) as exc:
        raise PermissionError("V5_CA_POLICY_TIMESTAMP_INVALID") from exc
    if (now.tzinfo is None or instant.tzinfo is None
            or not instant <= now <= instant+timedelta(days=7)
            or data["schema_version"]!="1.0"
            or data["tenant_id"]!=browser_policy.tenant_id
            or data["admin_oid"]!=browser_policy.admin_approver_oid
            or data["browser_client_id"]!=browser_policy.browser_client_id
            or data["auth_context_id"]!=browser_policy.auth_context_id
            or data["enforcement"]!="mfa_required"
            or data["verified_by"]!="native_entra_policy_read"
            or not isinstance(data["provider_policy_id"],str)
            or not re.fullmatch(
                r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",
                data["provider_policy_id"],
            )
            or not isinstance(data["provider_read_evidence_sha256"],str)
            or not re.fullmatch(r"[0-9a-f]{64}",data["provider_read_evidence_sha256"])):
        raise PermissionError("V5_CA_MFA_ENFORCEMENT_NOT_INDEPENDENTLY_VERIFIED")
    # The caller returns this SHA, which is included in the signed decision.
    return browser_policy.ca_enforcement_receipt_sha256


def assess_exact_admin_auth_context_mfa(*, policies, admin_oid: str,
                                        auth_context_id: str) -> dict[str, object]:
    """Read-only preflight from a governed Entra CA policy list.

    This does NOT author the root CA receipt or activate V5. It proves only a
    narrow case: an enabled browser MFA policy explicitly targets the exact
    administrator and authentication context. Group/role-derived policies need
    separate independently verified membership evidence, so fail closed here.
    The caller must obtain the list from a separately authorized provider read.
    """
    import uuid
    if (not isinstance(policies, list) or not 1 <= len(policies) <= 100
            or not isinstance(admin_oid, str)
            or not isinstance(auth_context_id, str)
            or re.fullmatch(r"c[1-9][0-9]?", auth_context_id) is None):
        raise PermissionError("V5_CA_POLICY_READ_NOT_VERIFIABLE")
    try:
        if str(uuid.UUID(admin_oid)) != admin_oid:
            raise ValueError("not canonical")
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionError("V5_CA_EXACT_ADMIN_REQUIRED") from exc
    matches = []
    for policy in policies:
        if not isinstance(policy, dict):
            raise PermissionError("V5_CA_POLICY_READ_NOT_VERIFIABLE")
        conditions = policy.get("conditions") or {}
        users = conditions.get("users") or {}
        apps = conditions.get("applications") or {}
        # Microsoft Graph returns grantControls (camelCase). Legacy test
        # fixtures use grant_controls. Accept either exact shape, but a
        # conflicting dual representation is not trustworthy evidence.
        graph_grants = policy.get("grantControls")
        legacy_grants = policy.get("grant_controls")
        if (graph_grants is not None and legacy_grants is not None
                and graph_grants != legacy_grants):
            raise PermissionError("V5_CA_POLICY_READ_NOT_VERIFIABLE")
        grants = (graph_grants if graph_grants is not None
                  else legacy_grants) or {}
        if (not isinstance(conditions, dict)
                or not isinstance(users, dict)
                or not isinstance(apps, dict)
                or not isinstance(grants, dict)):
            raise PermissionError("V5_CA_POLICY_READ_NOT_VERIFIABLE")
        if auth_context_id not in (apps.get("includeAuthenticationContextClassReferences") or []):
            continue
        if (policy.get("state") != "enabled"
                or "mfa" not in (grants.get("builtInControls") or [])
                or (grants.get("operator") not in {"AND", "OR"})
                or admin_oid not in (users.get("includeUsers") or [])
                or admin_oid in (users.get("excludeUsers") or [])
                or (users.get("excludeGroups") or [])
                or (users.get("excludeRoles") or [])
                or not any(x in (conditions.get("clientAppTypes") or [])
                           for x in ("browser", "all"))):
            continue
        try:
            if str(uuid.UUID(policy.get("id"))) != policy["id"]:
                continue
        except (TypeError, ValueError, AttributeError, KeyError):
            continue
        matches.append(policy)
    if len(matches) != 1:
        raise PermissionError("V5_CA_EXACT_AUTH_CONTEXT_MFA_NOT_PROVEN")
    # A content digest is useful for human/root review, but not equivalent to
    # a signed or root-protected enforcement receipt. Never return approval.
    raw = json.dumps(matches[0], sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return {
        "status": "candidate_requires_independent_root_review",
        "provider_policy_id": matches[0]["id"],
        "provider_read_evidence_sha256": sha256(raw).hexdigest(),
        "auth_context_id": auth_context_id,
        "approval_authorized": False,
    }


def assess_existing_admin_role_browser_mfa(
    *, policies, role_assignments, tenant_id: str, admin_oid: str,
    browser_client_id: str,
) -> dict[str, object]:
    """Read-only exploration of a license-free *configuration-change* route.

    Existing all-cloud-apps admin MFA is stronger evidence than an unprotected
    auth-context acrs token, but this function does not enable an alternate
    V5 approval, authorize tenant writes, or waive any V5 root CA gate.
    It identifies an exact, unexcluded role-bound policy that a separate
    privileged sign-in + token MFA proof could potentially reuse after
    explicit security review.
    """
    import uuid

    def uuid_ok(value):
        try:
            return type(value) is str and str(uuid.UUID(value)) == value
        except (ValueError, TypeError, AttributeError):
            return False

    if (not all(uuid_ok(v) for v in
                (tenant_id, admin_oid, browser_client_id))
            or type(policies) is not list or not 1 <= len(policies) <= 100
            or type(role_assignments) is not list
            or not 1 <= len(role_assignments) <= 1000):
        raise PermissionError("V5_EXISTING_ADMIN_MFA_INPUTS_NOT_VERIFIED")
    relevant_roles = set()
    evidence_assignments = []
    for assignment in role_assignments:
        if not isinstance(assignment, dict):
            raise PermissionError("V5_EXISTING_ADMIN_MFA_ROLE_EVIDENCE_INVALID")
        if assignment.get("principalId") != admin_oid:
            continue
        role = assignment.get("roleDefinitionId")
        if (not uuid_ok(role)
                or assignment.get("directoryScopeId") != "/"
                or assignment.get("principalOrganizationId") != tenant_id):
            raise PermissionError("V5_EXISTING_ADMIN_MFA_ROLE_EVIDENCE_INVALID")
        relevant_roles.add(role)
        evidence_assignments.append(assignment)
    if not relevant_roles:
        raise PermissionError("V5_EXISTING_ADMIN_MFA_NO_ADMIN_ROLE_PROOF")
    matching=[]
    for policy in policies:
        if not isinstance(policy, dict):
            raise PermissionError("V5_EXISTING_ADMIN_MFA_POLICY_EVIDENCE_INVALID")
        conditions=policy.get("conditions") or {}
        users=conditions.get("users") or {}
        apps=conditions.get("applications") or {}
        grants=policy.get("grantControls")
        if (grants is None or not isinstance(grants, dict)
                or not isinstance(conditions, dict)
                or not isinstance(users, dict)
                or not isinstance(apps, dict)):
            continue
        include_roles=users.get("includeRoles") or []
        exclusions=set(users.get("excludeRoles") or [])
        if (policy.get("state") != "enabled"
                or not uuid_ok(policy.get("id"))
                or not relevant_roles.intersection(include_roles)
                or relevant_roles.intersection(exclusions)
                or admin_oid in (users.get("excludeUsers") or [])
                or users.get("excludeGroups")
                or users.get("excludeGuestsOrExternalUsers")
                or apps.get("excludeApplications")
                or apps.get("applicationFilter")
                or apps.get("includeAuthenticationContextClassReferences")
                or apps.get("includeApplications") != ["All"]
                or not any(v in (conditions.get("clientAppTypes") or [])
                           for v in ("browser","all"))
                or sorted(grants.get("builtInControls") or []) != ["mfa"]
                or grants.get("operator") not in ("AND","OR")
                or any(conditions.get(k) for k in (
                    "locations","devices","platforms","userRiskLevels",
                    "signInRiskLevels","servicePrincipalRiskLevels",
                    "clientApplications","authenticationFlows",
                    "insiderRiskLevels"))):
            continue
        matching.append(policy)
    if len(matching)!=1:
        raise PermissionError("V5_EXISTING_ADMIN_ROLE_MFA_NOT_PROVEN")
    used_roles=sorted(set(matching[0]["conditions"]["users"]["includeRoles"])
                      & relevant_roles)
    proof={
        "tenant_id":tenant_id,
        "admin_oid":admin_oid,
        "browser_client_id":browser_client_id,
        "provider_policy_id":matching[0]["id"],
        "admin_role_ids":used_roles,
        "policy":matching[0],
        "role_assignments":[a for a in evidence_assignments
                            if a["roleDefinitionId"] in used_roles],
    }
    raw=json.dumps(proof,sort_keys=True,separators=(",",":"),
                   ensure_ascii=False,allow_nan=False).encode("utf-8")
    return {
        "status":"candidate_requires_independent_root_review",
        "provider_policy_id":matching[0]["id"],
        "matching_role_count":len(used_roles),
        "provider_read_evidence_sha256":sha256(raw).hexdigest(),
        "approval_authorized":False,
        "requires_separate_privileged_oidc_mfa_token":True,
        "requires_teams_owner_release_authorization":True,
    }


def _verify_existing_admin_role_mfa_receipt(
    path: str | Path, *, browser_policy: AotV5BrowserPolicy,
    now: datetime,
) -> str:
    """Verify pinned, separately obtained existing-role MFA policy evidence.

    No new tenant CA policy, context or admin Teams license is required.
    The browser must also prove fresh cryptographic Entra MFA (amr).
    """
    source=Path(path)
    try:
        info=source.lstat()
        raw=source.read_bytes()
        data=json.loads(raw)
    except (OSError,UnicodeError,ValueError,TypeError) as exc:
        raise PermissionError("V5_ROLE_MFA_ATTESTATION_MISSING") from exc
    fields={
        "schema_version","tenant_id","admin_oid","browser_client_id",
        "mfa_profile","enforcement","verified_by","provider_policy_id",
        "provider_read_evidence_sha256","admin_role_ids","checked_at",
    }
    if (source.is_symlink() or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode)!=0o600
            or info.st_uid not in {0,os.geteuid()}
            or info.st_gid not in {0,os.getegid()}
            or not 50<=len(raw)<=8192
            or sha256(raw).hexdigest()
                !=browser_policy.ca_enforcement_receipt_sha256
            or not isinstance(data,dict) or set(data)!=fields):
        raise PermissionError("V5_ROLE_MFA_ATTESTATION_NOT_REVIEWED")
    import uuid

    def uuid_ok(value):
        try:
            return type(value) is str and str(uuid.UUID(value))==value
        except (ValueError,TypeError,AttributeError):
            return False

    try:
        instant=datetime.fromisoformat(data["checked_at"])
    except (TypeError,ValueError) as exc:
        raise PermissionError("V5_ROLE_MFA_ATTESTATION_TIMESTAMP_INVALID") from exc
    if (now.tzinfo is None or instant.tzinfo is None
            or not instant<=now<=instant+timedelta(hours=24)
            or data["schema_version"]!="2.0"
            or data["tenant_id"]!=browser_policy.tenant_id
            or data["admin_oid"]!=browser_policy.admin_approver_oid
            or data["browser_client_id"]!=browser_policy.browser_client_id
            or data["mfa_profile"]!="existing_admin_role_mfa"
            or data["enforcement"]!="mfa_required"
            or data["verified_by"]!="native_entra_policy_and_admin_roles_read"
            or not uuid_ok(data["provider_policy_id"])
            or type(data["provider_read_evidence_sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}",
                                data["provider_read_evidence_sha256"])
            or not isinstance(data["admin_role_ids"],list)
            or not 1<=len(data["admin_role_ids"])<=50
            or not all(uuid_ok(x) for x in data["admin_role_ids"])
            or len(set(data["admin_role_ids"]))!=len(data["admin_role_ids"])):
        raise PermissionError("V5_ROLE_MFA_ENFORCEMENT_NOT_INDEPENDENTLY_VERIFIED")
    return browser_policy.ca_enforcement_receipt_sha256
