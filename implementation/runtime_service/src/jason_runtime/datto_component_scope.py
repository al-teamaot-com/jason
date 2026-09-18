from __future__ import annotations

import json
import os
import re
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

# Arbitrary shell/code execution may never inherit standing-safe authority.
# Either durable identity side is sufficient to force per-run approval so
# a stale configured UID or later display-name change cannot weaken policy.
DATTO_AD_HOC_POWERSHELL_UID = (
    "8a1c153c-feee-41c5-9c9b-58a48e0214fe"
)
DATTO_AD_HOC_POWERSHELL_NAME = (
    "Run Ad Hoc Command (PowerShell 2-5) [WIN]"
)

_FORCED_PER_RUN_COMPONENT_UIDS = frozenset(
    {
        DATTO_AD_HOC_POWERSHELL_UID,
    }
)

_FORCED_PER_RUN_COMPONENT_NAMES = frozenset(
    {
        DATTO_AD_HOC_POWERSHELL_NAME.casefold(),
    }
)

# Standing-safe PowerShell is intentionally narrow. These cmdlets are
# operational reads whose normal behavior does not modify endpoint state.
# Generic filesystem, registry, event-log, WMI/CIM, shell and executable
# access remains per-run because "read-looking" input can expose sensitive
# data, cross scope boundaries, or have provider-specific side effects.
_READ_ONLY_POWERSHELL_PRIMARY = frozenset(
    {
        "get-acl",
        "get-authenticodesignature",
        "get-computerinfo",
        "get-counter",
        "get-date",
        "get-disk",
        "get-dnsclient",
        "get-dnsclientserveraddress",
        "get-filehash",
        "get-hotfix",
        "get-localgroup",
        "get-localgroupmember",
        "get-localuser",
        "get-mpcomputerstatus",
        "get-netadapter",
        "get-netfirewallprofile",
        "get-netfirewallrule",
        "get-netipaddress",
        "get-netipconfiguration",
        "get-netroute",
        "get-nettcpconnection",
        "get-netudpendpoint",
        "get-partition",
        "get-physicaldisk",
        "get-pnpdevice",
        "get-process",
        "get-scheduledtask",
        "get-scheduledtaskinfo",
        "get-service",
        "get-smbconnection",
        "get-timezone",
        "get-volume",
        "resolve-dnsname",
        "test-netconnection",
        "test-path",
    }
)

_READ_ONLY_POWERSHELL_PIPELINE = frozenset(
    {
        "convertto-json",
        "format-list",
        "format-table",
        "group-object",
        "measure-object",
        "out-string",
        "select-object",
        "sort-object",
        "where-object",
    }
)

_POWERSHELL_APPROVAL_REQUIRED_REASON = (
    "DATTO_POWERSHELL_COMMAND_APPROVAL_REQUIRED"
)
_POWERSHELL_READ_ONLY_REASON = (
    "DATTO_POWERSHELL_READ_ONLY_COMMAND"
)


@dataclass(frozen=True, slots=True)
class DattoApprovedComponent:
    uid: str
    name: str
    approval_mode: str = DATTO_APPROVAL_MODE_PER_RUN

    @property
    def requires_explicit_approval(self) -> bool:
        return self.approval_mode == DATTO_APPROVAL_MODE_PER_RUN


def _powershell_command_token(segment: str) -> str:
    text = segment.strip()

    if not text:
        return ""

    token = text.split(None, 1)[0]

    if re.fullmatch(
        r"[A-Za-z][A-Za-z0-9-]*",
        token,
    ) is None:
        return ""

    return token.casefold()


def _powershell_is_deterministically_read_only(
    command: object,
) -> bool:
    if not isinstance(command, str):
        return False

    text = command.strip()

    if not text or len(text) > 4000:
        return False

    # Standing-safe is limited to a simple one-line PowerShell pipeline.
    # Any construct that can chain commands, invoke expressions, redirect
    # data, expand variables, create script blocks, call methods, splat
    # arguments, or escape normal parsing falls back to per-run approval.
    for forbidden in (
        "\n",
        "\r",
        ";",
        "`",
        "$",
        "@",
        "{",
        "}",
        "(",
        ")",
        ">",
        "<",
        "&",
        "--%",
    ):
        if forbidden in text:
            return False

    segments = [
        value.strip()
        for value in text.split("|")
    ]

    if not segments or any(
        not value for value in segments
    ):
        return False

    risky_parameter = re.compile(
        r"(?i)(?:^|\s)-("
        r"credential|"
        r"cimsession|"
        r"session|"
        r"connectionuri|"
        r"scriptblock|"
        r"argumentlist|"
        r"encodedcommand|"
        r"asjob"
        r")\b"
    )

    remote_computer = re.compile(
        r"(?i)(?:^|\s)-computername\b"
    )

    for index, segment in enumerate(segments):
        command_name = _powershell_command_token(
            segment
        )

        allowed = (
            _READ_ONLY_POWERSHELL_PRIMARY
            if index == 0
            else _READ_ONLY_POWERSHELL_PIPELINE
        )

        if command_name not in allowed:
            return False

        if risky_parameter.search(segment):
            return False

        # Test-NetConnection is expressly a local diagnostic whose normal
        # purpose is testing a named remote network destination. Other
        # standing-safe cmdlets may not widen execution/query scope to a
        # second managed computer through -ComputerName.
        if (
            command_name != "test-netconnection"
            and remote_computer.search(segment)
        ):
            return False

    return True


def effective_datto_component_approval_mode(
    component: DattoApprovedComponent,
    variables: object,
) -> tuple[str, str | None]:
    """Return the server-derived approval mode for one exact execution.

    Component configuration remains the baseline. The exact reviewed AOT
    PowerShell runner is the only component whose approval can be narrowed
    further by deterministic command analysis.

    Unknown, ambiguous, sensitive or non-read-only PowerShell always remains
    per-run. The caller cannot supply or override this classification.
    """

    if not (
        component.uid == DATTO_AD_HOC_POWERSHELL_UID
        and component.name.casefold()
        == DATTO_AD_HOC_POWERSHELL_NAME.casefold()
    ):
        return component.approval_mode, None

    if not isinstance(variables, Mapping):
        return (
            DATTO_APPROVAL_MODE_PER_RUN,
            _POWERSHELL_APPROVAL_REQUIRED_REASON,
        )

    if len(variables) != 1:
        return (
            DATTO_APPROVAL_MODE_PER_RUN,
            _POWERSHELL_APPROVAL_REQUIRED_REASON,
        )

    supplied_name, supplied_value = next(
        iter(variables.items())
    )

    if (
        not isinstance(supplied_name, str)
        or supplied_name.strip().casefold()
        != "usrinput"
    ):
        return (
            DATTO_APPROVAL_MODE_PER_RUN,
            _POWERSHELL_APPROVAL_REQUIRED_REASON,
        )

    if _powershell_is_deterministically_read_only(
        supplied_value
    ):
        return (
            DATTO_APPROVAL_MODE_STANDING_SAFE,
            _POWERSHELL_READ_ONLY_REASON,
        )

    return (
        DATTO_APPROVAL_MODE_PER_RUN,
        _POWERSHELL_APPROVAL_REQUIRED_REASON,
    )


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
        normalized_uid
        in _FORCED_PER_RUN_COMPONENT_UIDS
        or normalized_name.casefold()
        in _FORCED_PER_RUN_COMPONENT_NAMES
    ):
        normalized_approval_mode = (
            DATTO_APPROVAL_MODE_PER_RUN
        )

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
