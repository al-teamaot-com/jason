from __future__ import annotations

from dataclasses import dataclass, field
from time import sleep
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote

from connectors.core.contracts import ConnectorTransportError, HttpTransport


class TenantApplicationTokenProvider(Protocol):
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str: ...


@dataclass(frozen=True, slots=True)
class MicrosoftGraphSecurityPostureReader:
    """Bounded Microsoft Graph security-posture reads in one validated tenant."""

    tokens: TenantApplicationTokenProvider
    transport: HttpTransport
    base_url: str = "https://graph.microsoft.com/v1.0"
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    max_retry_delay_seconds: float = 5.0
    sleeper: Callable[[float], None] = field(default=sleep, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != "https://graph.microsoft.com/v1.0":
            raise ValueError("Microsoft security posture must use Graph v1.0 public cloud")

    def authentication_methods(self, *, microsoft_tenant_id: str, user_id: str) -> Mapping[str, Any]:
        uid = user_id.strip()
        if not uid:
            raise ValueError("user_id is required")
        response = self._get(
            tenant_id=microsoft_tenant_id,
            path=f"/users/{quote(uid, safe='')}/authentication/methods",
            params={},
        )
        values = response.get("value")
        if not isinstance(values, list):
            raise ConnectorTransportError("Microsoft authentication methods returned an unexpected shape")
        items = []
        for item in values:
            if not isinstance(item, Mapping):
                raise ConnectorTransportError("Microsoft authentication methods returned an invalid record")
            items.append({
                "id": item.get("id"),
                "method_type": item.get("@odata.type"),
            })
        return {"items": items, "count": len(items), "user_id": uid}

    def conditional_access_policies(self, *, microsoft_tenant_id: str, maximum_records: int = 100) -> Mapping[str, Any]:
        maximum = int(maximum_records)
        if not 1 <= maximum <= 100:
            raise ValueError("page_size must be between 1 and 100")
        response = self._get(
            tenant_id=microsoft_tenant_id,
            path="/identity/conditionalAccess/policies",
            params={"$top": maximum},
        )
        values = response.get("value")
        if not isinstance(values, list):
            raise ConnectorTransportError("Microsoft Conditional Access returned an unexpected shape")
        if len(values) > maximum:
            raise ConnectorTransportError("Microsoft Conditional Access exceeded the requested bound")
        items=[]
        for item in values:
            if not isinstance(item, Mapping):
                raise ConnectorTransportError("Microsoft Conditional Access returned an invalid record")
            items.append({
                "id": item.get("id"), "display_name": item.get("displayName"),
                "state": item.get("state"), "created_at": item.get("createdDateTime"),
                "modified_at": item.get("modifiedDateTime"), "conditions": item.get("conditions"),
                "grant_controls": item.get("grantControls"), "session_controls": item.get("sessionControls"),
            })
        return {"items": items, "count": len(items)}

    def directory_roles(self, *, microsoft_tenant_id: str, maximum_records: int = 100) -> Mapping[str, Any]:
        maximum=int(maximum_records)
        if not 1 <= maximum <= 100:
            raise ValueError("page_size must be between 1 and 100")
        response=self._get(tenant_id=microsoft_tenant_id,path="/directoryRoles",params={"$top":maximum})
        values=response.get("value")
        if not isinstance(values,list): raise ConnectorTransportError("Microsoft directory roles returned an unexpected shape")
        items=[{"id":x.get("id"),"display_name":x.get("displayName"),"role_template_id":x.get("roleTemplateId")} for x in values if isinstance(x,Mapping)]
        if len(items)!=len(values): raise ConnectorTransportError("Microsoft directory roles returned an invalid record")
        return {"items":items,"count":len(items)}

    def role_members(self, *, microsoft_tenant_id: str, role_id: str, maximum_records: int = 100) -> Mapping[str, Any]:
        rid=role_id.strip(); maximum=int(maximum_records)
        if not rid: raise ValueError("role_id is required")
        if not 1 <= maximum <= 100: raise ValueError("page_size must be between 1 and 100")
        response=self._get(tenant_id=microsoft_tenant_id,path=f"/directoryRoles/{quote(rid,safe='')}/members",params={"$top":maximum})
        values=response.get("value")
        if not isinstance(values,list): raise ConnectorTransportError("Microsoft directory role members returned an unexpected shape")
        items=[]
        for x in values:
            if not isinstance(x,Mapping): raise ConnectorTransportError("Microsoft directory role members returned an invalid record")
            items.append({"id":x.get("id"),"display_name":x.get("displayName"),"user_principal_name":x.get("userPrincipalName"),"account_enabled":x.get("accountEnabled"),"object_type":x.get("@odata.type")})
        return {"items":items,"count":len(items),"role_id":rid}

    def _get(self, *, tenant_id: str, path: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        tenant=tenant_id.strip()
        if not tenant: raise ValueError("Microsoft tenant identifier is required")
        token=self.tokens.access_token_for_tenant(microsoft_tenant_id=tenant)
        if not isinstance(token,str) or not token.strip(): raise PermissionError("Microsoft Graph application token is unavailable")
        for attempt in range(1,self.max_attempts+1):
            try:
                return self.transport.request(method="GET",url=f"{self.base_url.rstrip('/')}{path}",headers={"Authorization":f"Bearer {token.strip()}"},params=params,timeout_seconds=self.timeout_seconds)
            except ConnectorTransportError as error:
                if error.status_code != 429 or attempt >= self.max_attempts: raise
                delay=error.retry_after_seconds if error.retry_after_seconds is not None else float(2 ** (attempt-1))
                delay=min(max(delay,0.0),self.max_retry_delay_seconds)
                if delay: self.sleeper(delay)
        raise RuntimeError("unreachable Microsoft security posture retry state")
