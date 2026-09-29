from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable


GROMELSKI_COMPANY_ID = 597
GROMELSKI_PRIMARY_CONTACT_ID = 30684489
GROMELSKI_CLOSE_PENDING_STATUS_ID = 21

VULSCAN_CLIENT_NOTE_TEMPLATE_ID = "vulscan-approved-or-installed-v1"
VULSCAN_CLIENT_NOTE_TITLE = "Vulnerability Update"
VULSCAN_CLIENT_NOTE_BODY = (
    "The identified vulnerability mentioned in this ticket has been reviewed. "
    "The required update has either already been installed or has been approved "
    "for implementation and is scheduled to be applied during the device’s next "
    "regular patching window in accordance with our maintenance policy.\n\n"
    "No further action is required at this time. Monitoring will continue to "
    "confirm successful deployment and remediation. Please reopen the ticket if "
    "you experience any issues following the update."
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
    continue_patch_monitoring=True,
)


DEFAULT_VULSCAN_POLICY = VulScanDispositionPolicy()


def configured_vulscan_overrides() -> tuple[VulScanPolicyOverride, ...]:
    return (
        VulScanPolicyOverride(
            scope="client",
            scope_id=str(GROMELSKI_COMPANY_ID),
            policy=GROMELSKI_VULSCAN_POLICY,
        ),
    )


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
