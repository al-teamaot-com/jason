from __future__ import annotations

import os
from typing import Any, Mapping

# Company-controlled opt-in is separate from playbook/template authority.
# This module is deliberately off until the field is provisioned and the
# complete governed release has passed its independent activation gates.
JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE_ENV = "JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE"
JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE = "autotask-company-udf-v1"
CLIENT_OUTBOUND_OPT_IN_FIELD = "enable_jason_outbound_comm"

# Owner-approved bounded XYZ test-client exception: any genuine XYZ ticket,
# only the designated test inbox, and only if the Company UDF is absent.
# An explicit False or malformed UDF always takes precedence.
JASON_XYZ_TEST_CONSENT_PROFILE_ENV = "JASON_XYZ_TEST_CONSENT_PROFILE"
JASON_XYZ_TEST_CONSENT_PROFILE = "xyz-test-company-ticket-sandbox-v1"


class ClientOutboundOptInDenied(PermissionError):
    """Company-level client communication authorization failed closed."""


def company_opt_in_gate_enabled() -> bool:
    profile = os.getenv(JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE_ENV, "").strip()
    if not profile:
        return False
    if profile != JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE:
        raise ClientOutboundOptInDenied("CLIENT_OUTBOUND_OPT_IN_PROFILE_INVALID")
    return True


def company_outbound_opted_in(company: Mapping[str, Any], *, expected_id: int) -> bool:
    """Only an exact matching, explicit Company UDF True authorizes routine send.

    Missing, null, duplicate, malformed, non-true and cross-company data
    all return False. Never borrow a contact/ticket/client UDF as authority.
    """
    if not isinstance(company, Mapping) or isinstance(expected_id, bool):
        return False
    try:
        company_id = int(company.get("id"))
    except (TypeError, ValueError):
        return False
    if company_id != expected_id or expected_id < 1:
        return False
    fields = company.get("userDefinedFields")
    if not isinstance(fields, list):
        return False
    values = [
        field.get("value")
        for field in fields
        if isinstance(field, Mapping)
        and field.get("name") == CLIENT_OUTBOUND_OPT_IN_FIELD
    ]
    return len(values) == 1 and (
        values[0] is True
        or isinstance(values[0], str) and values[0].strip().casefold() == "true"
    )


def require_company_outbound_opt_in(company: Mapping[str, Any], *, expected_id: int) -> None:
    if not company_outbound_opted_in(company, expected_id=expected_id):
        raise ClientOutboundOptInDenied("CLIENT_OUTBOUND_COMPANY_NOT_OPTED_IN")


def xyz_test_consent_exception_enabled() -> bool:
    """Require explicit, independently named test activation AND the UDF gate."""
    raw = os.getenv(JASON_XYZ_TEST_CONSENT_PROFILE_ENV, "").strip()
    if not raw:
        return False
    if raw != JASON_XYZ_TEST_CONSENT_PROFILE:
        raise ClientOutboundOptInDenied("CLIENT_OUTBOUND_XYZ_TEST_PROFILE_INVALID")
    if not company_opt_in_gate_enabled():
        raise ClientOutboundOptInDenied("CLIENT_OUTBOUND_XYZ_TEST_REQUIRES_UDF_GATE")
    return True


def company_udf_not_yet_provisioned(
    company: Mapping[str, Any], *, expected_id: int
) -> bool:
    """Temporary test may apply only to an *absent* field on the right Company.

    Explicit False, null, empty, malformed UDF, duplicate, or a different
    company's UDF is not absent for consent purposes.
    """
    if (
        not isinstance(company, Mapping)
        or type(expected_id) is not int
        or type(company.get("id")) is not int
        or company["id"] != expected_id
        or expected_id < 1
    ):
        return False
    fields = company.get("userDefinedFields")
    if not isinstance(fields, list):
        return False
    for field in fields:
        if not isinstance(field, Mapping):
            return False
        if field.get("name") == CLIENT_OUTBOUND_OPT_IN_FIELD:
            return False
    return True
