"""Runtime binding contract for Jason - Datto EDR/AV Diagnose & Repair.

This module contains no provider calls and performs no device work. It converts
one deterministic playbook action into an exact governed capability request and
fails closed when the live Jason surface cannot represent the requested action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from datto_edr_av_playbook import ActionKind, PlannedAction, PLAYBOOK_NAME


AUTOMATION_COMPONENT_EXECUTE = "automation.component.execute"
AUTOMATION_JOB_READ = "automation.job.read"
AUTOMATION_JOB_OUTPUT_READ = "automation.job.output.read"
SERVICE_TICKET_NOTE_CREATE = "service.ticket.note.create"


class RuntimeBindingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ComponentIdentity:
    uid: str
    name: str


@dataclass(frozen=True)
class CapabilityRequest:
    capability: str
    arguments: Mapping[str, Any]


# Provider identities independently verified through Jason's governed Datto
# component catalog on 2026-09-17. These identities are evidence, not global
# standing-safe authority; policy still decides whether a step may execute.
VERIFIED_COMPONENTS = {
    "Check Datto EDR/AV Status AOT Ver 12122025-1": ComponentIdentity(
        uid="8cb0f063-5875-452e-88ad-2e1748ed0fd0",
        name="Check Datto EDR/AV Status AOT Ver 12122025-1",
    ),
    "Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1": ComponentIdentity(
        uid="2b49d490-bcae-4825-b31e-c4f1be881ae5",
        name="Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1",
    ),
    "Datto EDR Maintenance [WIN]": ComponentIdentity(
        uid="3f069258-9b5e-4083-9b13-fa61c0fc0499",
        name="Datto EDR Maintenance [WIN]",
    ),
    "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024": ComponentIdentity(
        uid="9c30dab8-b76c-417d-a264-b3ca91995179",
        name="Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024",
    ),
    "Uninstall Datto EDR / AV AOT Ver 11052025-1": ComponentIdentity(
        uid="b1e523aa-6464-4eaf-b99d-0172649f2115",
        name="Uninstall Datto EDR / AV AOT Ver 11052025-1",
    ),
    "230 AM Scheduled Reboot AOT Ver 11282024": ComponentIdentity(
        uid="a61ce810-84a6-435c-ba02-b589a6008f28",
        name="230 AM Scheduled Reboot AOT Ver 11282024",
    ),
}


def bind_execution(action: PlannedAction, *, device_uid: str) -> CapabilityRequest:
    """Bind one playbook action to Jason's existing governed execution surface.

    Free-form commands deliberately do not fall back to PowerShell or shell.
    They remain blocked until an exact vetted Datto component or dedicated
    governed capability exists.
    """

    target = str(device_uid or "").strip()
    if not target:
        raise RuntimeBindingError("exact Datto device UID is required")

    if action.kind in {ActionKind.COMPONENT, ActionKind.SCHEDULED_REBOOT}:
        component = VERIFIED_COMPONENTS.get(action.operation)
        if component is None:
            raise RuntimeBindingError(
                f"unverified Datto component identity: {action.operation}"
            )

        return CapabilityRequest(
            capability=AUTOMATION_COMPONENT_EXECUTE,
            arguments={
                "device_uid": target,
                "component_uid": component.uid,
                "component_name": component.name,
                "variables": dict(action.variables),
                "job_name": f"{PLAYBOOK_NAME} - {action.step.value}",
                "idempotency_key": action.idempotency_key,
            },
        )

    if action.kind == ActionKind.PREDEFINED_COMMAND:
        raise RuntimeBindingError(
            "Datto AV force-update is not yet represented by an exact governed "
            "component/capability; arbitrary shell fallback is prohibited"
        )

    if action.kind == ActionKind.IMMEDIATE_REBOOT:
        raise RuntimeBindingError(
            "immediate reboot is outside the autonomous playbook binding"
        )

    raise RuntimeBindingError(f"unsupported action kind: {action.kind}")


def bind_job_read(job_uid: str) -> CapabilityRequest:
    value = str(job_uid or "").strip()
    if not value:
        raise RuntimeBindingError("job UID is required")
    return CapabilityRequest(AUTOMATION_JOB_READ, {"resource_id": value})


def bind_job_output_read(
    job_uid: str,
    *,
    device_uid: str,
    component_uid: str,
    stream: str = "stdout",
) -> CapabilityRequest:
    job = str(job_uid or "").strip()
    device = str(device_uid or "").strip()
    component = str(component_uid or "").strip()
    selected_stream = str(stream or "stdout").strip().casefold()
    if not job or not device or not component:
        raise RuntimeBindingError(
            "job UID, device UID, and component UID are required for output read"
        )
    if selected_stream not in {"stdout", "stderr"}:
        raise RuntimeBindingError("stream must be stdout or stderr")
    return CapabilityRequest(
        AUTOMATION_JOB_OUTPUT_READ,
        {
            "resource_id": job,
            "device_uid": device,
            "component_uid": component,
            "stream": selected_stream,
        },
    )


def bind_internal_note(ticket_id: int, note: str) -> CapabilityRequest:
    if int(ticket_id) <= 0:
        raise RuntimeBindingError("Autotask ticket id must be positive")
    body = str(note or "").strip()
    if not body:
        raise RuntimeBindingError("internal note body is required")
    return CapabilityRequest(
        SERVICE_TICKET_NOTE_CREATE,
        {
            "ticket_id": int(ticket_id),
            "note": body,
            "title": PLAYBOOK_NAME,
        },
    )
