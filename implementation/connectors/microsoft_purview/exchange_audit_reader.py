from __future__ import annotations

from dataclasses import dataclass, field
from time import sleep
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote


class TenantApplicationTokenProvider(Protocol):
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str: ...


_DEFAULT_OPERATIONS = (
    "Move",
    "MoveToDeletedItems",
    "SoftDelete",
    "HardDelete",
    "Update",
    "UpdateInboxRules",
    "MailItemsAccessed",
)


@dataclass(frozen=True, slots=True)
class MicrosoftPurviewExchangeAuditReader:
    tokens: TenantApplicationTokenProvider
    transport: object
    base_url: str = "https://graph.microsoft.com/v1.0"
    timeout_seconds: float = 20.0
    maximum_poll_attempts: int = 10
    poll_interval_seconds: float = 2.0
    sleeper: Callable[[float], None] = field(default=sleep, repr=False, compare=False)

    def search_mailbox_events(
        self,
        *,
        microsoft_tenant_id: str,
        mailbox: str,
        start: str,
        end: str,
        correlation_id: str,
        subject: str | None = None,
        internet_message_id: str | None = None,
        operations: tuple[str, ...] = _DEFAULT_OPERATIONS,
        maximum_records: int = 500,
    ) -> Mapping[str, Any]:
        tenant = microsoft_tenant_id.strip()
        target_mailbox = mailbox.strip().casefold()
        if not tenant or not target_mailbox or "@" not in target_mailbox:
            raise ValueError("tenant and exact mailbox address are required")
        if not start.strip() or not end.strip():
            raise ValueError("start and end are required")
        if not correlation_id.strip():
            raise ValueError("correlation_id is required")
        maximum = int(maximum_records)
        if not 1 <= maximum <= 1000:
            raise ValueError("maximum_records must be between 1 and 1000")

        allowed = frozenset(_DEFAULT_OPERATIONS)
        normalized_operations = tuple(dict.fromkeys(str(x).strip() for x in operations))
        if not normalized_operations or any(x not in allowed for x in normalized_operations):
            raise ValueError("audit operations exceed the CAP-003 allowlist")

        token = self.tokens.access_token_for_tenant(microsoft_tenant_id=tenant)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        create = self.transport.request(
            method="POST",
            url=f"{self.base_url}/security/auditLog/queries",
            headers=headers,
            json={
                "displayName": f"Jason CAP-003 {correlation_id[:80]}",
                "filterStartDateTime": start.strip(),
                "filterEndDateTime": end.strip(),
                "serviceFilter": "Exchange",
                "operationFilters": list(normalized_operations),
            },
            timeout_seconds=self.timeout_seconds,
        )
        if not isinstance(create, Mapping):
            raise RuntimeError("Purview audit query returned an invalid create response")
        query_id = str(create.get("id") or "").strip()
        if not query_id:
            raise RuntimeError("Purview audit query did not return an id")

        status = str(create.get("status") or "").strip()
        for attempt in range(self.maximum_poll_attempts):
            if status in {"succeeded", "failed", "cancelled"}:
                break
            if attempt:
                self.sleeper(self.poll_interval_seconds)
            current = self.transport.request(
                method="GET",
                url=f"{self.base_url}/security/auditLog/queries/{quote(query_id, safe='')}",
                headers={"Authorization": f"Bearer {token}"},
                timeout_seconds=self.timeout_seconds,
            )
            if not isinstance(current, Mapping):
                raise RuntimeError("Purview audit query returned invalid status")
            status = str(current.get("status") or "").strip()

        if status != "succeeded":
            return {
                "mailbox": target_mailbox,
                "query_id": query_id,
                "query_status": status or "unknown",
                "items": [],
                "count": 0,
                "complete": False,
            }

        raw_records: list[Mapping[str, Any]] = []
        next_url: str | None = (
            f"{self.base_url}/security/auditLog/queries/"
            f"{quote(query_id, safe='')}/records"
        )
        while next_url and len(raw_records) < maximum:
            page = self.transport.request(
                method="GET",
                url=next_url,
                headers={"Authorization": f"Bearer {token}"},
                params={"$top": min(100, maximum - len(raw_records))}
                if next_url.startswith(self.base_url)
                else None,
                timeout_seconds=self.timeout_seconds,
            )
            if not isinstance(page, Mapping):
                raise RuntimeError("Purview audit records returned an invalid response")
            values = page.get("value")
            if not isinstance(values, list):
                raise RuntimeError("Purview audit records returned an invalid collection")
            for record in values:
                if isinstance(record, Mapping):
                    raw_records.append(record)
                    if len(raw_records) >= maximum:
                        break
            candidate = page.get("@odata.nextLink")
            next_url = str(candidate).strip() if candidate else None

        items = []
        for record in raw_records:
            projected = self._project_record(record)
            owner = str(projected.get("mailbox_owner") or "").casefold()
            if owner != target_mailbox:
                continue
            if subject:
                affected_subjects = " ".join(
                    str(item.get("subject") or "")
                    for item in projected.get("affected_items", [])
                ).casefold()
                if subject.strip().casefold() not in affected_subjects:
                    continue
            if internet_message_id:
                wanted = internet_message_id.strip().casefold()
                affected_ids = {
                    str(item.get("internet_message_id") or "").strip().casefold()
                    for item in projected.get("affected_items", [])
                }
                if wanted not in affected_ids:
                    continue
            items.append(projected)

        return {
            "mailbox": target_mailbox,
            "query_id": query_id,
            "query_status": status,
            "items": items,
            "count": len(items),
            "complete": True,
        }

    @staticmethod
    def _project_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
        audit = record.get("auditData")
        audit_data = audit if isinstance(audit, Mapping) else {}

        affected = audit_data.get("AffectedItems")
        affected_items = []
        if isinstance(affected, list):
            for item in affected:
                if not isinstance(item, Mapping):
                    continue
                parent = item.get("ParentFolder")
                parent_data = parent if isinstance(parent, Mapping) else {}
                affected_items.append(
                    {
                        "id": item.get("Id"),
                        "internet_message_id": item.get("InternetMessageId"),
                        "subject": item.get("Subject"),
                        "parent_folder": parent_data.get("Path"),
                    }
                )

        folder = audit_data.get("Folder")
        folder_data = folder if isinstance(folder, Mapping) else {}

        return {
            "id": record.get("id"),
            "created_at": record.get("createdDateTime"),
            "operation": record.get("operation"),
            "actor": record.get("userPrincipalName") or record.get("userId"),
            "client_ip": record.get("clientIp") or audit_data.get("ClientIPAddress"),
            "service": record.get("service"),
            "mailbox_owner": audit_data.get("MailboxOwnerUPN"),
            "client": audit_data.get("ClientInfoString"),
            "app_id": audit_data.get("AppId"),
            "client_app_id": audit_data.get("ClientAppId"),
            "device_id": audit_data.get("DeviceId"),
            "logon_type": audit_data.get("LogonType"),
            "internal_logon_type": audit_data.get("InternalLogonType"),
            "external_access": audit_data.get("ExternalAccess"),
            "folder": folder_data.get("Path"),
            "affected_items": affected_items,
        }
