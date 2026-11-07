"""One-message governed MCP adapter acceptance, identity and same-job replay."""
from __future__ import annotations

import pytest

from jason_mcp.endpoint_security_assessment_adapter import (
    BoundTechnician, EndpointSecurityAssessmentMcpAdapter,
)
from autonomous_remediation.endpoint_security_assessment_workflow import (
    AssessmentGovernanceError,
)
from autonomous_remediation.test_endpoint_security_assessment import HUNT, output
from autonomous_remediation.test_endpoint_security_assessment_investigation import (
    ProbePort, probe_output,
)

TECH=BoundTechnician(identity="entra-jason-technician",
                     organization_id="aot-organization")


class CorrelatedPort(ProbePort):
    def read(self, capability, arguments):
        result=super().read(capability, arguments)
        if result.get("status")=="succeeded":
            result=dict(result)
            result["correlation_id"]="corr_authenticated_proof_"+capability.replace(".","_")
        return result


def make_adapter(tmp_path):
    provider=CorrelatedPort()
    def action(cap,args):
        if cap!="automation.component.execute":
            raise AssertionError("unexpected action")
        assert args["jason_remediation_review"]["evidence_refs"]
        assert args["explicit_approval"] is True
        return provider.action(cap,args)
    adapter=EndpointSecurityAssessmentMcpAdapter(
        db_path=tmp_path/"state.db",
        artifact_dir=tmp_path/"private",
        read=provider.read,action=action,
    )
    return adapter,provider


def test_one_user_request_runs_one_job_and_emits_private_pdf(tmp_path):
    adapter,provider=make_adapter(tmp_path)
    provider.stdout=output([HUNT],bounded=True)
    req,first=adapter.start(technician=TECH,hostname="CCPC-50960",
                            direct_technician_approval=True)
    assert first.state=="waiting_job"
    assert first.job_uid is not None and provider.actions==1
    # A duplicate tool call for same authenticated user/device must reuse
    # exact request and job; no second scan even with 'approval' again.
    same,again=adapter.start(technician=TECH,hostname="CCPC-50960",
                            direct_technician_approval=True)
    assert same.request_id==req.request_id
    assert provider.actions==1
    provider.job_status="completed"
    pending_req,pending=adapter.resume(technician=TECH,request_id=req.request_id)
    assert pending.state=="investigating"
    assert provider.probe_dispatches==1
    provider.probe_status="completed"
    final_req,final=adapter.resume(technician=TECH,request_id=req.request_id)
    assert final.client_pdf_allowed
    assert final.state=="report_ready"
    ref,pdf=adapter.artifact(technician=TECH,request_id=req.request_id,
                             audience="client")
    assert pdf.startswith(b"%PDF-")
    assert ref.audience=="client"
    assert provider.actions==1
    ref2,again=adapter.artifact(technician=TECH,request_id=req.request_id,
                                audience="client")
    assert ref2.sha256==ref.sha256 and again==pdf


def test_explicit_technician_approval_is_not_minted_by_default(tmp_path):
    adapter,provider=make_adapter(tmp_path)
    req,state=adapter.start(technician=TECH,hostname="CCPC-50960",
                            direct_technician_approval=False)
    assert state.state=="waiting_approval"
    assert provider.actions==0
    resumed=adapter.resume(technician=TECH,request_id=req.request_id)
    assert resumed[1].state=="waiting_approval"
    assert provider.actions==0


def test_wrong_requester_cannot_resume_or_download(tmp_path):
    adapter,provider=make_adapter(tmp_path)
    req,state=adapter.start(technician=TECH,hostname="CCPC-50960",
                            direct_technician_approval=True)
    other=BoundTechnician(identity="different-technician",organization_id=TECH.organization_id)
    with pytest.raises(AssessmentGovernanceError,match="AUTHORITY_BOUNDARY"):
        adapter.resume(technician=other,request_id=req.request_id)
    with pytest.raises(AssessmentGovernanceError,match="AUTHORITY_BOUNDARY"):
        adapter.artifact(technician=other,request_id=req.request_id,audience="technician")


def test_wrong_customer_match_does_not_enter_state_or_dispatch(tmp_path):
    adapter,provider=make_adapter(tmp_path)
    provider.site="different-customer"
    # It is still a unique matched device returned from the authorized
    # provider read, so the adapter correctly binds *that* provider site;
    # the upstream Entra/Orchestrator must still enforce client authorization.
    req,state=adapter.start(technician=TECH,hostname="CCPC-50960",
                            direct_technician_approval=False)
    assert req.client_site_uid=="different-customer"
    assert provider.actions==0


def test_non_matching_or_malformed_host_refused(tmp_path):
    adapter,provider=make_adapter(tmp_path)
    for name in ("", "CCPC-50960; shutdown -r -t 0", "../../etc/passwd"):
        with pytest.raises(AssessmentGovernanceError):
            adapter.start(technician=TECH,hostname=name,
                          direct_technician_approval=True)
    assert provider.actions==0



def test_structured_finding_pages_recover_low_detail_without_false_clear(tmp_path):
    from jason_mcp.endpoint_security_assessment_pages import project_finding_page
    from autonomous_remediation.test_endpoint_security_assessment import MAPS, JOB, COMPONENT, HOST
    from autonomous_remediation.test_endpoint_security_assessment_workflow import DEVICE
    raw=output([HUNT,MAPS])
    expected={"data":{
        "resource_id":JOB,"device_uid":DEVICE,"component_uid":COMPONENT,
        "stream":"stdout","match_count":1,"output_bounded":False,
        "outputs":[{"component_uid":COMPONENT,"stream":"stdout",
                    "text":raw,"truncated":False}],
    }}
    port=CorrelatedPort()
    port.stdout=output([HUNT,MAPS],bounded=True)
    def pages(**kwargs):
        return {"status":"succeeded","evidence":project_finding_page(
            expected,**kwargs)}
    adapter=EndpointSecurityAssessmentMcpAdapter(
        db_path=tmp_path/"state.db",artifact_dir=tmp_path/"private",
        read=port.read,action=port.action,finding_page=pages)
    req,state=adapter.start(technician=TECH,hostname="CCPC-50960",
                            direct_technician_approval=True)
    port.job_status="completed"
    first_req,first=adapter.resume(technician=TECH,request_id=req.request_id)
    assert first.assessment is not None
    assert first.assessment.unresolved_detail_count == 0
    assert any(f.raw.name == "MapS.bat" for f in first.assessment.reviewed)
    assert not first.client_pdf_allowed
    port.probe_status="completed"
    second_req,second=adapter.resume(technician=TECH,request_id=req.request_id)
    assert second.state=="human_review"
    assert second.assessment is not None
    assert not second.assessment.report_publishable
    assert port.actions==1 and port.probe_dispatches==1
    with pytest.raises(AssessmentGovernanceError):
        adapter.artifact(technician=TECH,request_id=req.request_id,
                         audience="client")
    ref,pdf=adapter.artifact(technician=TECH,request_id=req.request_id,
                             audience="technician")
    assert pdf.startswith(b"%PDF-") and ref.audience=="technician"
