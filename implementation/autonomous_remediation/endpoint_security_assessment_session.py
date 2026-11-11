"""Single-request composition of persisted scan, follow-up and report stages.

Admission and delivery remain external governed concerns.  This source module
provides the reusable orchestration entrypoint, not a bypass or self-activating
MCP tool; a scheduler/Teams adapter can re-enter advance() after pending jobs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .endpoint_security_assessment import Assessment
from .endpoint_security_assessment_investigation import (
    ReadOnlyInvestigator, available_recipe,
)
from .endpoint_security_assessment_workflow import (
    AssessmentProgress, AssessmentRequest, GovernedAssessmentCoordinator,
)


@dataclass(frozen=True)
class SessionProgress:
    state: str
    next_action: str
    job_uid: str | None
    assessment: Assessment | None
    pending_probe_jobs: tuple[str, ...] = ()
    client_pdf_allowed: bool = False


class EndpointSecurityAssessmentSession:
    """Reusable coordinator, not component-specific copy-paste automation.

    Unknown security findings remain open, but routine supported signed
    components can be investigated through the narrow governed read port.
    Re-enter across process restarts using the persistent store; no repeated
    component submission.
    """

    def __init__(self, scan: GovernedAssessmentCoordinator,
                 investigation: ReadOnlyInvestigator) -> None:
        self.scan = scan
        self.investigation = investigation

    def advance(self, request: AssessmentRequest, *,
                approval_bound_arguments: Mapping | None = None) -> SessionProgress:
        row = self.scan.store.create_or_get(request)
        if not row["device_uid"]:
            p=self.scan.prepare(request)
            if p.state != "waiting_approval":
                return SessionProgress(p.state,p.next_action,p.job_uid,None)
            row = self.scan.store.create_or_get(request)
        if row["state"] == "waiting_device":
            refreshed=self.scan.prepare(request)
            if refreshed.state != "waiting_approval":
                return SessionProgress("waiting_device","recheck_device_availability",
                                       row["job_uid"],None)
            row=self.scan.store.create_or_get(request)
        if row["state"] == "waiting_approval":
            p=self.scan.dispatch(request,
                approval_bound_arguments=approval_bound_arguments)
            if p.state != "waiting_job":
                return SessionProgress(p.state,p.next_action,p.job_uid,None)
            row=self.scan.store.create_or_get(request)
        if row["state"] == "dispatched":
            return SessionProgress("blocked",
                                   "reconcile_previous_action_acceptance_without_redispatch",
                                   row["job_uid"],None)
        if row["state"] in {"blocked", "human_review"}:
            return SessionProgress(row["state"], "inspect_failure_or_genuine_authority_blocker",
                                   row["job_uid"], None)
        if row["state"] not in {"waiting_job","investigating","report_ready"}:
            return SessionProgress("blocked","invalid_persisted_state",
                                   row["job_uid"],None)
        known=self.investigation.known_results(request,
             device_uid=str(row["device_uid"]))
        p=self.scan.collect(request,additional_reviews=known)
        if p.assessment is None:
            return SessionProgress(p.state,p.next_action,p.job_uid,None)
        if p.report_ready:
            return SessionProgress("report_ready","render_and_deliver_authorized_pdf",
                                   p.job_uid,p.assessment,client_pdf_allowed=True)
        # Source output is bounded. Investigate only registered exact
        # identities; do NOT run arbitrary commands from provider text.
        queued: list[str] = []
        for finding in p.assessment.sweep.findings:
            if not available_recipe(finding):
                continue
            if any(review.name == finding.name for review in known):
                continue
            candidate=self.investigation.dispatch_probe(
                request,device_uid=str(row["device_uid"]),finding=finding)
            if candidate:
                queued.append(candidate)
        # A submitted probe must be polled by the normal worker/resume loop.
        # Its internal job UID is never a reason to re-run the main scan.
        pending=False
        for finding in p.assessment.sweep.findings:
            if not available_recipe(finding):
                continue
            if any(review.name == finding.name for review in known):
                continue
            try:
                reviewed=self.investigation.poll_probe(
                    request,device_uid=str(row["device_uid"]),finding=finding)
            except (PermissionError, RuntimeError):
                # Denied/incomplete read stays an explicit unresolved
                # evidence dependency. We do not circumvent it here.
                pending=True
                continue
            if reviewed is None:
                pending=True
        latest=self.investigation.known_results(request,
             device_uid=str(row["device_uid"]))
        if len(latest) > len(known):
            p=self.scan.collect(request,additional_reviews=latest)
            if p.report_ready:
                return SessionProgress(
                    "report_ready","render_and_deliver_authorized_pdf",p.job_uid,
                    p.assessment,client_pdf_allowed=True)
        return SessionProgress(
            "investigating" if pending else "human_review",
            ("resume_exact_investigation_jobs" if pending else
             "prepare_internal_report_with_specific_unresolved_findings"),
            p.job_uid,p.assessment,tuple(sorted(set(queued))),
            client_pdf_allowed=False)
