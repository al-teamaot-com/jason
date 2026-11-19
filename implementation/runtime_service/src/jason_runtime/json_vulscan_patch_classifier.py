"""VulScan patch source-only read-only disposition and non-KB pure evidence.

Uses original policy/source analyzers. No patch approval, Windows Update
change, user notification or provider job is performed by this module.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from .vulscan_client_policy import resolve_vulscan_policy
from .vulscan_non_kb import analyze_non_kb_vulscan, render_non_kb_assessment


class JsonVulscanPatchBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class JsonVulscanPatchAssessment:
    disposition: str
    policy_status: str
    exact_kb: str | None
    source_evidence: str
    client_notification_required: bool
    patch_execution_authorized: bool = False


def classify_vulscan_readonly(
    *,
    ticket_id: int,
    company_id: int,
    device_uid: str,
    endpoint: Mapping[str, Any],
    target_kb: str | None,
    patch_inventory: Sequence[Mapping[str, Any]],
    source_text: str,
    installed_software: Sequence[Mapping[str, Any]],
    approved_patch_window_complete: bool,
    first_not_approved_at: datetime | None,
    observed_at: datetime,
) -> JsonVulscanPatchAssessment:
    if (ticket_id<=0 or company_id<0 or not device_uid or
        str(endpoint.get("resource_id") or "")!=device_uid or
        str(endpoint.get("companyID") or "")!=str(company_id)):
        raise JsonVulscanPatchBoundaryError("VULSCAN_EXACT_DEVICE_CLIENT_MISMATCH")
    if observed_at.tzinfo is None or not isinstance(
        patch_inventory,Sequence) or len(patch_inventory)>1000:
        raise JsonVulscanPatchBoundaryError("VULSCAN_PATCH_EVIDENCE_UNVERIFIED")
    policy=resolve_vulscan_policy(client_id=company_id,device_id=device_uid,
                                  ticket_id=ticket_id)
    if policy.client_notification_required and not policy.client_notification_template_id:
        raise JsonVulscanPatchBoundaryError("VULSCAN_NOTIFICATION_TEMPLATE_MISSING")
    if not target_kb:
        assessment=analyze_non_kb_vulscan(source_text,installed_software)
        return JsonVulscanPatchAssessment(
            "non_kb_"+assessment.classification,
            policy.terminal_status,None,render_non_kb_assessment(assessment),
            policy.client_notification_required)
    exact=target_kb.upper().replace(" ","")
    if not exact.startswith("KB") or not exact[2:].isdigit():
        raise JsonVulscanPatchBoundaryError("VULSCAN_INVALID_KB_IDENTITY")
    matches=[
        item for item in patch_inventory
        if isinstance(item,Mapping) and str(
            item.get("kb") or item.get("kbNumber") or
            item.get("identifier") or "").upper().replace(" ","")==exact
    ]
    if len(matches)!=1:
        raise JsonVulscanPatchBoundaryError("VULSCAN_PATCH_NOT_EXACT_UNIQUE")
    patch=matches[0]
    current=str(patch.get("status") or "").strip().casefold()
    approved=patch.get("approved") is True
    installed=patch.get("installed") is True
    superseded=patch.get("superseded") is True
    reboot_required=endpoint.get("reboot_required") is True
    if installed or superseded:
        disposition="verified_installed_or_superseded"
    elif reboot_required:
        disposition="reboot_required_exact_approval_human_review"
    elif not approved:
        if first_not_approved_at is None:
            disposition="waiting_patch_approval"
        elif (first_not_approved_at.tzinfo is None or
              first_not_approved_at>observed_at):
            raise JsonVulscanPatchBoundaryError("VULSCAN_APPROVAL_WAIT_TIME_INVALID")
        else:
            disposition=(
                "unapproved_patch_aged_human_review"
                if observed_at-first_not_approved_at>=timedelta(days=10)
                else "waiting_patch_approval"
            )
    elif not approved_patch_window_complete:
        disposition="waiting_approved_patch_window"
    elif "error" in current or "failed" in current:
        disposition="install_failure_human_review"
    else:
        disposition="approved_update_unverified_human_review"
    return JsonVulscanPatchAssessment(
        disposition,policy.terminal_status,exact,
        f"{exact} status={current} approved={approved} installed={installed} "
        f"superseded={superseded} reboot_required={reboot_required}",
        policy.client_notification_required)
