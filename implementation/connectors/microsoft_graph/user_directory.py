"""Read authenticated Microsoft user profile attributes through Microsoft Graph.

This component is intentionally narrow. It accepts only a tenant/object identity that
has already crossed the Teams authentication boundary, acquires an application token
through an injected provider, and reads the exact Graph user resource needed for
identity enrichment. It does not accept arbitrary Graph paths, filters, providers, or
execution instructions from conversation input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import quote

from connectors.core.contracts import HttpTransport


class TenantApplicationTokenProvider(Protocol):
    def access_token_for_tenant(
        self,
        *,
        microsoft_tenant_id: str,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class MicrosoftGraphUserDirectoryReader:
    tokens: TenantApplicationTokenProvider
    transport: HttpTransport
    base_url: str = "https://graph.microsoft.com/v1.0"
    timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != "https://graph.microsoft.com/v1.0":
            raise ValueError("Microsoft user directory must use Graph v1.0 public cloud")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def resolve_email(
        self,
        *,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
    ) -> str | None:
        tenant_id = microsoft_tenant_id.strip()
        object_id = microsoft_object_id.strip()
        if not tenant_id or not object_id:
            raise ValueError("Microsoft tenant and object identifiers are required")

        token = self.tokens.access_token_for_tenant(
            microsoft_tenant_id=tenant_id,
        )
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("Microsoft Graph application token is unavailable")

        response = self.transport.request(
            method="GET",
            url=f"{self.base_url.rstrip('/')}/users/{quote(object_id, safe='')}",
            headers={"Authorization": f"Bearer {token.strip()}"},
            params={"$select": "id,mail,userPrincipalName,accountEnabled"},
            timeout_seconds=self.timeout_seconds,
        )
        return self._extract_email(response=response, expected_object_id=object_id)

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
