"""Runtime binding contract for Jason - Datto EDR/AV Diagnose & Repair.

This module contains no provider calls and performs no device work. It converts
one deterministic playbook action into an exact governed capability request and
fails closed when the live Jason surface cannot represent the requested action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from datto_edr_av_playbook import (
    AV_FORCE_UPDATE_COMMAND,
    ActionKind,
    PlannedAction,
    PlaybookRun,
    PLAYBOOK_NAME,
    internal_ticket_note,
)


AUTOMATION_COMPONENT_EXECUTE = "automation.component.execute"
AUTOMATION_JOB_READ = "automation.job.read"
AUTOMATION_JOB_OUTPUT_READ = "automation.job.output.read"
SERVICE_TICKET_NOTE_CREATE = "service.ticket.note.create"
SERVICE_TICKET_UPDATE = "service.ticket.update"
ENDPOINT_SECURITY_SCAN_START = "endpoint.security.scan.start"
ENDPOINT_SECURITY_STATUS_READ = "endpoint.security.status.read"
ENDPOINT_SECURITY_DETECTION_SEARCH = "endpoint.security.detection.search"
ENDPOINT_SECURITY_DETECTION_READ = "endpoint.security.detection.read"
ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH = "endpoint.security.scan.history.search"

RUN_AD_HOC_POWERSHELL_COMPONENT = "Run Ad Hoc Command (PowerShell 2-5) [WIN]"
RUN_AD_HOC_POWERSHELL_UID = "8a1c153c-feee-41c5-9c9b-58a48e0214fe"

# The playbook is permitted to use the generic Datto command component only for
# this one fixed AV operation. No user-supplied command text is accepted here.
# The command discovers the currently active HUNTAgent service executable,
# permits only the two Datto paths observed in AOT's environment, then invokes
# exactly: agent.exe datto-av --force-update.
DATTO_AV_FORCE_UPDATE_POWERSHELL = (
    "$s=Get-CimInstance Win32_Service -Filter \"Name='HUNTAgent'\" -ErrorAction Stop;"
    "$raw=[string]$s.PathName;"
    "if($raw -match '^\\s*\"([^\"]+\\.exe)\"'){$p=$matches[1]}"
    "elseif($raw -match '^\\s*(.+?\\.exe)(?:\\s+--service)?\\s*$'){$p=$matches[1]}"
    "else{throw 'Unable to resolve HUNTAgent executable path'};"
    "$allowed=@('C:\\ProgramData\\CentraStage\\AEMAgent\\RMM.AdvancedThreatDetection\\agent.exe',"
    "'C:\\Program Files\\Infocyte\\agent\\agent.exe');"
    "if($allowed -notcontains $p){throw (\"Unapproved HUNTAgent path: {0}\" -f $p)};"
    "& $p 'datto-av' '--force-update';exit $LASTEXITCODE"
)


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
# component catalog on 2026-09-17, except the ad-hoc PowerShell identity which
# is the exact component used in the previously successful AOT-50282 repair.
# These identities are evidence, not global standing-safe authority; policy
# still decides whether a step may execute.
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
    RUN_AD_HOC_POWERSHELL_COMPONENT: ComponentIdentity(
        uid=RUN_AD_HOC_POWERSHELL_UID,
        name=RUN_AD_HOC_POWERSHELL_COMPONENT,
    ),
}


def bind_execution(action: PlannedAction, *, device_uid: str) -> CapabilityRequest:
    """Bind one playbook action to Jason's existing governed execution surface.

    The generic PowerShell component is allowed only for the exact predefined
    Datto AV force-update operation. The runtime generates the command itself;
    callers cannot supply arbitrary PowerShell through this binding.
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
        if action.operation != AV_FORCE_UPDATE_COMMAND:
            raise RuntimeBindingError(
                f"unapproved predefined command: {action.operation}"
            )

        component = VERIFIED_COMPONENTS[RUN_AD_HOC_POWERSHELL_COMPONENT]
        return CapabilityRequest(
            capability=AUTOMATION_COMPONENT_EXECUTE,
            arguments={
                "device_uid": target,
                "component_uid": component.uid,
                "component_name": component.name,
                "variables": {"Command": DATTO_AV_FORCE_UPDATE_POWERSHELL},
                "job_name": f"{PLAYBOOK_NAME} - {action.step.value}",
                "idempotency_key": action.idempotency_key,
            },
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


def bind_ticket_work_start(
    ticket_id: int,
    *,
    device_name: str | None = None,
    issue_type: str | None = None,
    sub_issue_type: str | None = None,
    ticket_type: str | None = None,
) -> CapabilityRequest:
    """Bind Jason's standing Autotask ticket-work-start lifecycle transition.

    The MCP server owns the fixed queue/status/work-type defaults and performs
    exact device correlation. Playbooks may contribute classification labels only
    when triage has enough evidence to do so; blank labels are omitted.
    """

    try:
        durable_ticket_id = int(ticket_id)
    except (TypeError, ValueError) as error:
        raise RuntimeBindingError(
            "Autotask ticket id must be positive"
        ) from error
    if durable_ticket_id <= 0:
        raise RuntimeBindingError("Autotask ticket id must be positive")

    arguments: dict[str, Any] = {
        "ticket_id": durable_ticket_id,
        "begin_work": True,
    }

    optional = {
        "device_name": device_name,
        "issue_type": issue_type,
        "sub_issue_type": sub_issue_type,
        "ticket_type": ticket_type,
    }
    for key, raw in optional.items():
        value = str(raw or "").strip()
        if value:
            arguments[key] = value

    return CapabilityRequest(
        SERVICE_TICKET_UPDATE,
        arguments,
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


def bind_playbook_internal_note(run: PlaybookRun, *, ticket_id: int) -> CapabilityRequest:
    """Bind the playbook's own milestone summary to governed Autotask documentation.

    Callers must execute this request through Central Orchestrator. This helper
    prevents an operator/chat layer from composing an ad-hoc support note.
    """

    return bind_internal_note(ticket_id, internal_ticket_note(run))


def bind_security_scan_start(*, device_uid: str, agent_id: str, scan_type: str) -> CapabilityRequest:
    device = str(device_uid or "").strip()
    agent = str(agent_id or "").strip()
    selected = str(scan_type or "").strip().casefold()
    if not device or not agent:
        raise RuntimeBindingError("exact Datto device UID and EDR agent ID are required")
    if selected not in {"quick", "full"}:
        raise RuntimeBindingError("scan_type must be quick or full")
    return CapabilityRequest(ENDPOINT_SECURITY_SCAN_START, {"resource_id": device, "agent_id": agent, "scan_type": selected})

def bind_security_status_read(*, device_uid: str) -> CapabilityRequest:
    device = str(device_uid or "").strip()
    if not device:
        raise RuntimeBindingError("exact Datto device UID is required")
    return CapabilityRequest(ENDPOINT_SECURITY_STATUS_READ, {"resource_id": device})

def bind_security_detection_search(*, agent_id: str, limit: int = 100) -> CapabilityRequest:
    agent = str(agent_id or "").strip()
    if not agent:
        raise RuntimeBindingError("exact EDR agent ID is required")
    if not 1 <= int(limit) <= 100:
        raise RuntimeBindingError("detection search limit must be between 1 and 100")
    return CapabilityRequest(ENDPOINT_SECURITY_DETECTION_SEARCH, {"agent_id": agent, "limit": int(limit)})

def bind_security_scan_history(*, agent_id: str, limit: int = 25) -> CapabilityRequest:
    agent = str(agent_id or "").strip()
    if not agent:
        raise RuntimeBindingError("exact EDR agent ID is required")
    if not 1 <= int(limit) <= 100:
        raise RuntimeBindingError("scan history limit must be between 1 and 100")
    return CapabilityRequest(ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH, {"agent_id": agent, "limit": int(limit)})
