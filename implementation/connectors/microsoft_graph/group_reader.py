"""Bounded Microsoft Graph group/user readback for governed group writes.

Reads use an independent, approved read-only Microsoft application identity.
Neither callers nor Microsoft response links may redirect this transport.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote, urlsplit
from uuid import UUID

from connectors.core.contracts import ConnectorTransportError, HttpTransport
from .user_directory import MicrosoftGraphUserDirectoryReader, TenantApplicationTokenProvider

_BASE = "https://graph.microsoft.com/v1.0"
_GROUP_FIELDS = "id,displayName,mailNickname,groupTypes,mailEnabled,securityEnabled,isAssignableToRole,onPremisesSyncEnabled"
_MAX_PAGES = 25


def canonical_uuid(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("Microsoft object identifier is missing")
    try:
        parsed = str(UUID(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Microsoft object identifier is not a UUID") from exc
    if parsed != raw.lower():
        raise ValueError("Microsoft object identifier is not canonical")
    return parsed


@dataclass(frozen=True, slots=True)
class MicrosoftGraphGroupReader:
    tokens: TenantApplicationTokenProvider
    transport: HttpTransport
    users: MicrosoftGraphUserDirectoryReader

    def _get(self, *, tenant_id: str, path: str, params: Mapping[str, Any] | None = None,
             next_link: str | None = None) -> Mapping[str, Any]:
        tenant_id = canonical_uuid(tenant_id)
        target = _BASE + path
        if next_link is not None:
            if not isinstance(next_link, str) or len(next_link) > 4096:
                raise ConnectorTransportError("Microsoft Graph pagination link invalid")
            parts = urlsplit(next_link)
            if (parts.scheme != "https" or parts.hostname != "graph.microsoft.com"
                    or parts.port is not None or parts.username is not None
                    or parts.password is not None or parts.fragment
                    or parts.path != "/v1.0" + path
                    or not parts.query):
                raise ConnectorTransportError("Microsoft Graph pagination origin or path changed")
            target = next_link
            params = None
        token = self.tokens.access_token_for_tenant(microsoft_tenant_id=tenant_id)
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("Microsoft directory read token unavailable")
        result = self.transport.request(
            method="GET", url=target,
            headers={"Authorization": "Bearer " + token},
            params=params, timeout_seconds=20.0,
        )
        if not isinstance(result, Mapping):
            raise ConnectorTransportError("Microsoft Graph read returned an invalid object")
        return result

    def find_groups_by_alias(self, *, tenant_id: str, alias: str) -> tuple[Mapping[str, Any], ...]:
        # This alias has already been constrained by the operation catalog.
        if (not isinstance(alias, str) or not alias or len(alias) > 64
                or not alias.isascii() or not all(c.isalnum() or c in "._-" for c in alias)):
            raise ValueError("Invalid group mail nickname")
        result = self._get(
            tenant_id=tenant_id, path="/groups",
            params={"$filter": "mailNickname eq '" + alias + "'",
                    "$select": _GROUP_FIELDS, "$top": 2},
        )
        items = result.get("value")
        if not isinstance(items, list) or len(items) > 2 or result.get("@odata.nextLink"):
            raise ConnectorTransportError("Microsoft group alias search was incomplete")
        for item in items:
            if not isinstance(item, Mapping) or str(item.get("mailNickname", "")).casefold() != alias.casefold():
                raise ConnectorTransportError("Microsoft group alias search identity mismatch")
            canonical_uuid(item.get("id"))
        return tuple(items)

    def read_group(self, *, tenant_id: str, group_id: str) -> Mapping[str, Any]:
        group_id = canonical_uuid(group_id)
        item = self._get(
            tenant_id=tenant_id,
            path="/groups/" + quote(group_id, safe=""),
            params={"$select": _GROUP_FIELDS},
        )
        if canonical_uuid(item.get("id")) != group_id:
            raise ConnectorTransportError("Microsoft group readback identity mismatch")
        return item

    def read_user(self, *, tenant_id: str, user_id: str) -> Mapping[str, Any]:
        user_id = canonical_uuid(user_id)
        user = self.users.read_user(
            microsoft_tenant_id=canonical_uuid(tenant_id),
            microsoft_object_id=user_id,
        )
        if canonical_uuid(user.get("id")) != user_id:
            raise ConnectorTransportError("Microsoft user identity mismatch")
        if user.get("accountEnabled") is not True:
            raise PermissionError("Microsoft target user must be active")
        return user

    def _contains(self, *, tenant_id: str, group_id: str, user_id: str, relationship: str) -> bool:
        group_id = canonical_uuid(group_id)
        user_id = canonical_uuid(user_id)
        if relationship not in {"owners", "members"}:
            raise ValueError("Unsupported Microsoft group relationship")
        path = "/groups/" + group_id + "/" + relationship
        link = None
        visited: set[str] = set()
        for _ in range(_MAX_PAGES):
            response = self._get(
                tenant_id=tenant_id, path=path,
                params={"$select": "id", "$top": 100} if link is None else None,
                next_link=link,
            )
            raw = response.get("value")
            if not isinstance(raw, list) or len(raw) > 100:
                raise ConnectorTransportError("Microsoft group relationship response was incomplete")
            for item in raw:
                if not isinstance(item, Mapping):
                    raise ConnectorTransportError("Microsoft group relationship record is invalid")
                if canonical_uuid(item.get("id")) == user_id:
                    return True
            link = response.get("@odata.nextLink")
            if link is None:
                return False
            if not isinstance(link, str) or link in visited:
                raise ConnectorTransportError("Microsoft group relationship pagination invalid")
            visited.add(link)
        raise ConnectorTransportError("Microsoft group relationship pagination limit reached")

    def is_member(self, *, tenant_id: str, group_id: str, user_id: str) -> bool:
        return self._contains(tenant_id=tenant_id, group_id=group_id,
                              user_id=user_id, relationship="members")

    def is_owner(self, *, tenant_id: str, group_id: str, user_id: str) -> bool:
        return self._contains(tenant_id=tenant_id, group_id=group_id,
                              user_id=user_id, relationship="owners")
