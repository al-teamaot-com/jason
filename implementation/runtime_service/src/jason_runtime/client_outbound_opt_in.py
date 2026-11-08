from __future__ import annotations

import os
from typing import Any, Mapping

# Company-controlled opt-in is separate from playbook/template authority.
# This module is deliberately off until the field is provisioned and the
# complete governed release has passed its independent activation gates.
JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE_ENV = "JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE"
JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE = "autotask-company-udf-v1"
CLIENT_OUTBOUND_OPT_IN_FIELD = "enable_jason_outbound_comm"


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
