"""Versioned, organization-policy-bound Entra admin browser release approval.

No tenant, personal account, owner or hostname is compiled into approval code.
The root-reviewed 0600 policy supplies exact Entra OIDs after owner/group
eligibility has been independently established. Source support is dormant.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
import ipaddress
import re
import uuid

CHANNEL = "microsoft_entra_browser_stepup"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
AUTH_CONTEXT = re.compile(r"^c[1-9][0-9]?$")
OWNER_ID = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
ORG_ID = re.compile(r"^[a-z][a-z0-9_.:-]{1,127}$")
NOTICE_PATH = "/admin/release-approval"
CALLBACK_PATH = "/admin/release-approval/callback"


def _reviewed_origin(value: Any, expected_path: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise PermissionError("V5_REVIEWED_APPROVAL_ENDPOINT_REQUIRED")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        if not host or host == "localhost" or host.endswith((".local", ".internal")):
            raise ValueError("unreviewable host")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("IP address is not a reviewed FQDN")
        port = parsed.port
    except ValueError as exc:
        raise PermissionError("V5_REVIEWED_APPROVAL_ENDPOINT_REQUIRED") from exc
    if (parsed.scheme != "https" or "." not in host
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443)
            or parsed.path != expected_path
            or parsed.query or parsed.fragment
            or value != f"https://{parsed.netloc}{expected_path}"):
        raise PermissionError("V5_REVIEWED_APPROVAL_ENDPOINT_REQUIRED")
    return f"https://{parsed.netloc}"


@dataclass(frozen=True)
class AotV5BrowserPolicy:
    """Legacy type name; data is generic and root policy authoritative."""
    browser_client_id: str
    auth_context_id: str
    ca_enforcement_receipt_sha256: str
    signer_public_key_sha256: str
    callback_uri: str
    notice_uri: str
    tenant_id: str
    admin_approver_oid: str
    requester_oid: str
    owner_identity_id: str
    organization_id: str
    # The existing-role-MFA alternative is OFF unless an exact V5 root
    # policy explicitly selects it after independent security review.
    mfa_profile: str = "auth_context"

    @classmethod
    def parse(cls, data: Any, *, admin: tuple[str, str],
              regular: tuple[str, str], owner_identity_id: str,
              organization_id: str) -> "AotV5BrowserPolicy":
        base_fields={
            "browser_client_id", "auth_context_id",
            "ca_enforcement_receipt_sha256", "signer_public_key_sha256",
            "callback_uri", "notice_uri", "channel", "teams_notice_only",
            "separate_admin_browser_login", "owner_role", "no_admin_teams_license",
        }
        # Opt-in alternative: reuse independently attested, existing admin
        # role MFA without creating any new Conditional Access policy or
        # licensing the separated administrator for Teams.
        profile=(data.get("mfa_profile") if isinstance(data,dict)
                 else None) or "auth_context"
        expected=(base_fields if profile=="auth_context"
                  else (base_fields-{"auth_context_id"}|{"mfa_profile"})
                  if profile=="existing_admin_role_mfa" else set())
        if not isinstance(data, dict) or set(data) != expected:
            raise PermissionError("V5_REVIEWED_POLICY_FIELDS_INVALID")
        if (data.get("channel") != CHANNEL
                or data.get("owner_role") != owner_identity_id
                or data.get("teams_notice_only") is not True
                or data.get("separate_admin_browser_login") is not True
                or data.get("no_admin_teams_license") is not True
                or not isinstance(owner_identity_id, str)
                or not OWNER_ID.fullmatch(owner_identity_id)
                or not isinstance(organization_id, str)
                or not ORG_ID.fullmatch(organization_id)):
            raise PermissionError("V5_REVIEWED_APPROVAL_CHANNEL_NOT_AUTHORIZED")
        if (len(admin) != 2 or len(regular) != 2
                or admin[0] != regular[0] or admin[1] == regular[1]
                or not all(isinstance(i, str) and str(uuid.UUID(i)) == i
                           for i in (*admin, *regular))):
            raise PermissionError("V5_SEPARATE_ENTRA_OWNER_REQUIRED")
        try:
            client = str(uuid.UUID(data["browser_client_id"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise PermissionError("V5_REVIEWED_BROWSER_CLIENT_REQUIRED") from exc
        context=data.get("auth_context_id")
        if (client != data["browser_client_id"]
                or (profile=="auth_context" and
                    (not isinstance(context,str)
                     or not AUTH_CONTEXT.fullmatch(context)))
                or (profile=="existing_admin_role_mfa" and context is not None)
                or any(not isinstance(data[key], str)
                       or not SHA256.fullmatch(data[key])
                       or data[key] == "0" * 64
                       for key in ("ca_enforcement_receipt_sha256",
                                   "signer_public_key_sha256"))):
            raise PermissionError("V5_REVIEWED_BROWSER_POLICY_REQUIRED")
        if (_reviewed_origin(data["callback_uri"], CALLBACK_PATH)
                != _reviewed_origin(data["notice_uri"], NOTICE_PATH)):
            raise PermissionError("V5_REVIEWED_APPROVAL_ORIGIN_MISMATCH")
        return cls(
            client, context,
            data["ca_enforcement_receipt_sha256"],
            data["signer_public_key_sha256"],
            data["callback_uri"], data["notice_uri"],
            admin[0], admin[1], regular[1],
            owner_identity_id, organization_id, profile,
        )
