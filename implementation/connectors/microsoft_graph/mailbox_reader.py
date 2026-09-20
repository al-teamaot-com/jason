from __future__ import annotations

from dataclasses import dataclass, field
from time import sleep
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote

from connectors.core.contracts import ConnectorTransportError, HttpTransport


class TenantApplicationTokenProvider(Protocol):
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str: ...


def _odata_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True, slots=True)
class MicrosoftGraphMailboxReader:
    """Bounded read-only mailbox evidence reader for explicitly approved mailboxes."""

    tokens: TenantApplicationTokenProvider
    transport: HttpTransport
    base_url: str = "https://graph.microsoft.com/v1.0"
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    max_retry_delay_seconds: float = 5.0
    sleeper: Callable[[float], None] = field(default=sleep, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != "https://graph.microsoft.com/v1.0":
            raise ValueError("Microsoft mailbox reader must use Graph v1.0 public cloud")

    def search_messages(
        self,
        *,
        microsoft_tenant_id: str,
        mailbox: str,
        maximum_records: int = 25,
        sender: str | None = None,
        received_after: str | None = None,
        received_before: str | None = None,
    ) -> Mapping[str, Any]:
        tenant = microsoft_tenant_id.strip()
        mailbox_address = mailbox.strip()
        if not tenant or not mailbox_address or "@" not in mailbox_address:
            raise ValueError("tenant and exact mailbox address are required")
        if isinstance(maximum_records, bool):
            raise ValueError("page_size must be between 1 and 50")
        maximum = int(maximum_records)
        if not 1 <= maximum <= 50:
            raise ValueError("page_size must be between 1 and 50")

        filters: list[str] = []
        if sender:
            sender_value = sender.strip()
            if not sender_value or "@" not in sender_value:
                raise ValueError("sender must be a valid exact email address")
            filters.append(
                "from/emailAddress/address eq " + _odata_string(sender_value)
            )
        if received_after:
            filters.append(f"receivedDateTime ge {received_after.strip()}")
        if received_before:
            filters.append(f"receivedDateTime le {received_before.strip()}")

        params: dict[str, Any] = {
            "$top": maximum,
            "$select": (
                "id,subject,from,toRecipients,receivedDateTime,sentDateTime,"
                "hasAttachments,internetMessageId,conversationId"
            ),
            "$orderby": "receivedDateTime desc",
        }
        if filters:
            params["$filter"] = " and ".join(filters)

        response = self._get(
            tenant_id=tenant,
            path=f"/users/{quote(mailbox_address, safe='')}/messages",
            params=params,
        )
        values = response.get("value")
        if not isinstance(values, list):
            raise ConnectorTransportError(
                "Microsoft mailbox search returned an unexpected shape"
            )
        if len(values) > maximum:
            raise ConnectorTransportError(
                "Microsoft mailbox search exceeded the requested bound"
            )

        items: list[Mapping[str, Any]] = []
        for item in values:
            if not isinstance(item, Mapping):
                raise ConnectorTransportError(
                    "Microsoft mailbox search returned an invalid record"
                )
            items.append(self._project_message(item, include_body=False))
        return {
            "mailbox": mailbox_address.casefold(),
            "items": items,
            "count": len(items),
        }

    def read_message(
        self,
        *,
        microsoft_tenant_id: str,
        mailbox: str,
        message_id: str,
    ) -> Mapping[str, Any]:
        tenant = microsoft_tenant_id.strip()
        mailbox_address = mailbox.strip()
        durable_id = message_id.strip()
        if not tenant or not mailbox_address or "@" not in mailbox_address:
            raise ValueError("tenant and exact mailbox address are required")
        if not durable_id:
            raise ValueError("message_id is required")

        response = self._get(
            tenant_id=tenant,
            path=(
                f"/users/{quote(mailbox_address, safe='')}/messages/"
                f"{quote(durable_id, safe='')}"
            ),
            params={
                "$select": (
                    "id,subject,from,toRecipients,ccRecipients,receivedDateTime,"
                    "sentDateTime,hasAttachments,internetMessageId,conversationId,"
                    "body,bodyPreview"
                )
            },
        )
        return {
            "mailbox": mailbox_address.casefold(),
            "item": self._project_message(response, include_body=True),
        }

    def attachment_metadata(
        self,
        *,
        microsoft_tenant_id: str,
        mailbox: str,
        message_id: str,
        maximum_records: int = 25,
    ) -> Mapping[str, Any]:
        maximum = int(maximum_records)
        if not 1 <= maximum <= 25:
            raise ValueError("attachment page_size must be between 1 and 25")
        response = self._get(
            tenant_id=microsoft_tenant_id.strip(),
            path=(
                f"/users/{quote(mailbox.strip(), safe='')}/messages/"
                f"{quote(message_id.strip(), safe='')}/attachments"
            ),
            params={
                "$top": maximum,
                "$select": "id,name,contentType,size,isInline,lastModifiedDateTime",
            },
        )
        values = response.get("value")
        if not isinstance(values, list):
            raise ConnectorTransportError(
                "Microsoft attachment metadata returned an unexpected shape"
            )
        items = []
        for item in values[:maximum]:
            if not isinstance(item, Mapping):
                raise ConnectorTransportError(
                    "Microsoft attachment metadata returned an invalid record"
                )
            items.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "content_type": item.get("contentType"),
                    "size": item.get("size"),
                    "is_inline": item.get("isInline"),
                    "modified_at": item.get("lastModifiedDateTime"),
                }
            )
        return {
            "mailbox": mailbox.strip().casefold(),
            "message_id": message_id.strip(),
            "items": items,
            "count": len(items),
            "content_exposed": False,
        }

    def _get(
        self,
        *,
        tenant_id: str,
        path: str,
        params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not tenant_id:
            raise ValueError("Microsoft tenant identifier is required")
        token = self.tokens.access_token_for_tenant(
            microsoft_tenant_id=tenant_id
        )
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("Microsoft Graph application token is unavailable")

        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.transport.request(
                    method="GET",
                    url=f"{self.base_url.rstrip('/')}{path}",
                    headers={"Authorization": f"Bearer {token.strip()}"},
                    params=params,
                    timeout_seconds=self.timeout_seconds,
                )
            except ConnectorTransportError as error:
                if error.status_code != 429 or attempt >= self.max_attempts:
                    raise
                delay = (
                    error.retry_after_seconds
                    if error.retry_after_seconds is not None
                    else float(2 ** (attempt - 1))
                )
                delay = min(max(delay, 0.0), self.max_retry_delay_seconds)
                if delay:
                    self.sleeper(delay)
        raise RuntimeError("unreachable Microsoft mailbox retry state")

    @staticmethod
    def _project_message(
        item: Mapping[str, Any],
        *,
        include_body: bool,
    ) -> Mapping[str, Any]:
        message_id = str(item.get("id") or "").strip()
        if not message_id:
            raise ConnectorTransportError("Microsoft message did not include an id")

        sender = item.get("from")
        sender_address = None
        if isinstance(sender, Mapping):
            email = sender.get("emailAddress")
            if isinstance(email, Mapping):
                sender_address = email.get("address")

        projected: dict[str, Any] = {
            "id": message_id,
            "subject": item.get("subject"),
            "sender": sender_address,
            "received_at": item.get("receivedDateTime"),
            "sent_at": item.get("sentDateTime"),
            "has_attachments": bool(item.get("hasAttachments")),
            "internet_message_id": item.get("internetMessageId"),
            "conversation_id": item.get("conversationId"),
        }
        if include_body:
            body = item.get("body")
            if isinstance(body, Mapping):
                projected["body_type"] = body.get("contentType")
                projected["body"] = body.get("content")
            projected["body_preview"] = item.get("bodyPreview")
        return projected
