from __future__ import annotations

from datetime import datetime

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)


SERVICE_TICKET_CREATE = "service.ticket.create"
SERVICE_TICKET_UPDATE = "service.ticket.update"
SERVICE_TICKET_NOTE_CREATE = "service.ticket.note.create"
SERVICE_TICKET_NOTE_UPDATE = "service.ticket.note.update"
SERVICE_PRODUCT_CREATE = "service.product.create"
SERVICE_PRODUCT_UPDATE = "service.product.update"
SERVICE_PRODUCT_VENDOR_CREATE = "service.product.vendor.create"
SERVICE_PRODUCT_VENDOR_UPDATE = "service.product.vendor.update"
SERVICE_SERVICE_CREATE = "service.service.create"
SERVICE_SERVICE_UPDATE = "service.service.update"
SERVICE_SERVICE_BUNDLE_CREATE = "service.service.bundle.create"
SERVICE_SERVICE_BUNDLE_UPDATE = "service.service.bundle.update"
SERVICE_PURCHASE_ORDER_CREATE = "service.purchase.order.create"
SERVICE_PURCHASE_ORDER_UPDATE = "service.purchase.order.update"
SERVICE_PURCHASE_ORDER_ITEM_CREATE = "service.purchase.order.item.create"
SERVICE_PURCHASE_ORDER_ITEM_UPDATE = "service.purchase.order.item.update"
SERVICE_PURCHASE_ORDER_RECEIVE = "service.purchase.order.receive"

AUTOTASK_MUTATION_CAPABILITIES = frozenset(
    {
        SERVICE_TICKET_CREATE,
        SERVICE_TICKET_UPDATE,
        SERVICE_TICKET_NOTE_CREATE,
        SERVICE_TICKET_NOTE_UPDATE,
        SERVICE_PRODUCT_CREATE,
        SERVICE_PRODUCT_UPDATE,
        SERVICE_PRODUCT_VENDOR_CREATE,
        SERVICE_PRODUCT_VENDOR_UPDATE,
        SERVICE_SERVICE_CREATE,
        SERVICE_SERVICE_UPDATE,
        SERVICE_SERVICE_BUNDLE_CREATE,
        SERVICE_SERVICE_BUNDLE_UPDATE,
        SERVICE_PURCHASE_ORDER_CREATE,
        SERVICE_PURCHASE_ORDER_UPDATE,
        SERVICE_PURCHASE_ORDER_ITEM_CREATE,
        SERVICE_PURCHASE_ORDER_ITEM_UPDATE,
        SERVICE_PURCHASE_ORDER_RECEIVE,
    }
)


def _mutation_capability(
    *,
    now: datetime,
    capability_name: str,
    display_name: str,
    business_purpose: str,
    resource_types: str,
    operation: str,
    idempotency_behavior: IdempotencyBehavior,
) -> CapabilityDefinition:
    """Build one source-only governed mutation capability.

    These definitions deliberately remain BUILDING and are not registered by
    production composition. Source presence therefore cannot advertise or
    authorize a write through MCP. Promotion requires provider-backed acceptance,
    a Central Orchestrator write path, explicit authority grants, and a separate
    production activation change.
    """

    return CapabilityDefinition(
        capability_name=capability_name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=business_purpose,
        owner_service="Jason Governed Actions",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006", "JAC-013"}),
        risk_level=CapabilityRisk.HIGH,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=(
            f"schema://jason/{capability_name.replace('.', '-')}/1.0"
        ),
        output_schema_reference=(
            f"schema://jason/{capability_name.replace('.', '-')}-result/1.0"
        ),
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(
            required=True,
            approver_classes=("owner",),
        ),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authenticated requester identity",
                "provider requester authorization evidence",
                "resolved target resource",
                "provider mutation result",
                "post-mutation verification result",
            ),
            verification_requirements=(
                "requester maps to exactly one active provider identity",
                "provider-native requester impersonation is applied",
                "requester provider permissions permit the concrete operation",
                "target remains in authorized tenant and client scope",
                "post-mutation read verifies the intended durable state",
            ),
        ),
        dependencies=frozenset(
            {
                "identity.authorization.resolve",
                "governance.action.evaluate",
            }
        ),
        idempotency_behavior=idempotency_behavior,
        idempotency_key_required=True,
        timeout_seconds=60,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without service-account fallback, implicit retry, "
            "first-match target selection, or unverified success."
        ),
        tenant_isolation_required=True,
        client_isolation_required=True,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Allow narrowly governed service-management mutations while "
                "preserving human authority, provider permissions, and auditability."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "Provider-native requester authorization can no longer be proven.",
                "A safer approved mutation capability replaces this pilot.",
            ),
            last_reviewed_at=now,
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
            authoritative_change_sources=("Autotask REST API documentation",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "false",
            "write_capability": "true",
            "resource_types": resource_types,
            "operation": operation,
            "provider_native_impersonation_required": "true",
            "requester_provider_profile_is_maximum_authority": "true",
            "activation_state": "source_only_not_registered",
            "pilot_provider": "autotask",
            "pilot_scope": "explicitly_registered_autotask_mutations",
        },
    )


def autotask_mutation_capability_definitions(
    *,
    now: datetime,
) -> tuple[CapabilityDefinition, ...]:
    """Return dormant Ticket/TicketNote mutation definitions for source tests."""

    return (
        _mutation_capability(
            now=now,
            capability_name=SERVICE_TICKET_CREATE,
            display_name="Create Service Ticket",
            business_purpose="Create one authorized service-management ticket.",
            resource_types="service_ticket,ticket",
            operation="create",
            idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_TICKET_UPDATE,
            display_name="Update Service Ticket",
            business_purpose="Apply a bounded partial update to one authorized service ticket.",
            resource_types="service_ticket,ticket",
            operation="update",
            idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_TICKET_NOTE_CREATE,
            display_name="Create Service Ticket Note",
            business_purpose="Create one authorized note on a resolved service ticket.",
            resource_types="service_ticket_note,ticket_note",
            operation="create",
            idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_TICKET_NOTE_UPDATE,
            display_name="Update Service Ticket Note",
            business_purpose="Apply a bounded partial update to one authorized ticket note.",
            resource_types="service_ticket_note,ticket_note",
            operation="update",
            idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_PRODUCT_CREATE,
            display_name="Create Service Product",
            business_purpose="Create one approved Autotask product catalog record.",
            resource_types="service_product,product,catalog_item",
            operation="create",
            idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_PRODUCT_UPDATE,
            display_name="Update Service Product",
            business_purpose="Apply a bounded approved update to one Autotask product catalog record.",
            resource_types="service_product,product,catalog_item",
            operation="update",
            idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_PRODUCT_VENDOR_CREATE,
            display_name="Create Product Vendor Association",
            business_purpose="Associate one approved Autotask product with one verified vendor.",
            resource_types="service_product_vendor,product_vendor,vendor",
            operation="create",
            idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_PRODUCT_VENDOR_UPDATE,
            display_name="Update Product Vendor Association",
            business_purpose="Apply a bounded approved update to one product-vendor association.",
            resource_types="service_product_vendor,product_vendor,vendor",
            operation="update",
            idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_SERVICE_CREATE,
            display_name="Create Catalog Service",
            business_purpose="Create one approved Autotask recurring service catalog record.",
            resource_types="service_catalog_service,service,catalog_item",
            operation="create",
            idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_SERVICE_UPDATE,
            display_name="Update Catalog Service",
            business_purpose="Apply a bounded approved update to one Autotask recurring service catalog record.",
            resource_types="service_catalog_service,service,catalog_item",
            operation="update",
            idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_SERVICE_BUNDLE_CREATE,
            display_name="Create Service Bundle",
            business_purpose="Create one approved Autotask service bundle catalog record.",
            resource_types="service_bundle,catalog_item",
            operation="create",
            idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_SERVICE_BUNDLE_UPDATE,
            display_name="Update Service Bundle",
            business_purpose="Apply a bounded approved update to one Autotask service bundle catalog record.",
            resource_types="service_bundle,catalog_item",
            operation="update",
            idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_PURCHASE_ORDER_CREATE,
            display_name="Create Purchase Order",
            business_purpose="Create one approved Autotask purchase order for one verified vendor.",
            resource_types="service_purchase_order,purchase_order,procurement",
            operation="create",
            idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_PURCHASE_ORDER_UPDATE,
            display_name="Update Purchase Order",
            business_purpose="Apply a bounded approved update to one Autotask purchase order.",
            resource_types="service_purchase_order,purchase_order,procurement",
            operation="update",
            idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_PURCHASE_ORDER_ITEM_CREATE,
            display_name="Create Purchase Order Item",
            business_purpose="Create one approved product line on one verified Autotask purchase order.",
            resource_types="service_purchase_order_item,purchase_order_item,procurement",
            operation="create",
            idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_PURCHASE_ORDER_ITEM_UPDATE,
            display_name="Update Purchase Order Item",
            business_purpose="Apply a bounded approved update to one Autotask purchase-order line.",
            resource_types="service_purchase_order_item,purchase_order_item,procurement",
            operation="update",
            idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        ),
        _mutation_capability(
            now=now,
            capability_name=SERVICE_PURCHASE_ORDER_RECEIVE,
            display_name="Receive Purchase Order Item",
            business_purpose="Receive an approved quantity for one verified Autotask purchase-order item.",
            resource_types="service_purchase_order_receipt,purchase_order_item,procurement",
            operation="receive",
            idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        ),
    )
