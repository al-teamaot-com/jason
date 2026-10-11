from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping, Any



GROMELSKI_COMPANY_ID = 597
GROMELSKI_PRIMARY_CONTACT_ID = 30684489
GROMELSKI_CLOSE_PENDING_STATUS_ID = 21

VULSCAN_CLIENT_NOTE_TEMPLATE_ID = "vulscan-complete-v1"
VULSCAN_CLIENT_NOTE_TITLE = "Vulnerability Resolved"
VULSCAN_CLIENT_NOTE_BODY = (
    "The vulnerability identified in this ticket has been reviewed and the "
    "technical work is complete. Current verification confirms the reported "
    "vulnerability condition is resolved.\n\n"
    "No further action is required at this time. Please reply to or reopen the "
    "ticket if you experience any related issues."
)


@dataclass(frozen=True, slots=True)
class VulScanDispositionPolicy:
    terminal_status: str = "Complete"
    primary_contact_id: int | None = None
    client_notification_required: bool = False
    client_notification_template_id: str | None = None
    continue_patch_monitoring: bool = False


@dataclass(frozen=True, slots=True)
class VulScanPolicyOverride:
    scope: str
    scope_id: str
    policy: VulScanDispositionPolicy


_SCOPE_ORDER = {
    "global": 0,
    "client": 1,
    "site": 2,
    "device": 3,
    "user": 4,
    "ticket": 5,
}


GROMELSKI_VULSCAN_POLICY = VulScanDispositionPolicy(
    terminal_status="Close Pending",
    primary_contact_id=GROMELSKI_PRIMARY_CONTACT_ID,
    client_notification_required=True,
    client_notification_template_id=VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
    continue_patch_monitoring=False,
)


DEFAULT_VULSCAN_POLICY = VulScanDispositionPolicy()


DEFAULT_VULSCAN_CLIENT_POLICY_PATH = (
    Path(__file__).resolve().parents[4] / "config" / "client_policies" / "vulscan.json"
)


def _load_configured_vulscan_overrides(
    path: Path = DEFAULT_VULSCAN_CLIENT_POLICY_PATH,
) -> tuple[VulScanPolicyOverride, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()

    if not isinstance(payload, Mapping) or payload.get("version") != 1:
        return ()
    raw_overrides = payload.get("overrides")
    if not isinstance(raw_overrides, list):
        return ()

    overrides: list[VulScanPolicyOverride] = []
    for raw in raw_overrides:
        if not isinstance(raw, Mapping) or raw.get("enabled") is not True:
            continue
        if raw.get("technical_completion_only") is not True:
            continue
        scope = str(raw.get("scope") or "").strip()
        scope_id = str(raw.get("scope_id") or "").strip()
        if scope not in _SCOPE_ORDER or not scope_id:
            continue
        primary_contact_raw: Any = raw.get("primary_contact_id")
        try:
            primary_contact_id = (
                None if primary_contact_raw is None else int(primary_contact_raw)
            )
        except (TypeError, ValueError):
            continue
        overrides.append(
            VulScanPolicyOverride(
                scope=scope,
                scope_id=scope_id,
                policy=VulScanDispositionPolicy(
                    terminal_status=str(raw.get("terminal_status") or "Complete"),
                    primary_contact_id=primary_contact_id,
                    client_notification_required=bool(
                        raw.get("client_notification_required")
                    ),
                    client_notification_template_id=(
                        str(raw.get("client_notification_template_id") or "").strip()
                        or None
                    ),
                    continue_patch_monitoring=False,
                ),
            )
        )
    return tuple(overrides)


def configured_vulscan_overrides() -> tuple[VulScanPolicyOverride, ...]:
    return _load_configured_vulscan_overrides()


def resolve_vulscan_policy(
    *,
    client_id: int | None = None,
    site_id: str | int | None = None,
    device_id: str | None = None,
    user_id: str | int | None = None,
    ticket_id: str | int | None = None,
    overrides: Iterable[VulScanPolicyOverride] | None = None,
) -> VulScanDispositionPolicy:
    """Resolve VulScan disposition policy from least to most specific scope."""

    identities = {
        "global": "global",
        "client": "" if client_id is None else str(client_id),
        "site": "" if site_id is None else str(site_id),
        "device": "" if device_id is None else str(device_id),
        "user": "" if user_id is None else str(user_id),
        "ticket": "" if ticket_id is None else str(ticket_id),
    }

    selected = DEFAULT_VULSCAN_POLICY
    ranked = sorted(
        tuple(overrides if overrides is not None else configured_vulscan_overrides()),
        key=lambda item: _SCOPE_ORDER.get(item.scope, -1),
    )
    for item in ranked:
        if item.scope not in _SCOPE_ORDER:
            raise ValueError(f"unsupported VulScan policy scope: {item.scope}")
        expected = identities[item.scope]
        if item.scope == "global":
            if item.scope_id.casefold() not in {"global", "*"}:
                continue
        elif not expected or str(item.scope_id) != expected:
            continue
        selected = replace(item.policy)

    return selected
