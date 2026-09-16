from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Mapping


DATTO_EXECUTION_COMPONENTS_JSON_ENV = (
    "JASON_DATTO_COMPONENT_EXECUTION_COMPONENTS_JSON"
)
DATTO_EXECUTION_COMPONENT_UID_ENV = (
    "JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_UID"
)
DATTO_EXECUTION_COMPONENT_NAME_ENV = (
    "JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_NAME"
)

DATTO_APPROVAL_MODE_STANDING_SAFE = "standing_safe"
DATTO_APPROVAL_MODE_PER_RUN = "per_run"
_VALID_APPROVAL_MODES = frozenset(
    {
        DATTO_APPROVAL_MODE_STANDING_SAFE,
        DATTO_APPROVAL_MODE_PER_RUN,
    }
)

_MAX_COMPONENTS = 16
_MAX_UID_LENGTH = 128
_MAX_NAME_LENGTH = 255
_FORBIDDEN_SCOPE_VALUES = frozenset(
    {
        "*",
        "all",
        "all components",
        "global",
        "unrestricted",
    }
)

# Source-controlled canonical identity overrides are deliberately exact and
# narrow. They repair stale server configuration only for a component whose
# current Datto UID has already been independently verified through complete
# governed catalog discovery. Caller-supplied names or UIDs never add entries
# to this mapping and therefore cannot broaden execution authority.
_CANONICAL_UID_OVERRIDES = {
    "check service detail & diagnostic [win] aot ver 12122025-1": (
        "2b49d490-bcae-4825-b31e-c4f1be881ae5"
    ),
}


@dataclass(frozen=True, slots=True)
class DattoApprovedComponent:
    uid: str
    name: str
    approval_mode: str = DATTO_APPROVAL_MODE_PER_RUN

    @property
    def requires_explicit_approval(self) -> bool:
        return self.approval_mode == DATTO_APPROVAL_MODE_PER_RUN


class DattoComponentScopeError(ValueError):
    pass


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _normalize_component(
    uid: object,
    name: object,
    approval_mode: object = DATTO_APPROVAL_MODE_PER_RUN,
) -> DattoApprovedComponent:
    normalized_uid = str(uid or "").strip()
    normalized_name = str(name or "").strip()
    normalized_approval_mode = str(approval_mode or "").strip().casefold()

    if not normalized_uid or not normalized_name:
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INCOMPLETE"
        )

    canonical_override = _CANONICAL_UID_OVERRIDES.get(
        normalized_name.casefold()
    )
    if canonical_override:
        normalized_uid = canonical_override

    if (
        len(normalized_uid) > _MAX_UID_LENGTH
        or len(normalized_name) > _MAX_NAME_LENGTH
    ):
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"
        )

    if (
        normalized_uid.casefold() in _FORBIDDEN_SCOPE_VALUES
        or normalized_name.casefold() in _FORBIDDEN_SCOPE_VALUES
    ):
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"
        )

    if normalized_approval_mode not in _VALID_APPROVAL_MODES:
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_EXECUTION_APPROVAL_MODE_INVALID"
        )

    return DattoApprovedComponent(
        uid=normalized_uid,
        name=normalized_name,
        approval_mode=normalized_approval_mode,
    )


def configured_datto_components() -> tuple[DattoApprovedComponent, ...]:
    """Return the exact server-controlled component identities.

    The JSON form is authoritative when present. Legacy scalar UID/name
    variables remain supported as a one-component fallback so existing
    deployments fail closed rather than requiring an in-place migration.
    """

    raw_json = _env(DATTO_EXECUTION_COMPONENTS_JSON_ENV)

    if raw_json:
        try:
            payload = json.loads(raw_json)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise DattoComponentScopeError(
                "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"
            ) from error

        if (
            not isinstance(payload, list)
            or not payload
            or len(payload) > _MAX_COMPONENTS
        ):
            raise DattoComponentScopeError(
                "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"
            )

        components: list[DattoApprovedComponent] = []

        for item in payload:
            if not isinstance(item, Mapping):
                raise DattoComponentScopeError(
                    "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"
                )

            if set(item) != {"uid", "name", "approval_mode"}:
                raise DattoComponentScopeError(
                    "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"
                )

            components.append(
                _normalize_component(
                    item.get("uid"),
                    item.get("name"),
                    item.get("approval_mode"),
                )
            )

        uids = [item.uid for item in components]
        names = [item.name.casefold() for item in components]

        if len(set(uids)) != len(uids) or len(set(names)) != len(names):
            raise DattoComponentScopeError(
                "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_AMBIGUOUS"
            )

        return tuple(components)

    legacy_uid = _env(DATTO_EXECUTION_COMPONENT_UID_ENV)
    legacy_name = _env(DATTO_EXECUTION_COMPONENT_NAME_ENV)

    if not legacy_uid and not legacy_name:
        return ()

    return (
        _normalize_component(legacy_uid, legacy_name),
    )


def resolve_datto_component(
    components: tuple[DattoApprovedComponent, ...],
    *,
    component_uid: object = None,
    component_name: object = None,
) -> DattoApprovedComponent:
    """Resolve exactly one approved UID/name pair and fail closed otherwise."""

    uid = str(component_uid or "").strip()
    name = str(component_name or "").strip()

    if not uid and not name:
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_IDENTITY_REQUIRED"
        )

    matches = [
        item
        for item in components
        if (not uid or item.uid == uid)
        and (not name or item.name.casefold() == name.casefold())
    ]

    if len(matches) == 1:
        return matches[0]

    if name and not uid:
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_NAME_MISMATCH"
        )

    raise DattoComponentScopeError(
        "DATTO_COMPONENT_IDENTITY_MISMATCH"
    )
