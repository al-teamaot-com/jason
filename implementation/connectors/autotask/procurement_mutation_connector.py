from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorRequest,
    ConnectorResult,
)

from .mutation_connector import AutotaskMutationConnector


AUTOTASK_PROCUREMENT_MUTATION_OPERATIONS = frozenset(
    {
        "autotask.product.create",
        "autotask.product.update",
        "autotask.product.vendor.create",
        "autotask.product.vendor.update",
        "autotask.service.create",
        "autotask.service.update",
        "autotask.service.bundle.create",
        "autotask.service.bundle.update",
        "autotask.purchase.order.create",
        "autotask.purchase.order.update",
        "autotask.purchase.order.item.create",
        "autotask.purchase.order.item.update",
    }
)
PROCUREMENT_OPERATION_PREFLIGHT = {
    "autotask.product.create": ("Products", "userAccessForCreate"),
    "autotask.product.update": ("Products", "userAccessForUpdate"),
    "autotask.product.vendor.create": ("ProductVendors", "userAccessForCreate"),
    "autotask.product.vendor.update": ("ProductVendors", "userAccessForUpdate"),
    "autotask.service.create": ("Services", "userAccessForCreate"),
    "autotask.service.update": ("Services", "userAccessForUpdate"),
    "autotask.service.bundle.create": ("ServiceBundles", "userAccessForCreate"),
    "autotask.service.bundle.update": ("ServiceBundles", "userAccessForUpdate"),
    "autotask.purchase.order.create": ("PurchaseOrders", "userAccessForCreate"),
    "autotask.purchase.order.update": ("PurchaseOrders", "userAccessForUpdate"),
    "autotask.purchase.order.item.create": (
        "PurchaseOrderItems",
        "userAccessForCreate",
    ),
    "autotask.purchase.order.item.update": (
        "PurchaseOrderItems",
        "userAccessForUpdate",
    ),
}


SAFE_FIELDS = {
    "autotask.product.create": frozenset({
        "name", "description", "isActive", "isSerialized", "sku",
        "vendorProductNumber", "defaultVendorID", "unitCost", "unitPrice",
        "msrp", "productCategory", "periodType", "doesNotRequireProcurement",
        "productBillingCodeID", "chargeBillingCodeID",
    }),
    "autotask.product.update": frozenset({
        "id", "name", "description", "isActive", "isSerialized", "sku",
        "vendorProductNumber", "defaultVendorID", "unitCost", "unitPrice",
        "msrp", "productCategory", "periodType", "doesNotRequireProcurement",
        "productBillingCodeID", "chargeBillingCodeID",
    }),
    "autotask.product.vendor.create": frozenset({
        "productID", "vendorID", "isActive", "isDefault",
        "vendorCost", "vendorPartNumber",
    }),
    "autotask.product.vendor.update": frozenset({
        "id", "vendorID", "isActive", "isDefault",
        "vendorCost", "vendorPartNumber",
    }),
    "autotask.service.create": frozenset({
        "billingCodeID", "name", "periodType", "unitPrice", "unitCost",
        "description", "invoiceDescription", "isActive", "sku",
        "vendorCompanyID", "catalogNumberPartNumber",
    }),
    "autotask.service.update": frozenset({
        "id", "billingCodeID", "name", "unitPrice", "unitCost",
        "description", "invoiceDescription", "isActive", "sku",
        "vendorCompanyID", "catalogNumberPartNumber",
    }),
    "autotask.service.bundle.create": frozenset({
        "billingCodeID", "name", "unitPrice", "description",
        "invoiceDescription", "isActive", "sku", "catalogNumberPartNumber",
    }),
    "autotask.service.bundle.update": frozenset({
        "id", "billingCodeID", "name", "unitPrice", "description",
        "invoiceDescription", "isActive", "sku", "catalogNumberPartNumber",
    }),
    "autotask.purchase.order.create": frozenset({
        "vendorID", "purchaseForCompanyID", "externalPONumber",
        "vendorInvoiceNumber", "freight", "generalMemo", "paymentTerm",
        "purchaseOrderTemplateID", "shippingType", "shipToAddress1",
        "shipToAddress2", "shipToCity", "shipToName", "shipToPostalCode",
        "shipToState", "taxRegionID", "useItemDescriptionsFrom",
        "showTaxCategory", "showEachTaxInGroup",
    }),
    "autotask.purchase.order.update": frozenset({
        "id", "vendorInvoiceNumber", "externalPONumber", "paymentTerm",
        "taxRegionID", "showTaxCategory", "showEachTaxInGroup",
        "generalMemo", "purchaseForCompanyID", "status", "freight",
    }),
    "autotask.purchase.order.item.create": frozenset({
        "orderID", "productID", "inventoryLocationID", "quantity",
        "unitCost", "estimatedArrivalDate", "memo",
    }),
    "autotask.purchase.order.item.update": frozenset({
        "id", "productID", "inventoryLocationID", "quantity",
        "unitCost", "estimatedArrivalDate", "memo",
    }),
}


REQUIRED_CREATE_FIELDS = {
    "autotask.product.create": frozenset({"name", "isActive", "isSerialized"}),
    "autotask.product.vendor.create": frozenset(
        {"productID", "vendorID", "isActive", "isDefault"}
    ),
    "autotask.service.create": frozenset(
        {"billingCodeID", "name", "periodType", "unitPrice"}
    ),
    "autotask.service.bundle.create": frozenset({"billingCodeID", "name"}),
    "autotask.purchase.order.create": frozenset({"vendorID"}),
    "autotask.purchase.order.item.create": frozenset(
        {"orderID", "inventoryLocationID", "quantity", "unitCost"}
    ),
}
class AutotaskProcurementMutationConnector(AutotaskMutationConnector):
    """Dormant least-privilege connector for approved procurement mutations.

    Source presence does not register or activate these capabilities. Runtime
    composition must provide a separate procurement write secret, exact grants,
    approval, and post-mutation verification before use.
    """

    logical_secret = "autotask.procurement.write"
    capabilities = AUTOTASK_PROCUREMENT_MUTATION_OPERATIONS
    operation_preflight = PROCUREMENT_OPERATION_PREFLIGHT

    @staticmethod
    def _validated_payload(
        operation: str,
        payload: Any,
    ) -> dict[str, Any]:
        if not isinstance(payload, Mapping) or not payload:
            raise ValueError("procurement mutation requires a structured payload")
        normalized = dict(payload)
        allowed = SAFE_FIELDS[operation]
        unknown = set(normalized) - allowed
        if unknown:
            raise PermissionError("AUTOTASK_PROCUREMENT_FIELD_NOT_ALLOWED")
        if operation.endswith(".update"):
            raw_id = normalized.get("id")
            if isinstance(raw_id, bool) or not str(raw_id or "").isdigit():
                raise ValueError("procurement update requires a positive durable id")
            if int(raw_id) < 1:
                raise ValueError("procurement update requires a positive durable id")
            normalized["id"] = int(raw_id)
        required = REQUIRED_CREATE_FIELDS.get(operation, frozenset())
        missing = sorted(
            field
            for field in required
            if normalized.get(field) is None or normalized.get(field) == ""
        )
        if missing:
            raise ValueError(
                "procurement create is missing required fields: "
                + ", ".join(missing)
            )
        return normalized

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        if request.context.capability not in self.capabilities:
            raise ConnectorAuthorizationError(
                "Capability is not registered for procurement mutation."
            )
        payload = self._validated_payload(
            request.context.capability,
            request.arguments.get("payload"),
        )
        normalized = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": payload},
        )
        return super().execute(normalized)
