"""Read bounded Microsoft Entra user profile data through Microsoft Graph.

The directory reader accepts only a Microsoft tenant that has already crossed Jason's
validated client-boundary layer. Conversation input never supplies credentials, Graph
hosts, permission profiles, or arbitrary OData expressions. User search is intentionally
limited to exact equality selectors and a small bounded result set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import sleep
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote

from connectors.core.contracts import ConnectorTransportError, HttpTransport


class TenantApplicationTokenProvider(Protocol):
    def access_token_for_tenant(
        self,
        *,
        microsoft_tenant_id: str,
    ) -> str: ...


_USER_SELECT = "id,displayName,mail,userPrincipalName,accountEnabled"
_SEARCH_FIELDS = {
    "email": "mail",
    "user_principal_name": "userPrincipalName",
    "display_name": "displayName",
}


def _odata_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True, slots=True)
class MicrosoftGraphUserDirectoryReader:
    tokens: TenantApplicationTokenProvider
    transport: HttpTransport
    base_url: str = "https://graph.microsoft.com/v1.0"
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    max_retry_delay_seconds: float = 5.0
    sleeper: Callable[[float], None] = field(default=sleep, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != "https://graph.microsoft.com/v1.0":
            raise ValueError("Microsoft user directory must use Graph v1.0 public cloud")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts < 1 or self.max_attempts > 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if self.max_retry_delay_seconds < 0 or self.max_retry_delay_seconds > 30:
            raise ValueError("max_retry_delay_seconds must be between 0 and 30")

    def resolve_email(
        self,
        *,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
    ) -> str | None:
        response = self.read_user(
            microsoft_tenant_id=microsoft_tenant_id,
            microsoft_object_id=microsoft_object_id,
        )
        return self._extract_email(
            response=response,
            expected_object_id=microsoft_object_id.strip(),
        )

    def read_user(
        self,
        *,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
    ) -> Mapping[str, Any]:
        tenant_id = microsoft_tenant_id.strip()
        object_id = microsoft_object_id.strip()
        if not tenant_id or not object_id:
            raise ValueError("Microsoft tenant and object identifiers are required")

        token = self._token_for_tenant(tenant_id)
        response = self._request(
            token=token,
            url=f"{self.base_url.rstrip('/')}/users/{quote(object_id, safe='')}",
            params={"$select": _USER_SELECT},
        )
        returned_id = str(response.get("id", "")).strip()
        if not returned_id or returned_id.casefold() != object_id.casefold():
            raise PermissionError("Microsoft Graph user identity did not match requested object")
        return self._project_user(response)

    def search_users(
        self,
        *,
        microsoft_tenant_id: str,
        selector: str,
        value: str,
        maximum_records: int = 10,
    ) -> tuple[Mapping[str, Any], ...]:
        tenant_id = microsoft_tenant_id.strip()
        selector_name = selector.strip()
        selector_value = value.strip()
        if not tenant_id:
            raise ValueError("Microsoft tenant identifier is required")
        graph_field = _SEARCH_FIELDS.get(selector_name)
        if graph_field is None:
            raise ValueError("Unsupported Microsoft user search selector")
        if not selector_value:
            raise ValueError("Microsoft user search value is required")
        if isinstance(maximum_records, bool) or not 1 <= int(maximum_records) <= 25:
            raise ValueError("maximum_records must be between 1 and 25")

        token = self._token_for_tenant(tenant_id)
        response = self._request(
            token=token,
            url=f"{self.base_url.rstrip('/')}/users",
            params={
                "$filter": f"{graph_field} eq {_odata_string(selector_value)}",
                "$select": _USER_SELECT,
                "$top": int(maximum_records),
            },
        )
        raw = response.get("value")
        if not isinstance(raw, list):
            raise ConnectorTransportError("Microsoft Graph user search returned an unexpected shape")
        if len(raw) > int(maximum_records):
            raise ConnectorTransportError("Microsoft Graph user search exceeded the requested bound")

        projected = []
        for item in raw:
            if not isinstance(item, Mapping):
                raise ConnectorTransportError("Microsoft Graph user search returned an invalid record")
            projected.append(self._project_user(item))
        return tuple(projected)

    def _token_for_tenant(self, tenant_id: str) -> str:
        token = self.tokens.access_token_for_tenant(
            microsoft_tenant_id=tenant_id,
        )
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("Microsoft Graph application token is unavailable")
        return token.strip()

    def _request(
        self,
        *,
        token: str,
        url: str,
        params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Perform a bounded retry only for explicit HTTP throttling."""

        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.transport.request(
                    method="GET",
                    url=url,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                    timeout_seconds=self.timeout_seconds,
                )
            except ConnectorTransportError as error:
                if error.status_code != 429 or attempt >= self.max_attempts:
                    raise
                delay = error.retry_after_seconds
                if delay is None:
                    delay = float(2 ** (attempt - 1))
                delay = min(max(delay, 0.0), self.max_retry_delay_seconds)
                if delay > 0:
                    self.sleeper(delay)

        raise RuntimeError("unreachable Microsoft directory retry state")

    def _request_user(self, *, token: str, object_id: str) -> Mapping[str, Any]:
        """Compatibility seam retained for existing focused tests."""
        return self._request(
            token=token,
            url=f"{self.base_url.rstrip('/')}/users/{quote(object_id, safe='')}",
            params={"$select": _USER_SELECT},
        )

    @staticmethod
    def _project_user(response: Mapping[str, Any]) -> Mapping[str, Any]:
        user_id = str(response.get("id", "")).strip()
        if not user_id:
            raise ConnectorTransportError("Microsoft Graph user record did not include an id")
        return {
            "id": user_id,
            "displayName": response.get("displayName"),
            "mail": response.get("mail"),
            "userPrincipalName": response.get("userPrincipalName"),
            "accountEnabled": response.get("accountEnabled"),
        }

    @staticmethod
    def _extract_email(
        *,
        response: Mapping[str, Any],
        expected_object_id: str,
    ) -> str | None:
        returned_id = str(response.get("id", "")).strip()
        if not returned_id or returned_id.lower() != expected_object_id.lower():
            raise PermissionError("Microsoft Graph user identity did not match authenticated object")

        account_enabled = response.get("accountEnabled")
        if account_enabled is False:
            raise PermissionError("authenticated Microsoft user account is disabled")

        for field in ("mail", "userPrincipalName"):
            value = response.get(field)
            if value is None:
                continue
            email = str(value).strip()
            if email:
                if "@" not in email or email.startswith("@") or email.endswith("@"):
                    raise ValueError("Microsoft Graph returned an invalid user email address")
                return email
        return None
