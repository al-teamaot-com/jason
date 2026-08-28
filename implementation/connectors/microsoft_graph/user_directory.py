"""Read authenticated Microsoft user profile attributes through Microsoft Graph.

This component is intentionally narrow. It accepts only a tenant/object identity that
has already crossed the Teams authentication boundary, acquires an application token
through an injected provider, and reads the exact Graph user resource needed for
identity enrichment. It does not accept arbitrary Graph paths, filters, providers, or
execution instructions from conversation input.
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
        tenant_id = microsoft_tenant_id.strip()
        object_id = microsoft_object_id.strip()
        if not tenant_id or not object_id:
            raise ValueError("Microsoft tenant and object identifiers are required")

        token = self.tokens.access_token_for_tenant(
            microsoft_tenant_id=tenant_id,
        )
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("Microsoft Graph application token is unavailable")

        response = self._request_user(
            token=token.strip(),
            object_id=object_id,
        )
        return self._extract_email(response=response, expected_object_id=object_id)

    def _request_user(self, *, token: str, object_id: str) -> Mapping[str, Any]:
        """Perform a bounded retry only for explicit HTTP throttling.

        Identity enrichment remains fail-closed: no cached profile or alternate identity
        source is substituted when Graph is unavailable. Retry metadata is provider
        transport metadata, not conversation input, and the total retry count/delay is
        locally bounded.
        """

        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.transport.request(
                    method="GET",
                    url=f"{self.base_url.rstrip('/')}/users/{quote(object_id, safe='')}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"$select": "id,mail,userPrincipalName,accountEnabled"},
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
