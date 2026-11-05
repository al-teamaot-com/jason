"""Opt-in MCP adapter for governed Endpoint Security Assessment sessions.

All provider access is delegated to already-existing Jason MCP governed
capability functions, which re-authenticate through Entra/Central Orchestrator.
This adapter grants no extra permission or standing autonomous action.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from autonomous_remediation.endpoint_security_assessment import RawFinding
from uuid import uuid4

from autonomous_remediation.endpoint_security_assessment_artifacts import (
    ArtifactReference, PrivateAssessmentArtifactStore,
)
from autonomous_remediation.endpoint_security_assessment_investigation import (
    ReadOnlyInvestigator,
)
from autonomous_remediation.endpoint_security_assessment_session import (
    EndpointSecurityAssessmentSession, SessionProgress,
)
from autonomous_remediation.endpoint_security_assessment_workflow import (
    AssessmentGovernanceError, AssessmentRequest,
    COMPONENT_NAME, COMPONENT_UID, GovernedAssessmentCoordinator,
    SqliteAssessmentState,
)


ReadCallback = Callable[[str, dict[str, Any]], Mapping[str, Any]]
ActionCallback = Callable[[str, dict[str, Any]], Mapping[str, Any]]
FindingPageCallback = Callable[..., Mapping[str, Any]]


class GovernedMcpPort:
    def __init__(self, read: ReadCallback, action: ActionCallback,
                 finding_page: FindingPageCallback | None = None) -> None:
        self._read = read
        self._action = action
        self._finding_page = finding_page
        self.evidence_refs: list[str] = []

    def read(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self._read(capability, dict(arguments))
        if response.get("status") == "succeeded":
            ref = str(response.get("correlation_id") or "").strip()
            if ref and ref not in self.evidence_refs:
                self.evidence_refs.append(ref)
        return response

    def action(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._action(capability, dict(arguments))

    def read_assessment_findings(
        self, *, job_uid: str, device_uid: str, component_uid: str,
        hostname: str,
    ) -> tuple[RawFinding, ...] | None:
        if self._finding_page is None:
            return None
        all_items: list[dict[str,str]]=[]
        total: int | None = None
        digest: str | None = None
        counts: Mapping[str,int] | None = None
        for page_index in range(12):  # at most 12 * 25 = 300
            response=self._finding_page(
                job_uid=job_uid,device_uid=device_uid,
                component_uid=component_uid,hostname=hostname,
                page_index=page_index,page_size=25,
            )
            if response.get("status") != "succeeded":
                return None
            data=response.get("evidence") or {}
            if (data.get("status") != "succeeded"
                or data.get("job_uid") != job_uid
                or data.get("device_uid") != device_uid
                or data.get("component_uid") != component_uid
                or str(data.get("hostname","")).casefold()!=hostname.casefold()
                or data.get("page_index")!=page_index
                or data.get("page_size")!=25):
                return None
            page=data.get("findings")
            if not isinstance(page,list) or len(page)>25:
                return None
            if total is None:
                total=data.get("total_findings")
                digest=str(data.get("full_list_sha256") or "")
                counts=data.get("severity_counts")
                if (type(total) is not int or total<0 or total>300
                    or len(digest)!=64 or not isinstance(counts,Mapping)):
                    return None
            if (data.get("total_findings") != total
                or data.get("full_list_sha256") != digest
                or data.get("severity_counts") != counts):
                return None
            if (len(all_items)+len(page)>total
                or any(not isinstance(item,dict) for item in page)):
                return None
            all_items.extend(page)
            if data.get("complete") is True:
                if len(all_items)!=total:
                    return None
                serialized=json.dumps(all_items,sort_keys=True,
                                      separators=(",",":"),ensure_ascii=True)
                if sha256(serialized.encode("utf-8")).hexdigest()!=digest:
                    return None
                findings=tuple(RawFinding(
                    severity=str(item["severity"]),
                    category=str(item["category"]),
                    name=str(item["name"]),
                    title=str(item["title"]),
                    path=str(item.get("path") or ""),
                    evidence_refs=(f"datto-rmm:job:{job_uid}",),
                ) for item in all_items)
                return findings
        return None


@dataclass(frozen=True)
class BoundTechnician:
    # Construct this only from the existing authenticated Entra/MCP context.
    identity: str
    organization_id: str

    def __post_init__(self) -> None:
        if not self.identity.strip() or not self.organization_id.strip():
            raise AssessmentGovernanceError("AUTHENTICATED_TECHNICIAN_REQUIRED")


class EndpointSecurityAssessmentMcpAdapter:
    """Single human instruction -> persisted governed scan -> async resume -> PDF.

    A conversational tool can call start once, then resume on the same request
    ID until complete.  The shared runtime scheduler may also call resume,
    subject to its separate owner-approved authorization setup.  This module
    does not schedule work or impersonate a human in the background.
    """

    def __init__(self, *, db_path: str | Path, artifact_dir: str | Path,
                 read: ReadCallback, action: ActionCallback,
                 finding_page: FindingPageCallback | None = None) -> None:
        self.store = SqliteAssessmentState(db_path)
        self.port = GovernedMcpPort(read, action, finding_page=finding_page)
        self.coordinator = GovernedAssessmentCoordinator(self.port, self.store)
        self.investigator = ReadOnlyInvestigator(self.port, str(db_path))
        self.session = EndpointSecurityAssessmentSession(
            self.coordinator, self.investigator)
        self.artifacts = PrivateAssessmentArtifactStore(db_path, artifact_dir)

    def _get_request(self, request_id: str,
                     technician: BoundTechnician) -> AssessmentRequest:
        if not request_id.strip() or len(request_id) > 160:
            raise AssessmentGovernanceError("INVALID_REQUEST_REFERENCE")
        with sqlite3.connect(self.store.db_path) as db:
            row = db.execute("""SELECT request_id,organization_id,client_site_uid,
                hostname,requester_identity FROM endpoint_security_assessment
                WHERE request_id=?""", (request_id,)).fetchone()
        if row is None:
            raise AssessmentGovernanceError("ASSESSMENT_REQUEST_NOT_FOUND")
        if row[1] != technician.organization_id or row[4] != technician.identity:
            raise AssessmentGovernanceError("ASSESSMENT_REQUEST_AUTHORITY_BOUNDARY")
        return AssessmentRequest(
            request_id=row[0], organization_id=row[1], client_site_uid=row[2],
            hostname=row[3], requester_identity=row[4])

    def start(self, *, technician: BoundTechnician,
              hostname: str, direct_technician_approval: bool) -> tuple[
                  AssessmentRequest, SessionProgress]:
        name = hostname.strip()
        if (not name or len(name)>100 or
            any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in name)):
            raise AssessmentGovernanceError("HOSTNAME_NOT_AN_EXACT_SELECTOR")
        lookup = self.port.read("endpoint.device.search", {
            "hostname":name,"max":100,
        })
        if lookup.get("status") != "succeeded":
            raise AssessmentGovernanceError("GOVERNED_DEVICE_DISCOVERY_DENIED")
        evidence = lookup.get("evidence") or {}
        unique = [
            item for item in evidence.get("resource_matches", ())
            if str(item.get("hostname") or "").casefold() == name.casefold()
            and item.get("site_id") and item.get("resource_id")
        ]
        if len(unique) != 1:
            raise AssessmentGovernanceError("EXACT_ENDPOINT_UNIQUE_MATCH_REQUIRED")
        site_uid = str(unique[0]["site_id"])
        req = AssessmentRequest(
            request_id="esa_"+uuid4().hex,
            organization_id=technician.organization_id,
            client_site_uid=site_uid,
            hostname=name,
            requester_identity=technician.identity,
        )
        # A repeated start call for the same authenticated technician,
        # customer/site and active device MUST resume the first accepted job.
        # The database's scoped unique index also blocks concurrent races.
        existing = self.store.find_active(req)
        if existing is not None:
            prior = AssessmentRequest(
                request_id=existing["request_id"],
                organization_id=existing["organization_id"],
                client_site_uid=existing["client_site_uid"],
                hostname=existing["hostname"],
                requester_identity=existing["requester_identity"],
            )
            return prior, self.session.advance(prior,
                                               approval_bound_arguments=None)
        prepared = self.coordinator.prepare(req)
        args=None
        if direct_technician_approval and prepared.state == "waiting_approval":
            # This is allowed only when the invoking MCP turn is a direct,
            # authenticated technician command for this exact endpoint. The
            # existing execute_governed_capability validates the same caller,
            # justification, approval, impact and target again.
            if not self.port.evidence_refs:
                raise AssessmentGovernanceError("PROVIDER_EVIDENCE_REFERENCES_REQUIRED")
            args={
                "device_uid":prepared.device_uid,
                "component_uid":COMPONENT_UID,
                "component_name":COMPONENT_NAME,
                "variables":{},
                "explicit_approval":True,
                "jason_remediation_review":{
                    "decision":"recommend",
                    "target_id":prepared.device_uid,
                    "evidence_refs":list(self.port.evidence_refs),
                    "problem":"Authenticated technician explicitly requested this exact endpoint's AOT read-only security assessment.",
                    "expected_improvement":"Collect bounded read-only evidence and independently investigate observed security indicators; do not change endpoint state.",
                    "verification":"Verify exact job terminal status, stdout/stderr, managed antivirus and every finding; no duplicate job or remediation.",
                    "narrower_options":[],
                }
            }
        progress=self.session.advance(req,approval_bound_arguments=args)
        return req,progress

    def resume(self, *, technician: BoundTechnician,
               request_id: str) -> tuple[AssessmentRequest, SessionProgress]:
        req=self._get_request(request_id,technician)
        return req,self.session.advance(req,approval_bound_arguments=None)

    def artifact(self, *, technician: BoundTechnician, request_id: str,
                 audience: str) -> tuple[ArtifactReference, bytes]:
        req,progress=self.resume(technician=technician,request_id=request_id)
        if progress.assessment is None:
            raise AssessmentGovernanceError("REPORT_STILL_IN_PROGRESS")
        final_progress=self.coordinator.collect(req,additional_reviews=(
            self.investigator.known_results(req,device_uid=str(progress.assessment.device_uid))))
        ref=self.artifacts.publish(
            req,progress=final_progress,audience=audience,
            bound_requester=technician.identity)
        data=self.artifacts.retrieve(req,reference=ref,
                                     bound_requester=technician.identity)
        return ref,data
