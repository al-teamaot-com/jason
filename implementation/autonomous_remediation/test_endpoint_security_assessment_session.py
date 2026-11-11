"""One-request orchestration: exact job, async resume, safe proof, PDF gate."""
from __future__ import annotations

from .endpoint_security_assessment_investigation import ReadOnlyInvestigator
from .endpoint_security_assessment_session import EndpointSecurityAssessmentSession
from .endpoint_security_assessment_report import render_security_pdf, ReportNotPublishable
from .test_endpoint_security_assessment import HUNT, MAPS, output
from .test_endpoint_security_assessment_investigation import ProbePort, probe_output
from .test_endpoint_security_assessment_workflow import DEVICE, approval, req, setup


def create(tmp_path):
    provider = ProbePort()
    flow, _, path = setup(tmp_path, provider)
    inv = ReadOnlyInvestigator(provider, str(path))
    return EndpointSecurityAssessmentSession(flow,inv), provider, path


def test_one_command_session_resumes_to_approved_pdf_without_extra_run(tmp_path):
    session, provider, _ = create(tmp_path)
    provider.stdout = output([HUNT], bounded=True)
    first = session.advance(req(), approval_bound_arguments=approval())
    assert first.state == "waiting_job"
    assert provider.actions == 1
    provider.job_status = "completed"
    second = session.advance(req())
    assert second.state == "investigating"
    assert provider.probe_dispatches == 1
    third = session.advance(req())
    assert third.state == "investigating"
    assert provider.probe_dispatches == 1
    provider.probe_status = "completed"
    final = session.advance(req())
    assert final.state == "report_ready"
    assert final.client_pdf_allowed
    assert final.assessment is not None and final.assessment.report_publishable
    assert provider.actions == 1 and provider.probe_dispatches == 1
    pdf = session.scan.render(
        session.scan.collect(req(), additional_reviews=session.investigation.known_results(
            req(),device_uid=DEVICE)), audience="client")
    assert pdf.startswith(b"%PDF-")


def test_unknown_low_stays_internal_and_never_all_clear(tmp_path):
    session,provider,_=create(tmp_path)
    provider.stdout=output([HUNT, MAPS], bounded=True)
    session.advance(req(),approval_bound_arguments=approval())
    provider.job_status="completed"
    session.advance(req())
    provider.probe_status="completed"
    result=session.advance(req())
    assert not result.client_pdf_allowed
    assert result.state=="human_review"
    assert result.assessment is not None
    assert not result.assessment.report_publishable
    with __import__("pytest").raises(ReportNotPublishable):
        render_security_pdf(result.assessment,audience="client")
    assert render_security_pdf(result.assessment,audience="technician").startswith(b"%PDF-")
    assert provider.actions==1
