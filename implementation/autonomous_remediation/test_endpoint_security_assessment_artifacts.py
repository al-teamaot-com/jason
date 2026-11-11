"""PDF artifact integrity, isolation and publication authorization tests."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import pytest

pytest.importorskip("reportlab")
from .endpoint_security_assessment_artifacts import PrivateAssessmentArtifactStore
from .endpoint_security_assessment_workflow import AssessmentGovernanceError
from .test_endpoint_security_assessment import (
    HUNT, LENOVO_A, LENOVO_B, MAPS, output, verified,
)
from .test_endpoint_security_assessment_workflow import (
    MockGovernedPort, approval, req, setup,
)


def ready(tmp_path, *, unresolved=False):
    port=MockGovernedPort()
    flow,_,db=setup(tmp_path,port)
    flow.prepare(req())
    flow.dispatch(req(),approval_bound_arguments=approval())
    port.job_status="completed"
    findings=[HUNT,LENOVO_A,LENOVO_B]+([MAPS] if unresolved else [])
    port.stdout=output(findings)
    progress=flow.collect(req(),additional_reviews=[
        verified(v.name) for v in (HUNT,LENOVO_A,LENOVO_B)])
    store=PrivateAssessmentArtifactStore(str(db),tmp_path/"private_report_files")
    return store,progress,port


def test_technician_can_retrieve_their_own_verified_content_addressed_pdf(tmp_path):
    store,progress,port=ready(tmp_path)
    assert progress.report_ready
    ref=store.publish(req(),progress=progress,audience="client",
                      bound_requester=req().requester_identity)
    body=store.retrieve(req(),reference=ref,
                        bound_requester=req().requester_identity)
    assert body.startswith(b"%PDF-")
    assert len(body)>1500
    assert ref.sha256==__import__("hashlib").sha256(body).hexdigest()
    assert ref==store.publish(req(),progress=progress,audience="client",
                              bound_requester=req().requester_identity)
    files=list((tmp_path/"private_report_files").glob("*.pdf"))
    assert len(files)==1
    assert os.stat(files[0]).st_mode & 0o077 == 0
    assert port.actions==1


def test_client_report_cannot_be_published_with_unresolved_low(tmp_path):
    store,progress,_=ready(tmp_path,unresolved=True)
    assert not progress.report_ready
    with pytest.raises(AssessmentGovernanceError,match="CLIENT_PDF_NOT_VERIFIED"):
        store.publish(req(),progress=progress,audience="client",
                      bound_requester=req().requester_identity)
    ref=store.publish(req(),progress=progress,audience="technician",
                      bound_requester=req().requester_identity)
    assert store.retrieve(req(),reference=ref,bound_requester=req().requester_identity).startswith(b"%PDF-")


def test_cross_client_and_other_principal_cannot_access_artifact(tmp_path):
    store,progress,_=ready(tmp_path)
    ref=store.publish(req(),progress=progress,audience="client",
                      bound_requester=req().requester_identity)
    with pytest.raises(AssessmentGovernanceError):
        store.retrieve(req(),reference=ref,bound_requester="different-authenticated-technician")
    with pytest.raises(AssessmentGovernanceError):
        store.retrieve(replace(req(),client_site_uid="other-client"),
                       reference=ref,bound_requester=req().requester_identity)
    with pytest.raises(AssessmentGovernanceError):
        store.retrieve(replace(req(),request_id="other-request"),
                       reference=ref,bound_requester=req().requester_identity)


def test_artifact_tampering_fails_integrity_readback(tmp_path):
    store,progress,_=ready(tmp_path)
    ref=store.publish(req(),progress=progress,audience="client",
                      bound_requester=req().requester_identity)
    (tmp_path/"private_report_files"/(ref.sha256+".pdf")).write_bytes(b"%PDF-FAKE")
    with pytest.raises(RuntimeError,match="INTEGRITY"):
        store.retrieve(req(),reference=ref,bound_requester=req().requester_identity)
