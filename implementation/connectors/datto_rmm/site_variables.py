from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from connectors.core.contracts import ConnectorAuthorizationError


ADMIN_PERMISSION_MODES = frozenset({"administer"})


@dataclass(frozen=True, slots=True)
class SiteVariableView:
    name: str
    configured: bool
    value: Any | None = None


def sanitize_site_variables_for_principal(
    payload: Mapping[str, Any],
    *,
    permission_mode: str,
) -> Mapping[str, Any]:
    """Return a governed site-variable view.

    Non-admin callers may learn whether a variable exists/configured, but may not
    receive the variable value. Admin callers may receive values. This function
    is intentionally independent of the provider shape beyond common Datto
    variable field names so it can be reused at the presentation boundary.
    """

    variables = payload.get("variables")
    if variables is None:
        variables = payload.get("data")
    if variables is None and isinstance(payload, Mapping):
        variables = payload.get("items")
    if variables is None:
        variables = []

    if not isinstance(variables, list):
        raise ValueError("Unexpected Datto RMM site-variable payload shape.")

    disclose_values = permission_mode in ADMIN_PERMISSION_MODES
    result: list[dict[str, Any]] = []
    for raw in variables:
        if not isinstance(raw, Mapping):
            continue
        name = str(raw.get("name") or raw.get("variableName") or "").strip()
        value_present = "value" in raw and raw.get("value") not in (None, "")
        item: dict[str, Any] = {
            "name": name,
            "configured": bool(value_present),
        }
        if disclose_values:
            item["value"] = raw.get("value")
        result.append(item)

    return {
        "variables": result,
        "value_disclosure": "allowed" if disclose_values else "blocked",
    }


def require_site_variable_value_disclosure(permission_mode: str) -> None:
    if permission_mode not in ADMIN_PERMISSION_MODES:
        raise ConnectorAuthorizationError(
            "Site-variable values are restricted to administrators."
        )
