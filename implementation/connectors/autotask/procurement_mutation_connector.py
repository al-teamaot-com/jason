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
        "autotask.vendor.create",
        "autotask.product.create",
        "autotask.product.update",
        "autotask.product.vendor.create",
        "autotask.product.vendor.update",
        "autotask.service.create",
        "autotask.service.update",
        "autotask.service.bundle.create",
        "autotask.service.bundle.update",
        "autotask.opportunity.create",
        "autotask.quote.location.create",
        "autotask.quote.create",
        "autotask.quote.item.create",
        "autotask.purchase.order.create",
        "autotask.purchase.order.update",
        "autotask.purchase.order.item.create",
        "autotask.purchase.order.item.update",
        "autotask.purchase.order.item.receiving.create",
        "autotask.ticket.charge.create",
        "autotask.ticket.charge.update",
    }
)
PROCUREMENT_OPERATION_PREFLIGHT = {
    "autotask.vendor.create": ("Companies", "userAccessForCreate"),
    "autotask.product.create": ("Products", "userAccessForCreate"),
    "autotask.product.update": ("Products", "userAccessForUpdate"),
    "autotask.product.vendor.create": ("ProductVendors", "userAccessForCreate"),
    "autotask.product.vendor.update": ("ProductVendors", "userAccessForUpdate"),
    "autotask.service.create": ("Services", "userAccessForCreate"),
    "autotask.service.update": ("Services", "userAccessForUpdate"),
    "autotask.service.bundle.create": ("ServiceBundles", "userAccessForCreate"),
    "autotask.service.bundle.update": ("ServiceBundles", "userAccessForUpdate"),
    "autotask.opportunity.create": ("Opportunities", "userAccessForCreate"),
    "autotask.quote.location.create": ("QuoteLocations", "userAccessForCreate"),
    "autotask.quote.create": ("Quotes", "userAccessForCreate"),
    "autotask.quote.item.create": ("QuoteItems", "userAccessForCreate"),
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
    "autotask.purchase.order.item.receiving.create": (
        "PurchaseOrderItemReceiving",
        "userAccessForCreate",
    ),
    "autotask.ticket.charge.create": ("TicketCharges", "userAccessForCreate"),
    "autotask.ticket.charge.update": ("TicketCharges", "userAccessForUpdate"),
}


SAFE_FIELDS = {
    "autotask.vendor.create": frozenset({
        "companyName", "address1", "address2", "city", "state", "postalCode",
        "countryID", "phone", "webAddress",
    }),
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
    "autotask.opportunity.create": frozenset({
        "amount", "companyID", "contactID", "cost", "description", "ownerResourceID",
        "probability", "projectedCloseDate", "stage", "startDate", "status", "title",
        "useQuoteTotals", "onetimeRevenue", "onetimeCost", "productID",
    }),
    "autotask.quote.location.create": frozenset({
        "address1", "address2", "city", "postalCode", "state",
    }),
    "autotask.quote.create": frozenset({
        "billToLocationID", "companyID", "contactID", "comment", "description",
        "effectiveDate", "expirationDate", "externalQuoteNumber", "isActive",
        "name", "opportunityID", "primaryQuote", "quoteTemplateID",
        "shipToLocationID", "soldToLocationID", "taxRegionID",
    }),
    "autotask.quote.item.create": frozenset({
        "productID", "description", "isOptional", "lineDiscount", "name",
        "percentageDiscount", "periodType", "quantity", "quoteItemType",
        "taxCategoryID", "unitCost", "unitDiscount", "unitPrice",
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
    "autotask.purchase.order.item.receiving.create": frozenset({
        "purchaseOrderItemID", "quantityNowReceiving", "serialNumber",
        "vendorInvoiceNumber",
    }),
    "autotask.ticket.charge.create": frozenset({
        "ticketID", "productID", "billingCodeID", "costType", "chargeType",
        "datePurchased", "name", "unitQuantity", "unitCost", "unitPrice",
        "isBillableToCompany", "description", "notes",
        "internalPurchaseOrderNumber", "purchaseOrderNumber",
    }),
    "autotask.ticket.charge.update": frozenset({
        "id", "productID", "billingCodeID", "costType", "chargeType",
        "datePurchased", "name", "unitQuantity", "unitCost", "unitPrice",
        "isBillableToCompany", "description", "notes",
        "internalPurchaseOrderNumber", "purchaseOrderNumber",
    }),
}


REQUIRED_CREATE_FIELDS = {
    "autotask.vendor.create": frozenset({"companyName"}),
    "autotask.product.create": frozenset({"name", "isActive", "isSerialized"}),
    "autotask.product.vendor.create": frozenset(
        {"productID", "vendorID", "isActive", "isDefault"}
    ),
    "autotask.service.create": frozenset(
        {"billingCodeID", "name", "periodType", "unitPrice"}
    ),
    "autotask.service.bundle.create": frozenset({"billingCodeID", "name"}),
    "autotask.opportunity.create": frozenset({
        "amount", "companyID", "cost", "ownerResourceID", "probability",
        "projectedCloseDate", "stage", "startDate", "status", "title", "useQuoteTotals",
    }),
    "autotask.quote.location.create": frozenset(),
    "autotask.quote.create": frozenset({
        "billToLocationID", "effectiveDate", "expirationDate", "name",
        "opportunityID", "shipToLocationID", "soldToLocationID",
    }),
    "autotask.quote.item.create": frozenset({
        "productID", "isOptional", "lineDiscount", "name", "percentageDiscount",
        "periodType", "quantity", "quoteItemType", "unitDiscount",
    }),
    "autotask.purchase.order.create": frozenset({"vendorID"}),
    "autotask.purchase.order.item.create": frozenset(
        {"orderID", "inventoryLocationID", "quantity", "unitCost"}
    ),
    "autotask.purchase.order.item.receiving.create": frozenset(
        {"purchaseOrderItemID", "quantityNowReceiving"}
    ),
    "autotask.ticket.charge.create": frozenset(
        {"ticketID", "costType", "datePurchased", "name", "unitQuantity"}
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
        if operation == "autotask.vendor.create":
            # Procurement authority may create only Autotask Vendor companies.
            # AOT defaults are server-controlled and cannot be supplied or changed
            # by the conversational payload.
            normalized.update({
                "companyType": 7,
                "ownerResourceID": 29682892,
                "territoryID": 29682778,
                "companyCategoryID": 1,
                "currencyID": 1,
                "purchaseOrderTemplateID": 102,
                "isActive": True,
            })
            normalized["phone"] = str(normalized.get("phone") or "0").strip() or "0"
        if operation == "autotask.ticket.charge.create":
            if not normalized.get("productID") and not normalized.get("billingCodeID"):
                raise ValueError("ticket charge requires productID or billingCodeID")
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
        arguments = {**dict(request.arguments), "payload": payload}
        if request.context.capability == "autotask.product.vendor.create":
            arguments["productID"] = int(payload["productID"])
        if request.context.capability == "autotask.quote.item.create":
            raw_quote_id = request.arguments.get("quoteID") or request.arguments.get("quote_id")
            if isinstance(raw_quote_id, bool) or not str(raw_quote_id or "").isdigit() or int(raw_quote_id) < 1:
                raise ValueError("quote item create requires positive quoteID route selector")
            arguments["quoteID"] = int(raw_quote_id)
        if request.context.capability == "autotask.ticket.charge.update":
            raw_ticket_id = request.arguments.get("ticketID") or request.arguments.get("ticket_id")
            if isinstance(raw_ticket_id, bool) or not str(raw_ticket_id or "").isdigit() or int(raw_ticket_id) < 1:
                raise ValueError("ticket charge update requires positive ticketID route selector")
            arguments["ticketID"] = int(raw_ticket_id)
        normalized = ConnectorRequest(
            context=request.context,
            arguments=arguments,
        )
        return super().execute(normalized)
