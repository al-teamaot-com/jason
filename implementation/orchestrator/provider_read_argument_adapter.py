from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any, Mapping

from kernel.resolution import CapabilityResolutionResult

from .connector_invoker import GovernedConnectorCapabilityInvoker
from .contracts import OrchestrationRequest
from .provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    DOCUMENTATION_CONFIGURATION_READ,
    DOCUMENTATION_CONFIGURATION_SEARCH,
    DOCUMENTATION_CONTACT_READ,
    DOCUMENTATION_CONTACT_SEARCH,
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_ATTACHMENT_SEARCH,
    DOCUMENTATION_ATTACHMENT_READ,
    DOCUMENTATION_ATTACHMENT_CONTENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
    DOCUMENTATION_FLEXIBLE_ASSET_READ,
    DOCUMENTATION_FLEXIBLE_ASSET_SEARCH,
    DOCUMENTATION_FLEXIBLE_ASSET_TYPE_READ,
    DOCUMENTATION_FLEXIBLE_ASSET_TYPE_SEARCH,
    DOCUMENTATION_LOCATION_READ,
    DOCUMENTATION_LOCATION_SEARCH,
    DOCUMENTATION_ORGANIZATION_READ,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IDENTITY_USER_READ,
    IDENTITY_AUTHENTICATION_METHODS_READ,
    IDENTITY_CONDITIONAL_ACCESS_SEARCH,
    IDENTITY_DIRECTORY_ROLE_SEARCH,
    IDENTITY_DIRECTORY_ROLE_MEMBERS_SEARCH,
    IDENTITY_USER_SEARCH,
    COMMUNICATION_MAIL_MESSAGE_SEARCH,
    COMMUNICATION_MAIL_MESSAGE_READ,
    COMMUNICATION_MAIL_ATTACHMENT_SEARCH,
    IT_GLUE_PROVIDER,
    MICROSOFT_GRAPH_PROVIDER,
    SERVICE_COMPANY_READ,
    SERVICE_COMPANY_SEARCH,
    SERVICE_CONFIGURATION_READ,
    SERVICE_CONFIGURATION_SEARCH,
    SERVICE_CONTRACT_READ,
    SERVICE_CONTRACT_SEARCH,
    SERVICE_CONTACT_READ,
    SERVICE_CONTACT_SEARCH,
    SERVICE_RESOURCE_READ,
    SERVICE_RESOURCE_SEARCH,
    SERVICE_ENTITY_DESCRIBE,
    SERVICE_ENTITY_FIELDS_DESCRIBE,
    SERVICE_NOTIFICATION_HISTORY_SEARCH,
    SERVICE_PRODUCT_SEARCH,
    SERVICE_PRODUCT_READ,
    SERVICE_PRODUCT_VENDOR_SEARCH,
    SERVICE_SERVICE_SEARCH,
    SERVICE_SERVICE_READ,
    SERVICE_SERVICE_BUNDLE_SEARCH,
    SERVICE_SERVICE_BUNDLE_READ,
    SERVICE_PURCHASE_ORDER_SEARCH,
    SERVICE_PURCHASE_ORDER_READ,
    SERVICE_PURCHASE_ORDER_ITEM_SEARCH,
    SERVICE_TICKET_CHARGE_SEARCH,
    SERVICE_TICKET_CHARGE_READ,
    SERVICE_INVOICE_SEARCH,
    SERVICE_INVOICE_READ,
    SERVICE_BILLING_ITEM_SEARCH,
    SERVICE_BILLING_ITEM_READ,
    SERVICE_QUOTE_SEARCH,
    SERVICE_QUOTE_READ,
    SERVICE_OPPORTUNITY_SEARCH,
    SERVICE_OPPORTUNITY_READ,
    SERVICE_TICKET_COUNT,
    SERVICE_TICKET_NOTES_SEARCH,
    SERVICE_TICKET_ATTACHMENT_SEARCH,
    SERVICE_TICKET_ATTACHMENT_READ,
    SERVICE_TICKET_ATTACHMENT_CONTENT_READ,
    SERVICE_TICKET_READ,
    SERVICE_TICKET_SEARCH,
)
from .service import InvocationResult, InvocationTelemetry


_IT_GLUE_ENTITY = {
    DOCUMENTATION_ORGANIZATION_SEARCH: "Organizations",
    DOCUMENTATION_CONTACT_SEARCH: "Contacts",
    DOCUMENTATION_CONTACT_READ: "Contacts",
    DOCUMENTATION_LOCATION_SEARCH: "Locations",
    DOCUMENTATION_LOCATION_READ: "Locations",
    DOCUMENTATION_CONFIGURATION_SEARCH: "Configurations",
    DOCUMENTATION_CONFIGURATION_READ: "Configurations",
    DOCUMENTATION_DOCUMENT_READ: "Documents",
    DOCUMENTATION_FLEXIBLE_ASSET_SEARCH: "FlexibleAssets",
    DOCUMENTATION_FLEXIBLE_ASSET_READ: "FlexibleAssets",
    DOCUMENTATION_FLEXIBLE_ASSET_TYPE_SEARCH: "FlexibleAssetTypes",
    DOCUMENTATION_FLEXIBLE_ASSET_TYPE_READ: "FlexibleAssetTypes",
}

_IT_GLUE_SEARCH_CAPABILITIES = frozenset(
    {
        DOCUMENTATION_ORGANIZATION_SEARCH,
        DOCUMENTATION_CONTACT_SEARCH,
        DOCUMENTATION_LOCATION_SEARCH,
        DOCUMENTATION_CONFIGURATION_SEARCH,
        DOCUMENTATION_DOCUMENT_SEARCH,
        DOCUMENTATION_FLEXIBLE_ASSET_SEARCH,
        DOCUMENTATION_FLEXIBLE_ASSET_TYPE_SEARCH,
    }
)

_IT_GLUE_SAFE_PAGINATION_META_KEYS = frozenset(
    {
        "current-page",
        "current_page",
        "next-page",
        "next_page",
        "prev-page",
        "prev_page",
        "previous-page",
        "previous_page",
        "total-pages",
        "total_pages",
        "total-count",
        "total_count",
        "page-size",
        "page_size",
        "per-page",
        "per_page",
    }
)

_AUTOTASK_SEARCH_FIELDS: Mapping[str, Mapping[str, str]] = {
    SERVICE_COMPANY_SEARCH: {
        "resource_id": "id",
        "name": "companyName",
    },
    SERVICE_CONTACT_SEARCH: {
        "resource_id": "id",
        "company_id": "companyID",
        "first_name": "firstName",
        "last_name": "lastName",
        "email": "emailAddress",
    },
    SERVICE_RESOURCE_SEARCH: {
        "resource_id": "id",
        "first_name": "firstName",
        "last_name": "lastName",
        "email": "email",
    },
    SERVICE_RESOURCE_READ: {
        "resource_id": "id",
    },
    SERVICE_TICKET_SEARCH: {
        "resource_id": "id",
        "ticket_number": "ticketNumber",
        "company_id": "companyID",
        "status": "status",
    },
    SERVICE_TICKET_COUNT: {
        "resource_id": "id",
        "ticket_number": "ticketNumber",
        "company_id": "companyID",
        "status": "status",
    },
    SERVICE_CONFIGURATION_SEARCH: {
        "resource_id": "id",
        "company_id": "companyID",
        "name": "referenceTitle",
    },
    SERVICE_CONTRACT_SEARCH: {
        "resource_id": "id",
        "company_id": "companyID",
        "contract_name": "contractName",
        "contract_number": "contractNumber",
        "status": "status",
        "contract_type": "contractType",
        "contract_category": "contractCategory",
    },
    SERVICE_CONTRACT_READ: {
        "resource_id": "id",
        "company_id": "companyID",
    },
    SERVICE_NOTIFICATION_HISTORY_SEARCH: {
        "resource_id": "id",
        "company_id": "companyID",
        "ticket_id": "ticketID",
        "template_name": "templateName",
    },
    SERVICE_PRODUCT_SEARCH: {
        "resource_id": "id",
        "name": "name",
        "sku": "sku",
    },
    SERVICE_PRODUCT_VENDOR_SEARCH: {
        "resource_id": "id",
        "product_id": "productID",
        "vendor_id": "vendorID",
    },
    SERVICE_SERVICE_SEARCH: {
        "resource_id": "id",
        "name": "name",
    },
    SERVICE_SERVICE_BUNDLE_SEARCH: {
        "resource_id": "id",
        "name": "name",
    },
    SERVICE_PURCHASE_ORDER_SEARCH: {
        "resource_id": "id",
        "purchase_order_number": "purchaseOrderNumber",
        "vendor_id": "vendorID",
        "vendor_invoice_number": "vendorInvoiceNumber",
    },
    SERVICE_PURCHASE_ORDER_ITEM_SEARCH: {
        "resource_id": "id",
        "purchase_order_id": "orderID",
        "product_id": "productID",
    },
    SERVICE_TICKET_CHARGE_SEARCH: {
        "resource_id": "id",
        "ticket_id": "ticketID",
        "product_id": "productID",
        "is_billed": "isBilled",
    },
    SERVICE_INVOICE_SEARCH: {
        "resource_id": "id",
        "company_id": "companyID",
        "invoice_number": "invoiceNumber",
    },
    SERVICE_BILLING_ITEM_SEARCH: {
        "resource_id": "id",
        "invoice_id": "invoiceID",
        "ticket_id": "ticketID",
        "ticket_charge_id": "ticketChargeID",
    },
    SERVICE_QUOTE_SEARCH: {
        "resource_id": "id",
        "company_id": "companyID",
        "opportunity_id": "opportunityID",
        "external_quote_number": "externalQuoteNumber",
    },
    SERVICE_OPPORTUNITY_SEARCH: {
        "resource_id": "id",
        "company_id": "companyID",
        "title": "title",
    },
}

_DEFAULT_IT_GLUE_PAGE_SIZE = 100
_MAX_IT_GLUE_PAGE_SIZE = 1000
_DEFAULT_AUTOTASK_MAX_RECORDS = 100
_MAX_AUTOTASK_MAX_RECORDS = 500
_MAX_MICROSOFT_USER_RECORDS = 25


def _resource_id(arguments: Mapping[str, Any]) -> Any:
    value = arguments.get("resource_id")
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("resource_id is required for an exact provider read")
    return value


def _ticket_read_selector(arguments: Mapping[str, Any]) -> Any:
    """Resolve one human or durable ticket selector without first-match guessing.

    ChatGPT may naturally place an Autotask ticket number in ``ticket_id`` or
    ``resource_id``. Canonical ticket read accepts those aliases plus the explicit
    ``ticket_number`` selector. Multiple supplied selectors must identify the same
    textual value or the read fails closed as ambiguous.
    """

    supplied: list[tuple[str, Any]] = []
    for key in ("ticket_number", "ticket_id", "resource_id"):
        value = arguments.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        supplied.append((key, value))

    if not supplied:
        raise ValueError(
            "ticket_number, ticket_id, or resource_id is required for an exact ticket read"
        )

    normalized = {str(value).strip() for _, value in supplied}
    if len(normalized) != 1:
        raise ValueError("conflicting ticket selectors are not allowed")

    return supplied[0][1]


def _canonical_filters(
    arguments: Mapping[str, Any],
    *,
    excluded: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    filters = arguments.get("filters", {})
    if filters is None:
        filters = {}
    if not isinstance(filters, Mapping):
        raise ValueError("filters must be a mapping when supplied")

    result = {
        str(key): value
        for key, value in filters.items()
        if str(key).strip()
    }
    ignored = {
        "requested_facts",
        "result_intent",
        "completeness_requirement",
        "resource_id",
        "filters",
        "page_number",
        "page_size",
        "after_resource_id",
    }
    ignored.update(excluded)
    for key, value in arguments.items():
        if key in ignored or value is None:
            continue
        result.setdefault(str(key), value)
    return result


def _it_glue_page_size(arguments: Mapping[str, Any]) -> int:
    value = arguments.get("page_size", _DEFAULT_IT_GLUE_PAGE_SIZE)
    if isinstance(value, bool):
        raise ValueError("page_size must be an integer between 1 and 1000")
    try:
        page_size = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("page_size must be an integer between 1 and 1000") from error
    if not 1 <= page_size <= _MAX_IT_GLUE_PAGE_SIZE:
        raise ValueError("page_size must be between 1 and 1000")
    return page_size


def adapt_it_glue_arguments(
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Translate canonical documentation reads into the existing IT Glue connector.

    The model never needs to provide IT Glue entity-path tokens. Password/vault
    resources are impossible here because only the fixed approved entity families
    below can be injected by this adapter.
    """

    if capability_name == DOCUMENTATION_ORGANIZATION_READ:
        return {"organization_id": _resource_id(arguments)}
    if capability_name == DOCUMENTATION_DOCUMENT_READ:
        return {"document_id": _resource_id(arguments)}
    if capability_name == DOCUMENTATION_ATTACHMENT_SEARCH:
        document_id = arguments.get("document_id")
        if document_id is None or (isinstance(document_id, str) and not document_id.strip()):
            raise ValueError("document_id is required for IT Glue document attachment search")
        return {"document_id": document_id}
    if capability_name in {DOCUMENTATION_ATTACHMENT_READ, DOCUMENTATION_ATTACHMENT_CONTENT_READ}:
        document_id = arguments.get("document_id")
        if document_id is None or (isinstance(document_id, str) and not document_id.strip()):
            raise ValueError("document_id is required for IT Glue document attachment read")
        result = {"document_id": document_id, "attachment_id": _resource_id(arguments)}
        if capability_name == DOCUMENTATION_ATTACHMENT_CONTENT_READ:
            max_bytes = arguments.get("max_bytes", 10 * 1024 * 1024)
            if isinstance(max_bytes, bool):
                raise ValueError("max_bytes must be an integer between 1 and 15728640")
            try:
                max_bytes = int(max_bytes)
            except (TypeError, ValueError) as error:
                raise ValueError("max_bytes must be an integer between 1 and 15728640") from error
            if not 1 <= max_bytes <= 15 * 1024 * 1024:
                raise ValueError("max_bytes must be between 1 and 15728640")
            result["max_bytes"] = max_bytes
        return result

    if capability_name == DOCUMENTATION_FLEXIBLE_ASSET_SEARCH:
        type_id = arguments.get("flexible_asset_type_id")
        if type_id is None or (isinstance(type_id, str) and not type_id.strip()):
            raise ValueError("flexible_asset_type_id is required for IT Glue flexible asset search")
        filters = {"flexible-asset-type-id": type_id}
        organization_id = arguments.get("organization_id")
        if organization_id is not None and not (
            isinstance(organization_id, str) and not organization_id.strip()
        ):
            filters["organization-id"] = organization_id
        name = arguments.get("name")
        if name is not None and not (isinstance(name, str) and not name.strip()):
            filters["name"] = name
        if arguments.get("filters") not in (None, {}):
            raise ValueError("filters are not accepted for flexible asset search; use declared selectors")
        result = {
            "entity": "FlexibleAssets",
            "filters": filters,
            "page_size": _it_glue_page_size(arguments),
        }
        if arguments.get("page_number") is not None:
            result["page_number"] = arguments["page_number"]
        return result

    if capability_name == DOCUMENTATION_DOCUMENT_SEARCH:
        organization_id = arguments.get("organization_id")
        if organization_id is None or (
            isinstance(organization_id, str)
            and not organization_id.strip()
        ):
            raise ValueError(
                "organization_id is required for IT Glue document search"
            )

        if arguments.get("name") is not None:
            raise ValueError(
                "name is not a provider-supported IT Glue document "
                "collection filter"
            )

        if arguments.get("resource_id") is not None:
            raise ValueError(
                "resource_id is not valid for document collection search; "
                "use documentation.document.read"
            )

        filters = arguments.get("filters", {})
        if filters is None:
            filters = {}
        if not isinstance(filters, Mapping):
            raise ValueError(
                "filters must be a mapping when supplied"
            )

        unsupported = sorted(
            str(key)
            for key in filters
            if str(key) != "document_folder_id"
        )
        if unsupported:
            raise ValueError(
                "unsupported IT Glue document search filters: "
                + ", ".join(unsupported)
            )

        result = {
            "organization_id": organization_id,
            "filters": dict(filters),
            "page_size": _it_glue_page_size(arguments),
        }

        if arguments.get("page_number") is not None:
            result["page_number"] = arguments["page_number"]

        return result

    entity = _IT_GLUE_ENTITY.get(capability_name)
    if entity is None:
        raise ValueError(f"Unsupported IT Glue canonical capability: {capability_name}")

    if capability_name.endswith(".read"):
        return {
            "entity": entity,
            "entity_id": _resource_id(arguments),
        }

    result: dict[str, Any] = {
        "entity": entity,
        "filters": _canonical_filters(arguments),
        "page_size": _it_glue_page_size(arguments),
    }
    if arguments.get("page_number") is not None:
        result["page_number"] = arguments["page_number"]
    return result


def _autotask_max_records(arguments: Mapping[str, Any]) -> int:
    value = arguments.get("page_size", _DEFAULT_AUTOTASK_MAX_RECORDS)
    if isinstance(value, bool):
        raise ValueError("page_size must be an integer between 1 and 500")
    try:
        maximum = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("page_size must be an integer between 1 and 500") from error
    if not 1 <= maximum <= _MAX_AUTOTASK_MAX_RECORDS:
        raise ValueError("page_size must be between 1 and 500")
    return maximum


def _autotask_after_resource_id(arguments: Mapping[str, Any]) -> int | None:
    value = arguments.get("after_resource_id")
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("after_resource_id must be a positive integer")
    try:
        resource_id = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("after_resource_id must be a positive integer") from error
    if resource_id < 1:
        raise ValueError("after_resource_id must be a positive integer")
    return resource_id


def _autotask_created_range_value(
    arguments: Mapping[str, Any],
    selector: str,
) -> str | None:
    value = arguments.get(selector)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{selector} must be a non-empty ISO-8601 datetime string")
    return value.strip()


def _autotask_search(
    capability_name: str,
    arguments: Mapping[str, Any],
) -> str:
    explicit = arguments.get("search")
    if explicit is not None:
        raise ValueError(
            "provider-specific Autotask search expressions are not accepted by the "
            "canonical read adapter; use canonical selectors or schema-driven filters"
        )

    filters = arguments.get("filters", {})
    if filters is None:
        filters = {}
    if not isinstance(filters, Mapping):
        raise ValueError("filters must be a mapping when supplied")

    clauses: list[dict[str, Any]] = []
    ticket_filter_aliases = {
        "queue": "queueID",
        "queue_name": "queueID",
        "queueName": "queueID",
        "status_name": "status",
        "statusName": "status",
    } if capability_name in {SERVICE_TICKET_SEARCH, SERVICE_TICKET_COUNT} else {}
    for field, value in filters.items():
        field_name = str(field).strip()
        if not field_name:
            raise ValueError("Autotask filter field names must be non-empty")
        field_name = ticket_filter_aliases.get(field_name, field_name)
        clauses.append({"op": "eq", "field": field_name, "value": value})

    if capability_name in {SERVICE_TICKET_SEARCH, SERVICE_TICKET_COUNT}:
        created_after = _autotask_created_range_value(arguments, "created_after")
        created_before = _autotask_created_range_value(arguments, "created_before")
        if created_after is not None:
            clauses.append(
                {"op": "gte", "field": "createDate", "value": created_after}
            )
        if created_before is not None:
            clauses.append(
                {"op": "lte", "field": "createDate", "value": created_before}
            )

    after_resource_id = _autotask_after_resource_id(arguments)
    if after_resource_id is not None:
        if arguments.get("resource_id") is not None or any(
            item["field"] == "id" for item in clauses
        ):
            raise ValueError(
                "after_resource_id cannot be combined with an exact id selector"
            )
        clauses.append(
            {"op": "gt", "field": "id", "value": after_resource_id}
        )

    for selector, provider_field in _AUTOTASK_SEARCH_FIELDS[capability_name].items():
        value = arguments.get(selector)
        if value is None or any(item["field"] == provider_field for item in clauses):
            continue
        if (
            capability_name in {SERVICE_TICKET_SEARCH, SERVICE_TICKET_COUNT}
            and selector == "status"
            and isinstance(value, str)
            and value.strip().casefold() in {"open", "unresolved"}
        ):
            # Internal semantic operator. The Autotask impersonating connector
            # resolves this against the live ticket-status picklist and replaces
            # it with provider-supported terminal-status exclusions before I/O.
            clauses.append(
                {"op": "jason_open", "field": provider_field, "value": "open"}
            )
            continue
        clauses.append({"op": "eq", "field": provider_field, "value": value})

    if not clauses:
        clauses.append({"op": "exist", "field": "id"})

    return json.dumps(
        {
            "MaxRecords": _autotask_max_records(arguments),
            "filter": clauses,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _autotask_count(
    capability_name: str,
    arguments: Mapping[str, Any],
) -> str:
    if arguments.get("after_resource_id") is not None:
        raise ValueError("after_resource_id is not valid for an Autotask count")

    bounded_arguments = dict(arguments)
    bounded_arguments["page_size"] = 1
    payload = json.loads(_autotask_search(capability_name, bounded_arguments))
    payload.pop("MaxRecords", None)
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def adapt_autotask_arguments(
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_name == SERVICE_COMPANY_READ:
        return {"company_id": _resource_id(arguments)}
    if capability_name == SERVICE_CONTACT_READ:
        return {"contact_id": _resource_id(arguments)}
    if capability_name == SERVICE_TICKET_READ:
        return {"ticket_id": _ticket_read_selector(arguments)}
    if capability_name == SERVICE_CONFIGURATION_READ:
        return {"configuration_item_id": _resource_id(arguments)}
    if capability_name == SERVICE_TICKET_NOTES_SEARCH:
        return {
            "ticket_id": arguments.get("ticket_id") or _resource_id(arguments)
        }
    if capability_name in {
        SERVICE_TICKET_ATTACHMENT_SEARCH,
        SERVICE_TICKET_ATTACHMENT_READ,
        SERVICE_TICKET_ATTACHMENT_CONTENT_READ,
    }:
        company_id = arguments.get("company_id")
        ticket_id = arguments.get("ticket_id")
        if company_id is None or isinstance(company_id, bool):
            raise ValueError("company_id is required for ticket attachment reads")
        if ticket_id is None or isinstance(ticket_id, bool):
            raise ValueError("ticket_id is required for ticket attachment reads")
        try:
            company_id = int(company_id); ticket_id = int(ticket_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("company_id and ticket_id must be positive integers") from exc
        if company_id < 1 or ticket_id < 1:
            raise ValueError("company_id and ticket_id must be positive integers")
        result = {"company_id": company_id, "ticket_id": ticket_id}
        if capability_name != SERVICE_TICKET_ATTACHMENT_SEARCH:
            attachment_id = _resource_id(arguments)
            if isinstance(attachment_id, bool):
                raise ValueError("attachment id must be a positive integer")
            try:
                attachment_id = int(attachment_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("attachment id must be a positive integer") from exc
            if attachment_id < 1:
                raise ValueError("attachment id must be a positive integer")
            result["attachment_id"] = attachment_id
        if capability_name == SERVICE_TICKET_ATTACHMENT_CONTENT_READ:
            raw_max = arguments.get("max_bytes", 6_000_000)
            if isinstance(raw_max, bool):
                raise ValueError("max_bytes must be between 1 and 6000000")
            try:
                max_bytes = int(raw_max)
            except (TypeError, ValueError) as exc:
                raise ValueError("max_bytes must be between 1 and 6000000") from exc
            if not 1 <= max_bytes <= 6_000_000:
                raise ValueError("max_bytes must be between 1 and 6000000")
            result["max_bytes"] = max_bytes
        return result
    if capability_name == SERVICE_NOTIFICATION_HISTORY_SEARCH:
        company_id = arguments.get("company_id")
        if company_id is None or not str(company_id).strip():
            raise ValueError("company_id is required for notification-history search")
        return {"search": _autotask_search(capability_name, arguments)}
    if capability_name == SERVICE_CONTRACT_READ:
        company_id = arguments.get("company_id")
        if company_id is None or not str(company_id).strip():
            raise ValueError("company_id is required for contract read")
        _resource_id(arguments)
        return {"entity": "Contracts", "search": _autotask_search(capability_name, arguments)}
    if capability_name == SERVICE_CONTRACT_SEARCH:
        company_id = arguments.get("company_id")
        if company_id is None or not str(company_id).strip():
            raise ValueError("company_id is required for contract search")
        return {"entity": "Contracts", "search": _autotask_search(capability_name, arguments)}
    if capability_name == SERVICE_RESOURCE_READ:
        return {"entity": "Resources", "entity_id": _resource_id(arguments)}
    if capability_name == SERVICE_PRODUCT_READ:
        return {"entity": "Products", "entity_id": _resource_id(arguments)}
    if capability_name == SERVICE_SERVICE_READ:
        return {"entity": "Services", "entity_id": _resource_id(arguments)}
    if capability_name == SERVICE_SERVICE_BUNDLE_READ:
        return {"entity": "ServiceBundles", "entity_id": _resource_id(arguments)}
    if capability_name == SERVICE_PURCHASE_ORDER_READ:
        return {"entity": "PurchaseOrders", "entity_id": _resource_id(arguments)}
    if capability_name == SERVICE_TICKET_CHARGE_READ:
        return {"entity": "TicketCharges", "entity_id": _resource_id(arguments)}
    if capability_name == SERVICE_INVOICE_READ:
        return {"entity": "Invoices", "entity_id": _resource_id(arguments)}
    if capability_name == SERVICE_BILLING_ITEM_READ:
        return {"entity": "BillingItems", "entity_id": _resource_id(arguments)}
    if capability_name == SERVICE_QUOTE_READ:
        return {"entity": "Quotes", "entity_id": _resource_id(arguments)}
    if capability_name == SERVICE_OPPORTUNITY_READ:
        return {"entity": "Opportunities", "entity_id": _resource_id(arguments)}
    entity_searches = {
        SERVICE_RESOURCE_SEARCH: "Resources",
        SERVICE_PRODUCT_SEARCH: "Products",
        SERVICE_PRODUCT_VENDOR_SEARCH: "ProductVendors",
        SERVICE_SERVICE_SEARCH: "Services",
        SERVICE_SERVICE_BUNDLE_SEARCH: "ServiceBundles",
        SERVICE_PURCHASE_ORDER_SEARCH: "PurchaseOrders",
        SERVICE_PURCHASE_ORDER_ITEM_SEARCH: "PurchaseOrderItems",
        SERVICE_TICKET_CHARGE_SEARCH: "TicketCharges",
        SERVICE_INVOICE_SEARCH: "Invoices",
        SERVICE_BILLING_ITEM_SEARCH: "BillingItems",
        SERVICE_QUOTE_SEARCH: "Quotes",
        SERVICE_OPPORTUNITY_SEARCH: "Opportunities",
    }
    if capability_name in entity_searches:
        return {"entity": entity_searches[capability_name], "search": _autotask_search(capability_name, arguments)}
    if capability_name in {SERVICE_ENTITY_DESCRIBE, SERVICE_ENTITY_FIELDS_DESCRIBE}:
        entity = arguments.get("entity")
        if not isinstance(entity, str) or not entity.strip():
            raise ValueError("entity is required for schema description")
        return {"entity": entity.strip()}
    if capability_name == SERVICE_TICKET_COUNT:
        return {"search": _autotask_count(capability_name, arguments)}
    if capability_name in _AUTOTASK_SEARCH_FIELDS:
        return {"search": _autotask_search(capability_name, arguments)}
    raise ValueError(f"Unsupported Autotask canonical capability: {capability_name}")


def _mailbox_address(arguments: Mapping[str, Any]) -> str:
    mailbox = str(arguments.get("mailbox") or "").strip().casefold()
    if not mailbox or "@" not in mailbox:
        raise ValueError("mailbox must be an exact email address")
    return mailbox


def adapt_microsoft_graph_arguments(
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_name == COMMUNICATION_MAIL_MESSAGE_SEARCH:
        result = {"mailbox": _mailbox_address(arguments)}
        for key in ("sender", "received_after", "received_before", "page_size"):
            if arguments.get(key) is not None:
                result[key] = arguments[key]
        return result
    if capability_name == COMMUNICATION_MAIL_MESSAGE_READ:
        message_id = str(arguments.get("message_id") or arguments.get("resource_id") or "").strip()
        if not message_id:
            raise ValueError("message_id is required")
        return {"mailbox": _mailbox_address(arguments), "message_id": message_id}
    if capability_name == COMMUNICATION_MAIL_ATTACHMENT_SEARCH:
        message_id = str(arguments.get("message_id") or "").strip()
        if not message_id:
            raise ValueError("message_id is required")
        result = {"mailbox": _mailbox_address(arguments), "message_id": message_id}
        if arguments.get("page_size") is not None:
            result["page_size"] = arguments["page_size"]
        return result
    if capability_name == IDENTITY_USER_READ:
        return {"resource_id": _resource_id(arguments)}
    if capability_name == IDENTITY_AUTHENTICATION_METHODS_READ:
        user_id = arguments.get("user_id") or arguments.get("resource_id")
        if user_id is None or not str(user_id).strip():
            raise ValueError("user_id is required for authentication method read")
        return {"user_id": str(user_id).strip()}
    if capability_name in {IDENTITY_CONDITIONAL_ACCESS_SEARCH, IDENTITY_DIRECTORY_ROLE_SEARCH}:
        page_size = arguments.get("page_size", 100)
        if isinstance(page_size, bool): raise ValueError("page_size must be between 1 and 100")
        page_size = int(page_size)
        if not 1 <= page_size <= 100: raise ValueError("page_size must be between 1 and 100")
        return {"page_size": page_size}
    if capability_name == IDENTITY_DIRECTORY_ROLE_MEMBERS_SEARCH:
        role_id = arguments.get("role_id") or arguments.get("resource_id")
        if role_id is None or not str(role_id).strip(): raise ValueError("role_id is required for directory role member search")
        page_size = arguments.get("page_size", 100)
        if isinstance(page_size, bool): raise ValueError("page_size must be between 1 and 100")
        page_size = int(page_size)
        if not 1 <= page_size <= 100: raise ValueError("page_size must be between 1 and 100")
        return {"role_id": str(role_id).strip(), "page_size": page_size}
    if capability_name != IDENTITY_USER_SEARCH:
        raise ValueError(
            f"Unsupported Microsoft Graph canonical capability: {capability_name}"
        )

    selectors = [
        key
        for key in ("email", "user_principal_name", "display_name")
        if arguments.get(key) is not None and str(arguments.get(key)).strip()
    ]
    if len(selectors) != 1:
        raise ValueError(
            "Microsoft user search requires exactly one exact selector: "
            "email, user_principal_name, or display_name"
        )
    allowed = {
        "email",
        "user_principal_name",
        "display_name",
        "page_size",
        "requested_facts",
        "result_intent",
        "completeness_requirement",
    }
    unsupported = sorted(
        str(key)
        for key, value in arguments.items()
        if value is not None and key not in allowed
    )
    if unsupported:
        raise ValueError(
            "unsupported Microsoft user search arguments: " + ", ".join(unsupported)
        )

    page_size = arguments.get("page_size", 10)
    if isinstance(page_size, bool):
        raise ValueError("page_size must be between 1 and 25")
    try:
        page_size = int(page_size)
    except (TypeError, ValueError) as error:
        raise ValueError("page_size must be between 1 and 25") from error
    if not 1 <= page_size <= _MAX_MICROSOFT_USER_RECORDS:
        raise ValueError("page_size must be between 1 and 25")

    selector = selectors[0]
    return {
        selector: str(arguments[selector]).strip(),
        "page_size": page_size,
    }


def adapt_provider_read_arguments(
    *,
    provider_id: str,
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    if provider_id == IT_GLUE_PROVIDER:
        return adapt_it_glue_arguments(capability_name, arguments)
    if provider_id == AUTOTASK_PROVIDER:
        return adapt_autotask_arguments(capability_name, arguments)
    if provider_id == MICROSOFT_GRAPH_PROVIDER:
        return adapt_microsoft_graph_arguments(capability_name, arguments)
    raise ValueError(f"No provider-read argument adapter for provider: {provider_id}")


def _minimize_it_glue_search_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep record evidence and bounded pagination facts, not provider filter catalogs.

    IT Glue may include response metadata describing available filters or permitted
    values. Those details are useful to provider tooling but are not needed for a
    technician-facing evidence result and can be much larger than the actual records.
    Canonical search output therefore preserves the JSON:API records, optional
    included records, and only small pagination metadata. Provider links and all other
    metadata are deliberately omitted from the returned evidence package.
    """

    minimized: dict[str, Any] = {}
    if "data" in payload:
        minimized["data"] = payload["data"]

    included = payload.get("included")
    if isinstance(included, list):
        minimized["included"] = included

    meta = payload.get("meta")
    if isinstance(meta, Mapping):
        pagination = {
            str(key): value
            for key, value in meta.items()
            if str(key) in _IT_GLUE_SAFE_PAGINATION_META_KEYS
        }
        if pagination:
            minimized["meta"] = pagination

    return minimized


def _minimize_provider_read_output(
    *,
    provider_id: str,
    capability_name: str,
    invocation: InvocationResult,
) -> InvocationResult:
    if provider_id != IT_GLUE_PROVIDER or capability_name not in _IT_GLUE_SEARCH_CAPABILITIES:
        return invocation

    output = dict(invocation.output)
    payload = output.get("data")
    if not isinstance(payload, Mapping):
        return invocation

    output["data"] = _minimize_it_glue_search_payload(payload)
    return InvocationResult(
        output=output,
        artifact_references=invocation.artifact_references,
        attempts=invocation.attempts,
        telemetry=invocation.telemetry,
        information_authorization=invocation.information_authorization,
    )


def _normalized_human_name(value: object) -> str:
    return " ".join(
        token
        for token in re.split(r"[^a-z0-9]+", str(value or "").strip().casefold())
        if token
    )


def _it_glue_record_name(record: object) -> str:
    if not isinstance(record, Mapping):
        return ""
    attrs = record.get("attributes")
    if not isinstance(attrs, Mapping):
        return ""
    return str(attrs.get("name") or "").strip()


def _it_glue_records(invocation: InvocationResult) -> list[object]:
    payload = invocation.output.get("data")
    if not isinstance(payload, Mapping):
        return []
    records = payload.get("data")
    return list(records) if isinstance(records, list) else []


def _bounded_name_matches(records: list[object], requested_name: str) -> list[object]:
    query = _normalized_human_name(requested_name)
    if not query:
        return []
    exact = [
        item for item in records
        if _normalized_human_name(_it_glue_record_name(item)) == query
    ]
    if exact:
        return exact

    query_tokens = tuple(query.split())
    broader: list[object] = []
    for item in records:
        candidate = _normalized_human_name(_it_glue_record_name(item))
        if not candidate:
            continue
        tokens = tuple(candidate.split())
        if (
            tokens[: len(query_tokens)] == query_tokens
            or query_tokens[: len(tokens)] == tokens
            or f" {query} " in f" {candidate} "
        ):
            broader.append(item)
    return broader


def _replace_it_glue_records(
    invocation: InvocationResult,
    records: list[object],
) -> InvocationResult:
    output = dict(invocation.output)
    payload = output.get("data")
    if not isinstance(payload, Mapping):
        return invocation
    minimized = dict(payload)
    minimized["data"] = records
    output["data"] = minimized
    return InvocationResult(
        output=output,
        artifact_references=invocation.artifact_references,
        attempts=invocation.attempts,
        telemetry=invocation.telemetry,
        information_authorization=invocation.information_authorization,
    )


def _result_count(invocation: InvocationResult) -> int | None:
    payload = invocation.output.get("data")
    if isinstance(payload, Mapping):
        for key in ("items", "value", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return len(rows)
        for key in ("count", "queryCount", "totalCount"):
            value = payload.get(key)
            if isinstance(value, bool):
                continue
            try:
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                pass
    if isinstance(payload, list):
        return len(payload)
    return None


def _pagination_count(invocation: InvocationResult) -> int:
    payload = invocation.output.get("data")
    if not isinstance(payload, Mapping):
        return 0
    pagination = payload.get("jasonPagination")
    if isinstance(pagination, Mapping):
        try:
            return max(1, int(pagination.get("pagesFetched") or 1))
        except (TypeError, ValueError):
            return 1
    meta = payload.get("meta")
    if isinstance(meta, Mapping):
        for key in ("current-page", "current_page"):
            try:
                if meta.get(key) is not None:
                    return max(1, int(meta[key]))
            except (TypeError, ValueError):
                pass
    return 1


def _with_reflection_telemetry(
    invocation: InvocationResult,
    *,
    provider_id: str,
    capability_name: str,
    normalized_intent: str,
    selector_strategy: str,
    requested_result_scope: str,
    result_count: int | None,
    candidate_count: int | None,
    provider_call_count: int,
    pagination_count: int,
    fallback_count: int,
    search_strategies: tuple[str, ...],
    search_result_counts: tuple[int, ...],
    warning_codes: tuple[str, ...] = (),
) -> InvocationResult:
    base = invocation.telemetry or InvocationTelemetry()
    telemetry = replace(
        base,
        reflection_normalized_intent=normalized_intent,
        reflection_selector_strategy=selector_strategy,
        reflection_requested_result_scope=requested_result_scope,
        reflection_result_count=result_count,
        reflection_candidate_count=candidate_count,
        reflection_provider_call_count=provider_call_count,
        reflection_pagination_count=pagination_count,
        reflection_fallback_count=fallback_count,
        reflection_evidence_item_count=result_count or 0,
        reflection_search_strategies=search_strategies,
        reflection_search_result_counts=search_result_counts,
        reflection_warning_codes=warning_codes,
    )
    return InvocationResult(
        output=invocation.output,
        artifact_references=invocation.artifact_references,
        attempts=invocation.attempts,
        telemetry=telemetry,
        information_authorization=invocation.information_authorization,
    )


@dataclass(frozen=True, slots=True)
class GovernedProviderReadConnectorInvoker:
    """Adapt canonical reads and emit bounded REFLECT-001 execution telemetry."""

    delegate: GovernedConnectorCapabilityInvoker

    @staticmethod
    def _enforce_client_selector_binding(request: OrchestrationRequest, capability_name: str) -> None:
        scoped = {
            SERVICE_CONTRACT_SEARCH, SERVICE_CONTRACT_READ,
            SERVICE_TICKET_ATTACHMENT_SEARCH, SERVICE_TICKET_ATTACHMENT_READ,
            SERVICE_TICKET_ATTACHMENT_CONTENT_READ,
        }
        if capability_name not in scoped:
            return
        client_id = str(request.client_id or "").strip()
        company_id = request.arguments.get("company_id")
        if not client_id:
            raise PermissionError("client context is required for company-scoped reads")
        if company_id is None or isinstance(company_id, bool):
            raise PermissionError("company_id is required for company-scoped reads")
        try:
            canonical_company = str(int(company_id))
        except (TypeError, ValueError) as exc:
            raise PermissionError("company_id must be a non-negative Autotask company id") from exc
        if int(canonical_company) < 0:
            raise PermissionError("company_id must be a non-negative Autotask company id")
        if client_id != canonical_company:
            raise PermissionError("company selector does not match governed client context")

    def _invoke_it_glue_organization_search(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        requested_name = str(request.arguments.get("name") or "").strip()
        if not requested_name:
            raise ValueError("name is required for bounded organization resolution")

        exact_adapted = adapt_it_glue_arguments(
            DOCUMENTATION_ORGANIZATION_SEARCH,
            request.arguments,
        )
        exact_raw = self.delegate.invoke(
            request=replace(request, arguments=exact_adapted),
            resolution=resolution,
        )
        exact_invocation = _minimize_provider_read_output(
            provider_id=IT_GLUE_PROVIDER,
            capability_name=DOCUMENTATION_ORGANIZATION_SEARCH,
            invocation=exact_raw,
        )
        first_records = _it_glue_records(exact_invocation)
        exact_matches = [
            item for item in first_records
            if _normalized_human_name(_it_glue_record_name(item))
            == _normalized_human_name(requested_name)
        ]
        if len(exact_matches) > 1:
            raise ValueError("IT_GLUE_ORGANIZATION_SEARCH_AMBIGUOUS")
        if len(exact_matches) == 1:
            resolved = _replace_it_glue_records(exact_invocation, exact_matches)
            return _with_reflection_telemetry(
                resolved,
                provider_id=IT_GLUE_PROVIDER,
                capability_name=DOCUMENTATION_ORGANIZATION_SEARCH,
                normalized_intent="organization_search",
                selector_strategy="bounded_name_resolution",
                requested_result_scope="single",
                result_count=1,
                candidate_count=len(first_records),
                provider_call_count=1,
                pagination_count=1,
                fallback_count=0,
                search_strategies=("exact",),
                search_result_counts=(1,),
            )

        local_broader = _bounded_name_matches(first_records, requested_name)
        provider_calls = 1
        if not local_broader:
            broad_arguments = dict(request.arguments)
            broad_arguments.pop("name", None)
            broad_arguments["page_size"] = _MAX_IT_GLUE_PAGE_SIZE
            broad_adapted = adapt_it_glue_arguments(
                DOCUMENTATION_ORGANIZATION_SEARCH,
                broad_arguments,
            )
            broad_raw = self.delegate.invoke(
                request=replace(request, arguments=broad_adapted),
                resolution=resolution,
            )
            broad_invocation = _minimize_provider_read_output(
                provider_id=IT_GLUE_PROVIDER,
                capability_name=DOCUMENTATION_ORGANIZATION_SEARCH,
                invocation=broad_raw,
            )
            provider_calls += 1
            local_broader = _bounded_name_matches(
                _it_glue_records(broad_invocation), requested_name
            )
            base = broad_invocation
        else:
            base = exact_invocation

        if len(local_broader) > 1:
            raise ValueError("IT_GLUE_ORGANIZATION_SEARCH_AMBIGUOUS")
        resolved = _replace_it_glue_records(base, local_broader)
        return _with_reflection_telemetry(
            resolved,
            provider_id=IT_GLUE_PROVIDER,
            capability_name=DOCUMENTATION_ORGANIZATION_SEARCH,
            normalized_intent="organization_search",
            selector_strategy="bounded_name_resolution",
            requested_result_scope="single",
            result_count=len(local_broader),
            candidate_count=len(local_broader),
            provider_call_count=provider_calls,
            pagination_count=1,
            fallback_count=1,
            search_strategies=("exact", "normalized_prefix_contains"),
            search_result_counts=(0, len(local_broader)),
            warning_codes=("bounded_search_broadening_used",),
        )

    def _generic_reflection_telemetry(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
        provider_id: str,
        invocation: InvocationResult,
    ) -> InvocationResult:
        count = _result_count(invocation)
        pages = _pagination_count(invocation)
        capability = resolution.capability_name
        search_capability = capability.endswith(".search") or capability.endswith(".count")
        scope = "bounded" if search_capability else "single"
        normalized_intent = capability.replace(".", "_")
        selector_strategy = "canonical_provider_filter" if search_capability else "exact_resource_read"
        strategy = "provider_filter_pushdown" if search_capability else "exact_resource_id"
        provider_calls = 1
        warnings: tuple[str, ...] = ()

        if provider_id == AUTOTASK_PROVIDER:
            # Zone discovery plus the requested provider read. Continuation pages
            # add one call each beyond the first data page.
            provider_calls = 1 + max(1, pages)
            status = request.arguments.get("status")
            if (
                capability in {SERVICE_TICKET_SEARCH, SERVICE_TICKET_COUNT}
                and isinstance(status, str)
                and status.strip().casefold() in {"open", "unresolved"}
            ):
                normalized_intent = "open_ticket_search"
                selector_strategy = "company_open_status_pushdown"
                strategy = "open_status_pushdown"
                provider_calls += 1  # live status metadata resolution
                warnings = ("terminal_statuses_resolved_from_live_metadata",)

        return _with_reflection_telemetry(
            invocation,
            provider_id=provider_id,
            capability_name=capability,
            normalized_intent=normalized_intent,
            selector_strategy=selector_strategy,
            requested_result_scope=scope,
            result_count=count,
            candidate_count=count,
            provider_call_count=provider_calls,
            pagination_count=pages,
            fallback_count=0,
            search_strategies=(strategy,),
            search_result_counts=((count or 0),),
            warning_codes=warnings,
        )

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        provider_id = (resolution.selected_provider_id or "").strip()
        if not provider_id:
            raise PermissionError("resolved provider is required before argument adaptation")

        self._enforce_client_selector_binding(request, resolution.capability_name)
        if (
            provider_id == IT_GLUE_PROVIDER
            and resolution.capability_name == DOCUMENTATION_ORGANIZATION_SEARCH
            and str(request.arguments.get("name") or "").strip()
        ):
            return self._invoke_it_glue_organization_search(
                request=request,
                resolution=resolution,
            )

        adapted = adapt_provider_read_arguments(
            provider_id=provider_id,
            capability_name=resolution.capability_name,
            arguments=request.arguments,
        )
        invocation = self.delegate.invoke(
            request=replace(request, arguments=adapted),
            resolution=resolution,
        )
        minimized = _minimize_provider_read_output(
            provider_id=provider_id,
            capability_name=resolution.capability_name,
            invocation=invocation,
        )
        return self._generic_reflection_telemetry(
            request=request,
            resolution=resolution,
            provider_id=provider_id,
            invocation=minimized,
        )
