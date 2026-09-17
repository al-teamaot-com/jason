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
DATTO_EXECUTION_ALLOW_UNCLASSIFIED_PER_RUN_ENV = (
    "JASON_DATTO_COMPONENT_EXECUTION_ALLOW_UNCLASSIFIED_PER_RUN"
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
# to this mapping and therefore cannot broaden standing-safe authority.
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


def _unclassified_per_run_enabled() -> bool:
    return _env(
        DATTO_EXECUTION_ALLOW_UNCLASSIFIED_PER_RUN_ENV
    ).casefold() in {"1", "true", "yes", "on"}


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
    """Return the exact server-controlled standing-safe/per-run identities.

    The JSON form is authoritative when present. Legacy scalar UID/name
    variables remain supported as a one-component fallback so existing
    deployments fail closed rather than requiring an in-place migration.

    When the separate unclassified-per-run switch is enabled, components not
    present in this tuple may be accepted only as per-run identities after the
    caller supplies both durable Datto UID and display name. That fallback can
    never create standing-safe authority or override a configured identity.
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
    catalog_verified: bool = False,
) -> DattoApprovedComponent:
    """Resolve one component identity without allowing caller risk upgrades.

    Configured identities retain their exact server-side approval mode. When
    explicitly enabled, a UID/name pair that matches no configured identity may
    fall back to ``per_run``. The fallback is intentionally impossible for a
    partial collision with configured UID or name, preventing a caller from
    altering or downgrading a standing-safe identity.
    """

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

    uid_collision = bool(uid) and any(
        item.uid == uid for item in components
    )
    name_collision = bool(name) and any(
        item.name.casefold() == name.casefold()
        for item in components
    )

    if catalog_verified and uid and name:
        # A live complete-catalog lookup is the authoritative provider
        # identity. Static configured components classify risk; they do not
        # override a newer Datto UID/name pair.
        #
        # Preserve standing-safe/per-run classification when either durable
        # side of a configured identity still corresponds to the live record.
        related = [
            item
            for item in components
            if (
                item.uid == uid
                or item.name.casefold() == name.casefold()
            )
        ]

        approval_modes = {
            item.approval_mode
            for item in related
        }

        if len(approval_modes) > 1:
            raise DattoComponentScopeError(
                "DATTO_COMPONENT_CLASSIFICATION_AMBIGUOUS"
            )

        approval_mode = (
            next(iter(approval_modes))
            if approval_modes
            else DATTO_APPROVAL_MODE_PER_RUN
        )

        # A catalog-verified component not already classified standing-safe
        # remains per-run. Live discovery can never manufacture standing-safe
        # authority.
        return _normalize_component(
            uid,
            name,
            approval_mode,
        )

    if uid_collision or name_collision:
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_IDENTITY_MISMATCH"
        )

    if (
        uid
        and name
        and _unclassified_per_run_enabled()
    ):
        return _normalize_component(
            uid,
            name,
            DATTO_APPROVAL_MODE_PER_RUN,
        )

    if name and not uid:
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_NAME_MISMATCH"
        )

    raise DattoComponentScopeError(
        "DATTO_COMPONENT_IDENTITY_MISMATCH"
    )
