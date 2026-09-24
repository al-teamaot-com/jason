"""Deterministic evidence model for AOT client security/posture reviews.

This module deliberately does not fetch provider data. Governed provider reads collect
observations; this evaluator classifies only supplied evidence and never converts
missing evidence into a healthy state.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

class PostureState(str, Enum):
    CONFIRMED_GOOD="confirmed_good"
    CONFIRMED_GAP="confirmed_gap"
    UNKNOWN="unknown"
    NOT_APPLICABLE="not_applicable"
    EVIDENCE_UNAVAILABLE="evidence_unavailable"

@dataclass(frozen=True, slots=True)
class EvidenceObservation:
    source: str
    observed_at: str
    correlation_id: str
    facts: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class ControlAssessment:
    control_id: str
    title: str
    state: PostureState
    rationale: str
    evidence: tuple[EvidenceObservation, ...]
    remediation_hint: str | None = None

@dataclass(frozen=True, slots=True)
class ControlRule:
    control_id: str
    title: str
    required_fact: str
    expected: Any
    remediation_hint: str

AOT_BASELINE: tuple[ControlRule,...]=(
    ControlRule("ENDPOINT-ENCRYPTION","Endpoint disk encryption","bitlocker_enabled",True,"Enable and escrow BitLocker according to AOT policy."),
    ControlRule("ENDPOINT-AV","Managed antivirus protection","managed_av_healthy",True,"Restore the AOT-managed AV/EDR protection state."),
    ControlRule("ENDPOINT-EDR","Managed EDR protection","managed_edr_healthy",True,"Restore the AOT-managed EDR protection state."),
    ControlRule("ENDPOINT-OS","Supported endpoint operating system","os_supported",True,"Upgrade or replace unsupported operating systems."),
    ControlRule("ENDPOINT-MONITORING","DRMM monitoring health","drmm_monitoring_healthy",True,"Investigate unresolved actionable DRMM monitoring conditions."),
    ControlRule("VULNERABILITY","Vulnerability-management coverage","vulscan_covered",True,"Restore expected VulScan coverage or document an approved exception."),
    ControlRule("DNS-PROTECTION","Protective DNS coverage","dnsfilter_covered",True,"Restore expected DNSFilter coverage or document an approved exception."),
    ControlRule("BACKUP-COVERAGE","Managed backup coverage","backup_covered",True,"Restore expected managed backup coverage."),
    ControlRule("BACKUP-SUCCESS","Recent successful backup","backup_recent_success",True,"Investigate backup failure/staleness before treating protection as healthy."),
    ControlRule("IDENTITY-MFA","Microsoft identity MFA posture","mfa_posture_good",True,"Correct MFA registration/enforcement gaps."),
    ControlRule("IDENTITY-CA","Conditional Access baseline","conditional_access_good",True,"Review Conditional Access against the AOT baseline."),
    ControlRule("DOCUMENTATION","Required documentation completeness","documentation_complete",True,"Resolve missing, stale, or conflicting durable documentation."),
)

def assess_control(rule: ControlRule, observations: Sequence[EvidenceObservation], *, applicable: bool=True, source_available: bool=True, coverage_complete: bool=False) -> ControlAssessment:
    ev=tuple(observations)
    if not applicable:
        return ControlAssessment(rule.control_id,rule.title,PostureState.NOT_APPLICABLE,"Control marked not applicable for this client/resource.",ev)
    if not source_available:
        return ControlAssessment(rule.control_id,rule.title,PostureState.EVIDENCE_UNAVAILABLE,"Authoritative evidence source is not currently available to Jason.",ev)
    values=[o.facts[rule.required_fact] for o in ev if rule.required_fact in o.facts]
    if not values:
        return ControlAssessment(rule.control_id,rule.title,PostureState.UNKNOWN,"No authoritative observation establishes this control state.",ev)
    if any(v != rule.expected for v in values):
        return ControlAssessment(rule.control_id,rule.title,PostureState.CONFIRMED_GAP,"Authoritative evidence contains a value outside the AOT baseline.",ev,rule.remediation_hint)
    if not coverage_complete:
        return ControlAssessment(rule.control_id,rule.title,PostureState.UNKNOWN,"Available evidence is healthy but does not cover the complete client scope.",ev)
    return ControlAssessment(rule.control_id,rule.title,PostureState.CONFIRMED_GOOD,"Complete authoritative evidence matches the AOT baseline.",ev)


def build_review(*, client_id: str, evidence_by_control: Mapping[str,Sequence[EvidenceObservation]], unavailable_controls: Sequence[str]=(), not_applicable_controls: Sequence[str]=(), coverage_complete_controls: Sequence[str]=()) -> Mapping[str,Any]:
    cid=client_id.strip()
    if not cid: raise ValueError("client_id is required")
    unavailable=set(unavailable_controls); na=set(not_applicable_controls); complete=set(coverage_complete_controls)
    assessments=[assess_control(r,evidence_by_control.get(r.control_id,()),applicable=r.control_id not in na,source_available=r.control_id not in unavailable,coverage_complete=r.control_id in complete) for r in AOT_BASELINE]
    counts={state.value:sum(a.state is state for a in assessments) for state in PostureState}
    proposals=[{"control_id":a.control_id,"title":a.title,"rationale":a.rationale,"proposed_action":a.remediation_hint} for a in assessments if a.state is PostureState.CONFIRMED_GAP]
    return {"client_id":cid,"assessments":assessments,"counts":counts,"improvement_proposals":proposals,"automatic_changes_allowed":False}

@dataclass(frozen=True, slots=True)
class ClientEvidenceBinding:
    """Provider identifiers proven to refer to the same client boundary."""
    autotask_company_id: str
    autotask_company_name: str
    drmm_site_uid: str | None = None
    it_glue_organization_id: str | None = None
    dnsfilter_organization_id: str | None = None

    def __post_init__(self) -> None:
        if not self.autotask_company_id.strip() or not self.autotask_company_name.strip():
            raise ValueError("an exact Autotask company id and name are required")


def unavailable_controls_for_binding(binding: ClientEvidenceBinding, *, endpoint_backup_api_available: bool=False, microsoft_security_reads_available: bool=False, dnsfilter_api_available: bool=False) -> tuple[str,...]:
    unavailable={"BACKUP-SUCCESS"}
    if not endpoint_backup_api_available:
        unavailable.add("BACKUP-COVERAGE")
    if not microsoft_security_reads_available:
        unavailable.update({"IDENTITY-MFA","IDENTITY-CA"})
    if binding.drmm_site_uid is None:
        unavailable.update({"ENDPOINT-ENCRYPTION","ENDPOINT-AV","ENDPOINT-EDR","ENDPOINT-OS","ENDPOINT-MONITORING","VULNERABILITY"})
    if not dnsfilter_api_available or binding.dnsfilter_organization_id is None:
        unavailable.add("DNS-PROTECTION")
    if binding.it_glue_organization_id is None:
        unavailable.add("DOCUMENTATION")
    return tuple(sorted(unavailable))
