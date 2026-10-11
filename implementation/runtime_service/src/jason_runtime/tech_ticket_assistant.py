"""Read-only technician advisory projection for Project Jason.

This module deliberately contains no provider writes. It turns already-governed
ticket/evidence collection into a concise technician-facing recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .gpt_insights import CATEGORY_COMMANDS, InsightEvidence


@dataclass(frozen=True, slots=True)
class AdvisoryStep:
    kind: str
    action: str
    reason: str


@dataclass(frozen=True, slots=True)
class TechTicketAdvisory:
    assessment: str
    confidence: str
    evidence: tuple[str, ...]
    next_steps: tuple[AdvisoryStep, ...]
    remediation_options: tuple[str, ...] = ()
    approval_required: tuple[str, ...] = ()


def _norm(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def build_tech_ticket_advisory(
    evidence: InsightEvidence,
    *,
    attempted_steps: Sequence[str] = (),
    prior_resolution_hints: Sequence[str] = (),
) -> TechTicketAdvisory:
    attempted = {_norm(item) for item in attempted_steps if _norm(item)}
    evidence_lines: list[str] = []
    if evidence.device_name:
        state = (
            "online"
            if evidence.device_online is True
            else "offline"
            if evidence.device_online is False
            else "state unavailable"
        )
        evidence_lines.append(f"Device {evidence.device_name}: {state}")
    if evidence.operating_system:
        evidence_lines.append(f"OS: {evidence.operating_system}")
    if evidence.connection_summary:
        evidence_lines.append(f"Connection: {evidence.connection_summary}")
    if evidence.related_ticket_count:
        evidence_lines.append(
            f"Related same-company tickets: {evidence.related_ticket_count}"
        )
    if evidence.site_correlation:
        evidence_lines.append(f"Site correlation: {evidence.site_correlation}")
    if evidence.unresolved_reason:
        evidence_lines.append(f"Evidence gap: {evidence.unresolved_reason}")

    if evidence.category == "unknown":
        assessment = (
            "Current evidence does not support a confident fault classification. "
            "Do not assert root cause yet."
        )
        confidence = "low"
    else:
        assessment = (
            f"Evidence supports a {evidence.category} troubleshooting branch, "
            "but does not yet prove root cause."
        )
        confidence = "moderate" if not evidence.unresolved_reason else "low"

    candidates: list[AdvisoryStep] = []
    if evidence.category == "network":
        candidates.extend(
            (
                AdvisoryStep(
                    "diagnostic",
                    "Correlate the reported time with adapter, DHCP/DNS, gateway, and site evidence.",
                    "Separates endpoint-only failure from a site/network condition before configuration changes.",
                ),
                AdvisoryStep(
                    "diagnostic",
                    "Confirm the active wired/Wi-Fi path from existing adapter evidence.",
                    "Avoids asking the user or technician to rediscover a fact Jason can already obtain.",
                ),
            )
        )
    elif evidence.category == "printing":
        candidates.extend(
            (
                AdvisoryStep(
                    "diagnostic",
                    "Check queue state, exact driver, port type/address, and spooler health.",
                    "Distinguishes queue/driver/port drift from a device or spooler problem.",
                ),
                AdvisoryStep(
                    "diagnostic",
                    "Compare the current printer configuration with the AOT known-good/vendor-supported baseline.",
                    "Avoids reinstalling a working configuration merely because it differs from preference.",
                ),
            )
        )
    elif evidence.category == "performance":
        candidates.extend(
            (
                AdvisoryStep(
                    "diagnostic",
                    "Check uptime, top CPU/memory consumers, free memory, and recent System/Application errors.",
                    "Establishes resource pressure or crash evidence before restart/reboot decisions.",
                ),
            )
        )
    elif evidence.category == "login":
        candidates.extend(
            (
                AdvisoryStep(
                    "diagnostic",
                    "Correlate the affected identity, endpoint state, and recent authentication/system evidence.",
                    "Avoids credential resets when the failure may be endpoint, policy, or service related.",
                ),
            )
        )
    elif evidence.category == "application":
        candidates.extend(
            (
                AdvisoryStep(
                    "diagnostic",
                    "Confirm process state/version and review recent application errors before repair or reinstall.",
                    "Establishes whether the application is actually failing and captures evidence first.",
                ),
            )
        )
    else:
        candidates.append(
            AdvisoryStep(
                "diagnostic",
                "Collect only the missing facts that are not already discoverable from governed systems.",
                "The ticket is not yet specific enough for a safe diagnostic branch.",
            )
        )

    commands = CATEGORY_COMMANDS.get(evidence.category, ())
    if commands:
        candidates.append(
            AdvisoryStep(
                "diagnostic",
                f"Run the approved read-only check: {commands[0]}",
                "Provides a bounded next evidence point without changing endpoint state.",
            )
        )

    selected: list[AdvisoryStep] = []
    for step in candidates:
        action_norm = _norm(step.action)
        if any(token and (token in action_norm or action_norm in token) for token in attempted):
            continue
        if any(_norm(existing.action) == action_norm for existing in selected):
            continue
        selected.append(step)
        if len(selected) == 3:
            break

    remediation: list[str] = []
    approvals: list[str] = []
    for hint in prior_resolution_hints[:3]:
        clean = " ".join(str(hint).split())
        if clean:
            remediation.append(
                f"Prior confirmed resolution evidence: {clean}. Re-verify applicability before reuse."
            )
    if evidence.device_online is False:
        remediation.append(
            "Defer endpoint-changing remediation until the exact device is reachable and current evidence can be rechecked."
        )
    if evidence.category in {"printing", "login", "application", "network"}:
        approvals.append(
            "Any modifying or disruptive remediation remains subject to its existing playbook/capability approval policy."
        )

    return TechTicketAdvisory(
        assessment=assessment,
        confidence=confidence,
        evidence=tuple(evidence_lines[:6]),
        next_steps=tuple(selected),
        remediation_options=tuple(remediation[:3]),
        approval_required=tuple(approvals),
    )

def render_tech_ticket_advisory(advisory: TechTicketAdvisory) -> str:
    lines = [
        "Tech Ticket Assistant",
        "",
        f"Assessment: {advisory.assessment}",
        f"Confidence: {advisory.confidence}",
    ]
    if advisory.evidence:
        lines.extend(["", "Evidence"])
        lines.extend(f"- {item}" for item in advisory.evidence[:6])
    if advisory.next_steps:
        lines.extend(["", "Next best checks"])
        for index, step in enumerate(advisory.next_steps[:3], start=1):
            lines.append(f"{index}. {step.action}")
            lines.append(f"   Why: {step.reason}")
    if advisory.remediation_options:
        lines.extend(["", "Possible remediation options"])
        lines.extend(f"- {item}" for item in advisory.remediation_options[:3])
    if advisory.approval_required:
        lines.extend(["", "Authority"])
        lines.extend(f"- {item}" for item in advisory.approval_required)
    return "\n".join(lines).strip()
