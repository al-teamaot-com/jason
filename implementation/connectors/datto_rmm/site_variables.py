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


def _variable_collection(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    current: Any = payload
    for _ in range(5):
        if isinstance(current, list):
            return [item for item in current if isinstance(item, Mapping)]
        if not isinstance(current, Mapping):
            break
        for key in ("variables", "items"):
            candidate = current.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, Mapping)]
        for key in ("data", "provider_data"):
            candidate = current.get(key)
            if isinstance(candidate, (Mapping, list)):
                current = candidate
                break
        else:
            break
    raise ValueError("Unexpected Datto RMM site-variable payload shape.")


def sanitize_site_variables_for_principal(
    payload: Mapping[str, Any],
    *,
    permission_mode: str,
    requested_name: str | None = None,
) -> Mapping[str, Any]:
    """Return a requester-safe view without weakening Jason's internal use.

    Administrators may receive variable names and values. Non-admin callers may
    ask whether one exact named variable is configured, but cannot enumerate
    variable names or receive values.
    """

    variables = _variable_collection(payload)
    disclose = permission_mode in ADMIN_PERMISSION_MODES
    exact_name = str(requested_name or "").strip()
    if disclose:
        selected = variables
        if exact_name:
            selected = [
                raw
                for raw in variables
                if str(raw.get("name") or raw.get("variableName") or "").strip().casefold()
                == exact_name.casefold()
            ]
        result = []
        for raw in selected:
            name = str(raw.get("name") or raw.get("variableName") or "").strip()
            result.append(
                {
                    "name": name,
                    "configured": ("value" in raw and raw.get("value") not in (None, "")),
                    "value": raw.get("value"),
                }
            )
        return {
            "variables": result,
            "name_disclosure": "allowed",
            "value_disclosure": "allowed",
        }

    response: dict[str, Any] = {
        "name_disclosure": "blocked",
        "value_disclosure": "blocked",
        "variable_count": len(variables),
    }
    if exact_name:
        match = next(
            (
                raw
                for raw in variables
                if str(raw.get("name") or raw.get("variableName") or "").strip().casefold()
                == exact_name.casefold()
            ),
            None,
        )
        response["requested_variable"] = {
            "requested_name": exact_name,
            "present": match is not None,
            "configured": bool(
                match is not None
                and "value" in match
                and match.get("value") not in (None, "")
            ),
        }
    return response


def require_site_variable_value_disclosure(permission_mode: str) -> None:
    if permission_mode not in ADMIN_PERMISSION_MODES:
        raise ConnectorAuthorizationError(
            "Site-variable values are restricted to administrators."
        )
