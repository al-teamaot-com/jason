from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
    require_capability,
)

from .user_directory import MicrosoftGraphUserDirectoryReader


class TrustedMicrosoftBindingReader(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...


@dataclass(frozen=True, slots=True)
class MicrosoftGraphDirectoryConnector:
    """Expose a narrow governed Microsoft Entra user read surface.

    The target tenant is derived only from the durable Microsoft -> Jason binding for
    the authenticated requester. Conversation input can select a user within that
    already-bound tenant, but can never choose a tenant, application, token, Graph path,
    permission profile, or HTTP method.
    """

    directory: MicrosoftGraphUserDirectoryReader
    bindings: TrustedMicrosoftBindingReader
    audit: AuditSink

    provider_name = "microsoft_graph"
    capabilities = frozenset(
        {
            "microsoft_graph.user.search",
            "microsoft_graph.user.get",
        }
    )

    def _binding(self, context: ConnectorContext):
        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=context.principal_id
        )
        if binding is None:
            raise ConnectorAuthorizationError(
                "A unique active Microsoft identity binding is required."
            )
        if str(getattr(binding, "status", "") or "").strip() != "active":
            raise ConnectorAuthorizationError(
                "The Microsoft identity binding is not active."
            )
        tenant_id = str(getattr(binding, "microsoft_tenant_id", "") or "").strip()
        if not tenant_id:
            raise ConnectorAuthorizationError(
                "The Microsoft identity binding does not identify a tenant."
            )
        return binding, tenant_id

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        _binding, tenant_id = self._binding(request.context)

        self.audit.record(
            "connector.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": request.context.capability,
            },
        )

        if request.context.capability == "microsoft_graph.user.get":
            resource_id = str(request.arguments.get("resource_id") or "").strip()
            if not resource_id:
                raise ValueError("resource_id is required for Microsoft user read")
            data: Mapping[str, object] = {
                "item": self.directory.read_user(
                    microsoft_tenant_id=tenant_id,
                    microsoft_object_id=resource_id,
                )
            }
        else:
            selectors = [
                key
                for key in ("email", "user_principal_name", "display_name")
                if request.arguments.get(key) is not None
                and str(request.arguments.get(key)).strip()
            ]
            if len(selectors) != 1:
                raise ValueError(
                    "Microsoft user search requires exactly one exact selector: "
                    "email, user_principal_name, or display_name"
                )
            selector = selectors[0]
            maximum = request.arguments.get("page_size", 10)
            if isinstance(maximum, bool):
                raise ValueError("page_size must be between 1 and 25")
            try:
                maximum = int(maximum)
            except (TypeError, ValueError) as error:
                raise ValueError("page_size must be between 1 and 25") from error
            if not 1 <= maximum <= 25:
                raise ValueError("page_size must be between 1 and 25")

            items = self.directory.search_users(
                microsoft_tenant_id=tenant_id,
                selector=selector,
                value=str(request.arguments[selector]),
                maximum_records=maximum,
            )
            data = {
                "items": list(items),
                "count": len(items),
            }

        self.audit.record(
            "connector.completed",
            request.context,
            {"provider": self.provider_name},
        )

        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )
