from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
    SecretResolver,
    require_capability,
)
from kernel.client_boundaries import BoundaryStatus, ClientBoundaryRepository

from .client import BackupNetClient, require_backup_net_credentials

BACKUP_NET_PROVIDER = "backup_net"
BACKUP_NET_PROFILE = "endpoint-backup-read"
BACKUP_NET_READONLY_SECRET = "backup_net.readonly"
BACKUP_NET_FULL_ACCESS_SECRET = "backup_net.fullaccess"
BACKUP_NET_APPROVED_SECRETS = frozenset(
    {BACKUP_NET_READONLY_SECRET, BACKUP_NET_FULL_ACCESS_SECRET}
)

_CAPABILITY_OPERATIONS = {
    "backup_net.endpoint_asset.search": "asset_search",
    "backup_net.endpoint_asset.read": "asset_read",
    "backup_net.backup.search": "backup_search",
    "backup_net.backupiq_alert.search": "backupiq_alert_search",
}

_ALLOWED_ARGUMENTS = {
    "asset_search": {
        "company_id", "id", "name", "order_by", "order_direction",
        "page_number", "page_size",
    },
    "asset_read": {"company_id", "resource_id", "id"},
    "backup_search": {
        "company_id", "asset_tag", "start_time_from", "start_time_to",
        "complete_time_from", "complete_time_to", "size_from", "size_to",
        "type", "status", "replication_status", "asset_key", "order_by",
        "order_direction", "page_number", "page_size",
    },
    "backupiq_alert_search": {
        "company_id", "type", "severity", "is_muted", "customer_name",
        "asset_tag", "appliance_name", "asset_name", "asset_key", "job_name",
        "job_type", "is_dismissed", "order_by", "order_direction",
        "created_time_direction", "page_number", "page_size",
    },
}

_PROVIDER_CUSTOMER_KEYS = ("customerId", "customer_id")


class BackupNetConnector:
    provider_name = BACKUP_NET_PROVIDER
    capabilities = frozenset(_CAPABILITY_OPERATIONS)

    def __init__(
        self,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
        boundaries: ClientBoundaryRepository,
        *,
        logical_secret: str = BACKUP_NET_READONLY_SECRET,
        client_factory=BackupNetClient,
    ) -> None:
        if logical_secret not in BACKUP_NET_APPROVED_SECRETS:
            raise ConnectorConfigurationError(
                "Backup.net logical secret profile is not approved."
            )
        self._secrets = secrets
        self._transport = transport
        self._audit = audit
        self._boundaries = boundaries
        self._logical_secret = logical_secret
        self._client_factory = client_factory

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        if request.context.organization_id != "aot":
            raise ConnectorAuthorizationError(
                "Backup.net reads are restricted to the AOT organization."
            )

        operation = _CAPABILITY_OPERATIONS[request.context.capability]
        arguments = dict(request.arguments)
        self._validate_arguments(operation, arguments)
        company_id, customer_id = self._resolve_customer_boundary(request, arguments)

        credentials = self._secrets.resolve(self._logical_secret, request.context)
        require_backup_net_credentials(credentials)
        client = self._client_factory(credentials)

        self._audit.record(
            "connector.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": operation,
                "company_id": company_id,
                "customer_boundary_validated": True,
            },
        )

        data = self._execute_operation(client, operation, arguments, customer_id)
        self._assert_response_customer_scope(data, customer_id)

        self._audit.record(
            "connector.completed",
            request.context,
            {
                "provider": self.provider_name,
                "company_id": company_id,
                "customer_boundary_validated": True,
            },
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )

    @staticmethod
    def _validate_arguments(operation: str, arguments: Mapping[str, Any]) -> None:
        if "customer_id" in arguments or "customerId" in arguments:
            raise ConnectorAuthorizationError(
                "Backup.net customer_id is server-derived and may not be supplied."
            )
        unexpected = sorted(set(arguments) - _ALLOWED_ARGUMENTS[operation])
        if unexpected:
            raise ConnectorConfigurationError(
                "Backup.net request contains unsupported argument(s): "
                + ", ".join(unexpected)
            )
        if operation == "backupiq_alert_search" and "type" in arguments:
            alert_type = str(arguments.get("type") or "").strip()
            if alert_type not in {"alert", "job", "conditional", "helix"}:
                raise ConnectorConfigurationError(
                    "BackupIQ alert type must be alert, job, conditional, or helix."
                )
        page_number = arguments.get("page_number", 1)
        page_size = arguments.get("page_size", 50)
        try:
            page_number = int(page_number)
            page_size = int(page_size)
        except (TypeError, ValueError) as exc:
            raise ConnectorConfigurationError(
                "Backup.net paging values must be integers."
            ) from exc
        if page_number < 1 or not 1 <= page_size <= 100:
            raise ConnectorConfigurationError(
                "Backup.net page_number must be positive and page_size must be 1-100."
            )

    def _resolve_customer_boundary(
        self,
        request: ConnectorRequest,
        arguments: Mapping[str, Any],
    ) -> tuple[str, str]:
        raw_company_id = arguments.get("company_id")
        if isinstance(raw_company_id, bool):
            raise ConnectorAuthorizationError(
                "An exact Autotask company_id is required for Backup.net access."
            )
        try:
            company_id = str(int(raw_company_id))
        except (TypeError, ValueError) as exc:
            raise ConnectorAuthorizationError(
                "An exact Autotask company_id is required for Backup.net access."
            ) from exc
        if int(company_id) < 0:
            raise ConnectorAuthorizationError(
                "An exact Autotask company_id is required for Backup.net access."
            )
        if (
            request.context.client_id is not None
            and str(request.context.client_id) != company_id
        ):
            raise ConnectorAuthorizationError(
                "Backup.net request client scope does not match the selected company."
            )

        boundary = self._boundaries.find_active_for_client(
            client_id=company_id,
            provider=BACKUP_NET_PROVIDER,
        )
        if boundary is None or boundary.status is not BoundaryStatus.VALIDATED:
            raise ConnectorAuthorizationError(
                "No validated Backup.net customer boundary exists for this company."
            )
        if boundary.profile != BACKUP_NET_PROFILE:
            raise ConnectorAuthorizationError(
                "Backup.net customer boundary uses an unapproved profile."
            )
        try:
            customer_id = str(UUID(boundary.external_tenant_id))
        except (ValueError, AttributeError) as exc:
            raise ConnectorAuthorizationError(
                "Backup.net customer boundary contains an invalid customer UUID."
            ) from exc
        return company_id, customer_id

    @staticmethod
    def _execute_operation(
        client: BackupNetClient,
        operation: str,
        arguments: Mapping[str, Any],
        customer_id: str,
    ) -> Mapping[str, Any]:
        params = {
            key: value
            for key, value in arguments.items()
            if key != "company_id"
        }
        params["customer_id"] = customer_id
        params.setdefault("page_number", 1)
        params.setdefault("page_size", 50)

        if operation == "asset_search":
            return client.get("/api/epb/v1/assets", params)
        if operation == "asset_read":
            asset_id = str(
                arguments.get("resource_id") or arguments.get("id") or ""
            ).strip()
            if not asset_id:
                raise ConnectorConfigurationError(
                    "Backup.net endpoint asset read requires resource_id or id."
                )
            return client.get(
                "/api/epb/v1/assets",
                {
                    "id": asset_id,
                    "customer_id": customer_id,
                    "page_number": 1,
                    "page_size": 2,
                },
            )
        if operation == "backup_search":
            return client.get("/v1/backups", params)
        if operation == "backupiq_alert_search":
            params.setdefault("type", "alert")
            return client.get("/v1/backupiq/alerts", params)
        raise ConnectorConfigurationError(
            "Unsupported Backup.net operation."
        )

    @staticmethod
    def _assert_response_customer_scope(
        data: Mapping[str, Any],
        expected_customer_id: str,
    ) -> None:
        items = data.get("items")
        if items is None:
            return
        if not isinstance(items, list):
            raise ConnectorAuthorizationError(
                "Backup.net collection response has an invalid shape."
            )
        expected = expected_customer_id.casefold()
        for item in items:
            if not isinstance(item, Mapping):
                raise ConnectorAuthorizationError(
                    "Backup.net returned a non-object collection item."
                )
            raw_customer_id = None
            for key in _PROVIDER_CUSTOMER_KEYS:
                if key in item:
                    raw_customer_id = item.get(key)
                    break
            if raw_customer_id is None:
                raise ConnectorAuthorizationError(
                    "Backup.net response did not prove the requested customer boundary."
                )
            try:
                observed = str(UUID(str(raw_customer_id))).casefold()
            except (ValueError, AttributeError) as exc:
                raise ConnectorAuthorizationError(
                    "Backup.net response contained an invalid customer identifier."
                ) from exc
            if observed != expected:
                raise ConnectorAuthorizationError(
                    "Backup.net response crossed the authorized customer boundary."
                )
