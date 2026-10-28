"""Provider-neutral, fail-closed justification gate for client/device changes.

It does not grant authority. It prevents a technician's permission from
becoming a command to run an unnecessary or disproportionately disruptive
remediation. The provider contract and existing exact-argument approvals remain
mandatory, independent controls. The review is a proposal, NOT provider proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Any, Mapping


class Impact(str, Enum):
    TARGETED = "targeted"
    SERVICE_INTERRUPTION = "service_interruption"
    HOST_DISRUPTION = "host_disruption"


class RemediationGateResult(str, Enum):
    PERMIT_PROPOSAL = "permit_proposal"
    REFUSE = "refuse"


@dataclass(frozen=True)
class RemediationReviewDecision:
    outcome: RemediationGateResult
    reasons: tuple[str, ...]
    impact: Impact
    action_fingerprint: str

    @property
    def may_proceed_to_authority(self) -> bool:
        return self.outcome is RemediationGateResult.PERMIT_PROPOSAL


MANAGED_ACTION_PREFIXES = (
    "endpoint.", "automation.component.execute", "backup.", "dnsfilter.",
    "management.", "identity.", "security.", "network.",
)

# Server-derived impact. This cannot be downgraded through request metadata.
HOST_DISRUPTION_WORDS = (
    r"\breboot\b", r"\brestart-computer\b", r"\bshutdown\b",
    r"\bstop-computer\b", r"\blogoff\b", r"\blogout\b",
    r"\bisolat(?:e|ion)\b", r"\bnetwork\s+(?:reset|disconnect|disable)\b",
    r"\bdisable-netadapter\b",
)
SERVICE_DISRUPTION_WORDS = (
    r"\brestart(?:-service|\s+service|\s+spooler)\b",
    r"\bstop(?:-service|\s+service|\s+spooler)\b",
)


def applies_to_remediation(capability: str) -> bool:
    return any(str(capability).startswith(prefix) for prefix in MANAGED_ACTION_PREFIXES)


def classify_impact(
    capability: str, arguments: Mapping[str, Any], *, component_name: str = "",
) -> Impact:
    if not applies_to_remediation(capability):
        raise ValueError("not a device/client management action")
    # Assess server-resolved component identity and actual canonical argument
    # values (e.g. PowerShell command), not caller-supplied impact labels.
    variables = arguments.get("variables") or {}
    if not isinstance(variables, Mapping):
        variables = {}
    # Datto Windows ad-hoc PowerShell uses usrinput, whereas other components
    # use Command. Inspect all bounded string variables, not only one alias.
    commands = " ".join(str(value)[:2048] for value in variables.values()
                        if isinstance(value, str))
    sample = " ".join((capability, component_name, commands)).casefold()
    if any(re.search(pattern, sample) for pattern in HOST_DISRUPTION_WORDS):
        return Impact.HOST_DISRUPTION
    if any(re.search(pattern, sample) for pattern in SERVICE_DISRUPTION_WORDS):
        return Impact.SERVICE_INTERRUPTION
    if capability.startswith("identity.") and any(token in sample for token in (
            "disable", "revoke", "reset", "suspend", "delete")):
        return Impact.HOST_DISRUPTION
    # Changing network filtering, isolating applications, restoring backup
    # contents, and changing site variables can interrupt active users even
    # without rebooting the endpoint. When uncertain, require exact approval.
    if capability.startswith(("dnsfilter.", "network.", "management.")):
        return Impact.SERVICE_INTERRUPTION
    if capability.startswith("backup.") and ("restore" in sample or "delete" in sample):
        return Impact.SERVICE_INTERRUPTION
    if any(term in sample for term in ("quarantine", "terminate", "kill-process")):
        return Impact.SERVICE_INTERRUPTION
    # Arbitrary component execution may stop services or user applications;
    # there is no reliable generic metadata proving a component non-disruptive.
    # Read-only status components are exempted only by the separate server-side
    # standing-safe diagnostic classifier before reaching this evaluator.
    if capability == "automation.component.execute":
        return Impact.SERVICE_INTERRUPTION
    return Impact.TARGETED


def action_fingerprint(capability: str, arguments: Mapping[str, Any]) -> str:
    """Reference hash; provider arguments never contain this review's prose."""
    data = {"capability": capability, "arguments": dict(arguments)}
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _meaningful(value: Any, *, limit: int = 1024) -> bool:
    return isinstance(value, str) and 12 <= len(value.strip()) <= limit


def _references(value: Any) -> bool:
    return (isinstance(value, list) and 0 < len(value) <= 12
            and all(isinstance(ref, str) and 5 <= len(ref.strip()) <= 300
                    for ref in value))


def assess_remediation(
    *, capability: str, arguments: Mapping[str, Any],
    review: Mapping[str, Any] | None, component_name: str = "",
    explicit_technician_approval: bool = False,
) -> RemediationReviewDecision:
    """Block unjustified action before the existing governed execution gate.

    Evidence references, explanation and comparison are structured model/tech
    judgments that must be subsequently validated by normal source read and
    result verification. They do NOT grant permission or assert a verified fact.
    """
    impact = classify_impact(capability, arguments, component_name=component_name)
    fingerprint = action_fingerprint(capability, arguments)
    reasons: list[str] = []
    if not isinstance(review, Mapping):
        return RemediationReviewDecision(RemediationGateResult.REFUSE,
                                         ("REMEDIATION_ASSESSMENT_REQUIRED",), impact, fingerprint)
    if review.get("decision") != "recommend":
        reasons.append("REMEDIATION_NOT_RECOMMENDED_BY_JASON")
    if not _meaningful(review.get("problem")):
        reasons.append("REMEDIATION_PROBLEM_NOT_ESTABLISHED")
    if not _references(review.get("evidence_refs")):
        reasons.append("REMEDIATION_EVIDENCE_REFERENCES_REQUIRED")
    # Prevent copy-pasting a justification from one endpoint, policy, or backup
    # asset to a different target. The full action is independently bound to
    # the governed execution ledger's exact canonical argument fingerprint.
    target = next((str(arguments[key]) for key in (
        "device_uid", "resource_id", "asset_id", "policy_id", "agent_id",
        "target_device_uid", "client_id",
    ) if arguments.get(key) not in (None, "")), None)
    if target is not None and review.get("target_id") != target:
        reasons.append("REMEDIATION_TARGET_SCOPE_MISMATCH")
    if not _meaningful(review.get("expected_improvement")):
        reasons.append("REMEDIATION_EXPECTED_BENEFIT_REQUIRED")
    if not _meaningful(review.get("verification")):
        reasons.append("REMEDIATION_VERIFICATION_PLAN_REQUIRED")

    narrower = review.get("narrower_options", [])
    if not isinstance(narrower, list) or len(narrower) > 12:
        reasons.append("REMEDIATION_NARROWER_OPTIONS_INVALID")
        narrower = []
    for option in narrower:
        if not isinstance(option, Mapping) or not _meaningful(option.get("action"), limit=300):
            reasons.append("REMEDIATION_ALTERNATIVE_INVALID")
            continue
        disposition = option.get("disposition")
        if disposition == "viable":
            reasons.append("LESS_DISRUPTIVE_EFFECTIVE_ACTION_AVAILABLE")
        elif disposition not in ("attempted_failed", "not_applicable", "unsafe"):
            reasons.append("REMEDIATION_ALTERNATIVE_UNRESOLVED")
        elif not _references(option.get("evidence_refs")):
            reasons.append("REMEDIATION_ALTERNATIVE_EVIDENCE_REQUIRED")

    if impact is not Impact.TARGETED and not explicit_technician_approval:
        reasons.append("EXPLICIT_DISRUPTION_APPROVAL_REQUIRED")
    if impact is Impact.HOST_DISRUPTION:
        if not narrower:
            reasons.append("HOST_DISRUPTION_REQUIRES_NARROWER_OPTIONS_REVIEW")
        problem = str(review.get("problem") or "").casefold()
        if ("spooler" in problem or "print queue" in problem or "printer" in problem):
            if not any(isinstance(x, Mapping) and
                       ("spooler" in str(x.get("action") or "").casefold() or
                        "print service" in str(x.get("action") or "").casefold())
                       for x in narrower):
                reasons.append("PRINT_SERVICE_REPAIR_NOT_RULED_OUT")

    return RemediationReviewDecision(
        outcome=(RemediationGateResult.REFUSE if reasons else RemediationGateResult.PERMIT_PROPOSAL),
        reasons=tuple(dict.fromkeys(reasons)), impact=impact,
        action_fingerprint=fingerprint,
    )
