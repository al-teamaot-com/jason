from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from connectors.autotask.connector import AutotaskConnector
from connectors.autotask.impersonating_connector import TrustedPrincipalBindingResolver
from connectors.autotask.mutation_connector import AUTOTASK_MUTATION_ENABLED_ENV
from connectors.autotask.procurement_mutation_connector import (
    AutotaskProcurementMutationConnector,
)
from connectors.core.contracts import (
    AuditSink, ConnectorRequest, ConnectorResult, HttpTransport,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService
from kernel.execution_providers import (
    ExecutionProvider, ExecutionProviderRegistryService, ProviderApproval,
    ProviderFeatures, ProviderHealth, ProviderLifecycle, ProviderLimits,
    ProviderStewardship, ProviderType,
)
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_mutation_capability_catalog import (
    AUTOTASK_MUTATION_CAPABILITIES,
    SERVICE_PRODUCT_CREATE, SERVICE_PRODUCT_UPDATE,
    SERVICE_PRODUCT_VENDOR_CREATE, SERVICE_PRODUCT_VENDOR_UPDATE,
    SERVICE_SERVICE_CREATE, SERVICE_SERVICE_UPDATE,
    SERVICE_SERVICE_BUNDLE_CREATE, SERVICE_SERVICE_BUNDLE_UPDATE,
    SERVICE_PURCHASE_ORDER_CREATE, SERVICE_PURCHASE_ORDER_UPDATE,
    SERVICE_PURCHASE_ORDER_ITEM_CREATE, SERVICE_PURCHASE_ORDER_ITEM_UPDATE,
    SERVICE_PURCHASE_ORDER_RECEIVE,
    autotask_mutation_capability_definitions,
)
from orchestrator.service import CapabilityInvoker

AUTOTASK_PROCUREMENT_PROVIDER = "autotask_procurement"
AUTOTASK_PROCUREMENT_PROFILE_ENV = "JASON_AUTOTASK_PROCUREMENT_MCP_PROFILE"
AUTOTASK_PROCUREMENT_PROFILE = "owner-procurement-v1"

PROCUREMENT_CAPABILITIES = frozenset({
    SERVICE_PRODUCT_CREATE, SERVICE_PRODUCT_UPDATE,
    SERVICE_PRODUCT_VENDOR_CREATE, SERVICE_PRODUCT_VENDOR_UPDATE,
    SERVICE_SERVICE_CREATE, SERVICE_SERVICE_UPDATE,
    SERVICE_SERVICE_BUNDLE_CREATE, SERVICE_SERVICE_BUNDLE_UPDATE,
    SERVICE_PURCHASE_ORDER_CREATE, SERVICE_PURCHASE_ORDER_UPDATE,
    SERVICE_PURCHASE_ORDER_ITEM_CREATE, SERVICE_PURCHASE_ORDER_ITEM_UPDATE,
    SERVICE_PURCHASE_ORDER_RECEIVE,
})

PROVIDER_MAP = {
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_PRODUCT_CREATE): "autotask.product.create",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_PRODUCT_UPDATE): "autotask.product.update",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_PRODUCT_VENDOR_CREATE): "autotask.product.vendor.create",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_PRODUCT_VENDOR_UPDATE): "autotask.product.vendor.update",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_SERVICE_CREATE): "autotask.service.create",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_SERVICE_UPDATE): "autotask.service.update",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_SERVICE_BUNDLE_CREATE): "autotask.service.bundle.create",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_SERVICE_BUNDLE_UPDATE): "autotask.service.bundle.update",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_PURCHASE_ORDER_CREATE): "autotask.purchase.order.create",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_PURCHASE_ORDER_UPDATE): "autotask.purchase.order.update",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_PURCHASE_ORDER_ITEM_CREATE): "autotask.purchase.order.item.create",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_PURCHASE_ORDER_ITEM_UPDATE): "autotask.purchase.order.item.update",
    (AUTOTASK_PROCUREMENT_PROVIDER, SERVICE_PURCHASE_ORDER_RECEIVE): "autotask.purchase.order.item.receiving.create",
}
PROVIDER_ENTITY = {
    "autotask.product.create": "Products",
    "autotask.product.update": "Products",
    "autotask.product.vendor.create": "ProductVendors",
    "autotask.product.vendor.update": "ProductVendors",
    "autotask.service.create": "Services",
    "autotask.service.update": "Services",
    "autotask.service.bundle.create": "ServiceBundles",
    "autotask.service.bundle.update": "ServiceBundles",
    "autotask.purchase.order.create": "PurchaseOrders",
    "autotask.purchase.order.update": "PurchaseOrders",
    "autotask.purchase.order.item.create": "PurchaseOrderItems",
    "autotask.purchase.order.item.update": "PurchaseOrderItems",
    "autotask.purchase.order.item.receiving.create": "PurchaseOrderItemReceiving",
}

class ProcurementActivationError(RuntimeError):
    pass

@dataclass(frozen=True, slots=True)
class ProcurementActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]

def _enabled() -> bool:
    return (
        os.getenv(AUTOTASK_PROCUREMENT_PROFILE_ENV, "").strip().casefold()
        == AUTOTASK_PROCUREMENT_PROFILE
        and os.getenv(AUTOTASK_MUTATION_ENABLED_ENV, "").strip().casefold() == "true"
    )

def _definitions(now: datetime):
    wanted = {
        d.capability_name: d
        for d in autotask_mutation_capability_definitions(now=now)
        if d.capability_name in PROCUREMENT_CAPABILITIES
    }
    if set(wanted) != set(PROCUREMENT_CAPABILITIES):
        raise ProcurementActivationError("procurement capability catalog incomplete")
    result = []
    for name in sorted(wanted):
        base = wanted[name]
        metadata = dict(base.metadata)
        metadata.update({
            "activation_state": "procurement_mcp_source_only_not_activated",
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": "true",
            "pilot_scope": "aot_owner_procurement",
            "provider_credential": "autotask.write",
        })
        result.append(replace(base, client_isolation_required=False, metadata=metadata))
    return tuple(result)

def _provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=AUTOTASK_PROCUREMENT_PROVIDER,
        display_name="Autotask Governed Procurement",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=PROCUREMENT_CAPABILITIES,
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=10,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="Govern approved AOT catalog and procurement mutations.",
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=("Provider authorization cannot be proven.",),
            vendor_change_sources=("Autotask REST API documentation",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "autotask",
            "write_capability": "true",
            "provider_native_impersonation_required": "true",
            "activation_state": "procurement_mcp_source_only_not_activated",
        },
    )
class AutotaskProductionProcurementConnector(AutotaskProcurementMutationConnector):
    logical_secret = "autotask.write"

    @staticmethod
    def _id(data: Mapping[str, Any]) -> int:
        for key in ("itemId", "itemID", "id"):
            raw = data.get(key)
            if raw is not None and not isinstance(raw, bool) and str(raw).isdigit() and int(raw) > 0:
                return int(raw)
        item = data.get("item")
        if isinstance(item, Mapping):
            raw = item.get("id")
            if raw is not None and not isinstance(raw, bool) and str(raw).isdigit() and int(raw) > 0:
                return int(raw)
        raise ValueError("AUTOTASK_PROCUREMENT_DURABLE_ID_MISSING")

    def _readback(self, request: ConnectorRequest, entity: str, resource_id: int) -> Mapping[str, Any]:
        reader = AutotaskConnector(
            secrets=self._secrets,
            transport=self._transport,
            audit=self._audit,
        )
        read_request = ConnectorRequest(
            context=replace(
                request.context,
                capability="autotask.entity.get",
                mode="observe",
            ),
            arguments={"entity": entity, "entity_id": resource_id},
        )
        observed = reader.execute(read_request).data
        if not isinstance(observed, Mapping):
            raise ValueError("AUTOTASK_PROCUREMENT_READBACK_INVALID")
        item = observed.get("item")
        return item if isinstance(item, Mapping) else observed

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        result = super().execute(request)
        operation = request.context.capability
        entity = PROVIDER_ENTITY[operation]
        payload = dict(request.arguments.get("payload") or {})
        resource_id = self._id(result.data) if operation.endswith(".create") else int(payload["id"])
        observed = self._readback(request, entity, resource_id)
        if int(observed.get("id", 0)) != resource_id:
            raise ValueError("AUTOTASK_PROCUREMENT_READBACK_ID_MISMATCH")
        data = dict(result.data)
        data["jasonVerification"] = {
            "readbackVerified": True,
            "resourceId": resource_id,
            "entity": entity,
        }
        return ConnectorResult(
            capability=result.capability,
            provider=result.provider,
            data=data,
            evidence_ids=(*result.evidence_ids, f"autotask:{entity}:{resource_id}"),
            warnings=result.warnings,
        )

def register_autotask_procurement_runtime_foundation(
    *, capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService, now: datetime,
) -> ProcurementActivationState:
    for definition in _definitions(now):
        capabilities.register(definition)
    providers.register(_provider(now))
    profile = os.getenv(AUTOTASK_PROCUREMENT_PROFILE_ENV, "").strip().casefold()
    if not profile:
        return ProcurementActivationState("", False, (), ())
    if profile != AUTOTASK_PROCUREMENT_PROFILE or not _enabled():
        raise ProcurementActivationError("unsupported or disabled procurement MCP profile")
    for name in sorted(PROCUREMENT_CAPABILITIES):
        capabilities.set_lifecycle(
            capability_name=name, version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
    providers.set_approval(
        provider_id=AUTOTASK_PROCUREMENT_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=AUTOTASK_PROCUREMENT_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=AUTOTASK_PROCUREMENT_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return ProcurementActivationState(
        profile, True, (AUTOTASK_PROCUREMENT_PROVIDER,),
        tuple(sorted(PROCUREMENT_CAPABILITIES)),
    )

def build_autotask_procurement_invoker(
    *, openbao_url: str, role_id_path: Path, secret_id_path: Path,
    transport: HttpTransport, audit: AuditSink,
    bindings: TrustedPrincipalBindingResolver,
) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )
    connector = AutotaskProductionProcurementConnector(
        secrets=secrets, transport=transport, audit=audit, bindings=bindings,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={AUTOTASK_PROCUREMENT_PROVIDER: connector},
        provider_capability_map=PROVIDER_MAP,
    )

def register_autotask_procurement_invoker(
    *, invokers: CapabilityInvokerRegistry, invoker: CapabilityInvoker,
) -> None:
    for name in sorted(PROCUREMENT_CAPABILITIES):
        invokers.register(name, invoker)
