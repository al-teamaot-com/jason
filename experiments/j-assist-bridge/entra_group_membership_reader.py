"""Server-owned Microsoft Graph membership adapter for J-Assist preproduction.

No credentials, network transport, OAuth audience or browser token are
constructed here. The caller must inject a governed Microsoft Graph
application-permission client with authenticated AOT tenant binding.
The adapter is not registered to Jason production.

Required Graph app permissions for a user other than the app identity:
User.Read.All and GroupMember.Read.All (or reviewed Directory.Read.All).
Do not grant these to the J-Assist SPA; they belong exclusively to a
server-side, least-privilege read-only Graph service identity.

Graph checkMemberGroups is TRANSITIVE. If direct-only membership becomes
a business requirement, use a direct-membership provider operation and
update this contract rather than mislabeling transitive proof.
"""
from __future__ import annotations

from typing import Callable
import re

from entra_group_screen_authority import (
    AOT_JASSIST_PILOT_GROUP_ID, EntraGroupEvidence,
)
from entra_send_authority import AOT_ENTRA_TENANT_ID

GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


class GraphMembershipReader:
    """Read-through, no persistent membership caching, fail closed."""

    def __init__(
        self, *,
        get_json: Callable[[str], dict],
        post_json: Callable[[str, dict], dict],
    ):
        if not callable(get_json) or not callable(post_json):
            raise ValueError("server-owned Microsoft Graph transport required")
        self._get = get_json
        self._post = post_json

    def __call__(self, tenant: str, user_oid: str, group_id: str) -> EntraGroupEvidence:
        if (tenant != AOT_ENTRA_TENANT_ID
                or not isinstance(user_oid, str) or not GUID.fullmatch(user_oid)
                or not isinstance(group_id, str)
                or group_id.casefold() != AOT_JASSIST_PILOT_GROUP_ID):
            raise ValueError("only the exact AOT user/group binding is supported")

        oid = user_oid.lower()
        url = GRAPH_ROOT + "/users/" + oid
        profile = self._get(url + "?$select=id,accountEnabled")
        if (not isinstance(profile, dict)
                or not isinstance(profile.get("id"), str)
                or profile["id"].casefold() != oid
                or type(profile.get("accountEnabled")) is not bool):
            raise ValueError("unverified Entra user state")
        # No member inquiry for disabled user; fail immediately.
        enabled = profile["accountEnabled"]
        if not enabled:
            return EntraGroupEvidence(
                user_oid=oid, tenant_id=tenant, group_id=AOT_JASSIST_PILOT_GROUP_ID,
                is_member=False, account_enabled=False, verified_by_graph=True,
            )
        check = self._post(url + "/checkMemberGroups", {
            "groupIds": [AOT_JASSIST_PILOT_GROUP_ID]
        })
        if (not isinstance(check, dict) or type(check.get("value")) is not list):
            raise ValueError("invalid Graph membership response")
        values = check["value"]
        # Since only one exact group was requested, any extra value, wrong
        # shape or duplicate signals an invalid/unexpected provider result.
        if (len(values) > 1 or any(
            not isinstance(value, str)
            or value.casefold() != AOT_JASSIST_PILOT_GROUP_ID
            for value in values
        )):
            raise ValueError("unexpected Graph membership group ID")
        return EntraGroupEvidence(
            user_oid=oid, tenant_id=tenant, group_id=AOT_JASSIST_PILOT_GROUP_ID,
            is_member=(len(values) == 1),
            account_enabled=True, verified_by_graph=True,
        )
