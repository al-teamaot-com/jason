"""Source-only, non-executing plan for one AOT-MSA native ServiceBundleService link.

This module NEVER issues provider requests, grants authority, or registers a
write capability. Provider mutation and billing-price verification require a
separately governed, approved release and exact-action authorization.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

ENTITY_PATH = "/V1.0/ServiceBundleServices"
PROVIDER_OPERATION = "autotask.service.bundle.membership.create"
MANAGED_SERVICES_BILLING_CODE = 29682901
LEGACY_BUNDLE_IDS = frozenset({1, 2, 3, 4})


class BundleMembershipPlanDenied(PermissionError):
    """A proposal lacks exact, independently checkable prerequisites."""


def _deny(reason: str) -> None:
    raise BundleMembershipPlanDenied("AOT_MSA_BUNDLE_MEMBER_" + reason)


def _positive_id(value: Any, field: str) -> int:
    if type(value) is not int or value <= 0:
        _deny(field + "_INVALID")
    return value


def _zero_price(value: Any) -> None:
    if isinstance(value, bool) or value is None:
        _deny("BUNDLE_PRICE_UNVERIFIED")
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BundleMembershipPlanDenied(
            "AOT_MSA_BUNDLE_MEMBER_BUNDLE_PRICE_UNVERIFIED"
        ) from exc
    if not price.is_finite() or price != 0:
        _deny("BUNDLE_FINANCIAL_VALUE_NOT_ZERO")


def _evidence(value: Any, kind: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        _deny(kind + "_EVIDENCE_MISSING")
    return value.strip()


def plan_inactive_bundle_membership(
    *,
    bundle: Mapping[str, Any],
    service: Mapping[str, Any],
    existing_links: Sequence[Mapping[str, Any]],
    native_sum_pricing_observed: bool | None,
    bundle_read_evidence: str,
    service_read_evidence: str,
    links_read_evidence: str,
    pricing_setting_evidence: str,
) -> dict[str, Any]:
    """Prepare a readback-bound proposal; never mark it executable.

    The caller MUST independently verify all provider evidence again within
    the future governed mutation transaction; strings here are descriptions,
    not trusted authority or proof that external records were read.
    """
    if not isinstance(bundle, Mapping) or not isinstance(service, Mapping):
        _deny("SOURCE_RECORDS_REQUIRED")
    if isinstance(existing_links, (str, bytes)) or not isinstance(existing_links, Sequence):
        _deny("COMPLETE_LINK_SET_REQUIRED")
    bundle_id = _positive_id(bundle.get("id"), "BUNDLE_ID")
    service_id = _positive_id(service.get("id"), "SERVICE_ID")
    if bundle_id in LEGACY_BUNDLE_IDS:
        _deny("LEGACY_BUNDLE_PROTECTED")
    if not str(bundle.get("name", "")).startswith("AOT-MSA"):
        _deny("NON_AOT_MSA_BUNDLE_DENIED")
    if bundle.get("isActive") is not False:
        _deny("ACTIVE_BUNDLE_DENIED")
    if service.get("isActive") is not True:
        _deny("SERVICE_NOT_VERIFIED_ACTIVE")
    if bundle.get("billingCodeID") != MANAGED_SERVICES_BILLING_CODE:
        _deny("BILLING_CODE_UNVERIFIED")
    _zero_price(bundle.get("unitPrice"))
    if native_sum_pricing_observed is not False:
        _deny("NATIVE_SUM_PRICING_UNKNOWN_OR_PRICE_MUTATING")

    references = {
        "bundle": _evidence(bundle_read_evidence, "BUNDLE"),
        "service": _evidence(service_read_evidence, "SERVICE"),
        "membership": _evidence(links_read_evidence, "MEMBERSHIP"),
        "native_sum_pricing": _evidence(pricing_setting_evidence, "PRICING_SETTING"),
    }
    seen: set[int] = set()
    for item in existing_links:
        if not isinstance(item, Mapping):
            _deny("MALFORMED_LINK")
        if _positive_id(item.get("serviceBundleID"), "LINK_BUNDLE_ID") != bundle_id:
            _deny("CROSS_BUNDLE_LINK_SET")
        _positive_id(item.get("id"), "LINK_ID")
        current_id = _positive_id(item.get("serviceID"), "LINK_SERVICE_ID")
        if current_id in seen:
            _deny("AMBIGUOUS_DUPLICATE_EXISTING_LINKS")
        seen.add(current_id)
    if service_id in seen:
        _deny("MEMBERSHIP_ALREADY_EXISTS")

    return {
        "schema_version": "1.0",
        "status": "SOURCE_ONLY_NOT_AUTHORIZED",
        "provider": "Autotask",
        "operation": PROVIDER_OPERATION,
        "method": "POST",
        "path": ENTITY_PATH,
        "payload": {"serviceBundleID": bundle_id, "serviceID": service_id},
        "source_evidence_descriptions_only": references,
        "expected_parent_unit_price": "0.00",
        "bundle_price_must_be_reverified_after_create": True,
        "authenticated_exact_action_approval_required": True,
        "dedicated_jason_api_identity_required": True,
        "prewrite_duplicate_and_price_recheck_required": True,
        "automatic_retry_permitted": False,
        "customer_contract_mutation_permitted": False,
        "execution_authorized": False,
    }
