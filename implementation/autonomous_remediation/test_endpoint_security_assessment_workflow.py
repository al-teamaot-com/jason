"""Governance/idempotency/restart acceptance tests; all provider calls mocked."""
from __future__ import annotations

from dataclasses import replace
import json
import sqlite3

import pytest

from .endpoint_security_assessment import (
    RawFinding, Disposition,
)
from .endpoint_security_assessment_workflow import (
    AssessmentGovernanceError, AssessmentProviderError, AssessmentRequest,
    COMPONENT_NAME, COMPONENT_UID, GovernedAssessmentCoordinator,
    SqliteAssessmentState,
)
from .test_endpoint_security_assessment import HOST, JOB, HUNT, LENOVO_A, LENOVO_B, \
    output, verified

DEVICE = "fa38813a-91c4-b2e8-201a-4801f5e3aab2"
SITE = "f9b77373-c8d0-4219-a4de-215f81e08537"
CALLER = "authenticated-teams-tech-principal"


def req(key="chat-turn:1"):
    return AssessmentRequest(request_id=key, organization_id="AOT",
                             client_site_uid=SITE, hostname=HOST,
                             requester_identity=CALLER)


def approval():
    # The test port simulates an already-valid Central Orchestrator approval.
    # The workflow itself must never invent or upgrade this context.
    return {"device_uid": DEVICE, "component_uid": COMPONENT_UID,
            "component_name": COMPONENT_NAME, "explicit_approval": True,
            "jason_remediation_review": {"decision": "recommend",
                "evidence_refs": ["trusted-governance-evidence"]}}


class MockGovernedPort:
    def __init__(self, *, read_body=None):
        self.calls = []
        self.actions = 0
        self.online = True
        self.site = SITE
        self.job_status = "active"
        self.reject_component = False
        self.job_component_uid = COMPONENT_UID
        self.av_status = "RunningAndUpToDate"
        self.stdout = output([HUNT, LENOVO_A, LENOVO_B])
        self.stderr = ""
        self.output_resource_override = None

    def _ok(self, evidence):
        return {"status": "succeeded", "evidence": evidence}

    def read(self, capability, arguments):
        self.calls.append(("read", capability, dict(arguments)))
        if capability == "endpoint.device.search":
            return self._ok({"resource_matches": [
                {"hostname": HOST, "site_id": self.site, "resource_id": DEVICE}
            ]})
        if capability == "endpoint.device.read":
            return self._ok({"record": {
                "resource_id": DEVICE, "hostname": HOST, "site_id": self.site,
                "site": "Robert B. Hansen", "online": self.online,
                "deleted": False, "suspended": False,
                "antivirus": {"antivirusProduct": "Datto AV",
                              "antivirusStatus": self.av_status},
            }})
        if capability == "automation.component.search":
            return self._ok({"resource_matches": (
                [] if self.reject_component else
                [{"resource_id": COMPONENT_UID, "name": COMPONENT_NAME}]
            )})
        if capability == "automation.job.read":
            return self._ok({"data": {"job": {
                "resource_id": JOB, "status": self.job_status
            }}})
        if capability == "automation.job.output.read":
            return self._ok({"data": {
                "resource_id": self.output_resource_override or JOB,
                "device_uid": DEVICE, "component_uid": COMPONENT_UID,
                "match_count": 1,
                "outputs": [{
                    "component_uid": COMPONENT_UID,
                    "text": self.stdout if arguments.get("stream") == "stdout"
                    else self.stderr,
                }],
            }})
        raise AssertionError(f"unexpected governed read: {capability}")

    def action(self, capability, arguments):
        self.calls.append(("action", capability, dict(arguments)))
        assert capability == "automation.component.execute"
        self.actions += 1
        return {"status": "succeeded", "result": {
            "status": "accepted", "job_uid": JOB, "device_uid": DEVICE,
            "component_uid": self.job_component_uid,
        }}


def setup(tmp_path, port=None):
    p = port or MockGovernedPort()
    path = tmp_path / "assessment.db"
    return GovernedAssessmentCoordinator(p, SqliteAssessmentState(path)), p, path


def test_one_technician_request_persists_one_job_and_restarts(tmp_path):
    flow, provider, path = setup(tmp_path)
    r = req()
    assert flow.prepare(r).state == "waiting_approval"
    assert flow.dispatch(r, approval_bound_arguments=None).state == "waiting_approval"
    first = flow.dispatch(r, approval_bound_arguments=approval())
    assert first.job_uid == JOB and provider.actions == 1
    # Repeated turn, retried request, fresh coordinator: zero duplicate jobs.
    another = GovernedAssessmentCoordinator(provider, SqliteAssessmentState(path))
    assert another.dispatch(r, approval_bound_arguments=approval()).job_uid == JOB
    assert provider.actions == 1
    wait = another.collect(r)
    assert wait.state == "waiting_job" and not wait.report_ready
    provider.job_status = "completed"
    done = another.collect(r, additional_reviews=[
        verified("HUNTAgent"),
        verified("VantageCoreAddinIdleScheduleTask"),
        verified("LenovoMachineFixUser_OOBE_AUTO_Notification"),
    ])
    assert done.state == "report_ready" and done.report_ready
    assert done.assessment is not None and done.assessment.report_publishable
    assert provider.actions == 1
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT job_uid,state,observed_json FROM endpoint_security_assessment").fetchone()
    assert row[0] == JOB and row[1] == "report_ready"
    assert json.loads(row[2])["report_publishable"] is True


def test_cross_client_search_fails_closed(tmp_path):
    flow, provider, _ = setup(tmp_path)
    provider.site = "unrelated-client-site"
    with pytest.raises(AssessmentGovernanceError, match="CROSS_CLIENT"):
        flow.prepare(req())
    assert provider.actions == 0


def test_target_or_approval_mismatch_rejects_before_action(tmp_path):
    flow, provider, _ = setup(tmp_path)
    flow.prepare(req())
    for args in (
        dict(approval(), device_uid="wrong-device"),
        dict(approval(), component_uid="wrong-component"),
        dict(approval(), explicit_approval=False),
    ):
        with pytest.raises(AssessmentGovernanceError):
            flow.dispatch(req(), approval_bound_arguments=args)
    assert provider.actions == 0


def test_component_not_found_fails_closed(tmp_path):
    flow, provider, _ = setup(tmp_path)
    provider.reject_component = True
    with pytest.raises(AssessmentGovernanceError, match="EXACT_COMPONENT"):
        flow.prepare(req())
    assert provider.actions == 0


def test_offline_device_does_not_dispatch_even_with_args(tmp_path):
    flow, provider, _ = setup(tmp_path)
    provider.online = False
    assert flow.prepare(req()).state == "waiting_device"
    with pytest.raises(AssessmentGovernanceError):
        flow.dispatch(req(), approval_bound_arguments=approval())
    assert provider.actions == 0


def test_offline_device_can_be_resumed_with_fresh_verified_read(tmp_path):
    flow,provider,_=setup(tmp_path)
    provider.online=False
    assert flow.prepare(req()).state=="waiting_device"
    provider.online=True
    # Fresh read with same exact UID and verified site, not a new device search.
    assert flow.prepare(req()).state=="waiting_approval"
    assert provider.actions==0


def test_reused_id_for_different_client_or_requester_blocked(tmp_path):
    flow, provider, _ = setup(tmp_path)
    flow.prepare(req())
    with pytest.raises(AssessmentGovernanceError, match="REQUEST_ID_REUSED"):
        flow.prepare(replace(req(), client_site_uid="different"))
    with pytest.raises(AssessmentGovernanceError, match="REQUEST_ID_REUSED"):
        flow.prepare(replace(req(), requester_identity="other"))
    assert provider.actions == 0


def test_ambiguous_acceptance_blocks_second_dispatch(tmp_path):
    flow, provider, _ = setup(tmp_path)
    flow.prepare(req())
    provider.job_component_uid = "wrong-component"
    with pytest.raises(AssessmentProviderError, match="INCOMPLETE"):
        flow.dispatch(req(), approval_bound_arguments=approval())
    with pytest.raises(AssessmentGovernanceError, match="DEVICE_NOT_READY"):
        flow.dispatch(req(), approval_bound_arguments=approval())
    assert provider.actions == 1


def test_job_output_mismatch_is_error_not_new_job(tmp_path):
    flow, provider, _ = setup(tmp_path)
    flow.prepare(req())
    flow.dispatch(req(), approval_bound_arguments=approval())
    provider.job_status = "completed"
    provider.output_resource_override = "different-job"
    with pytest.raises(AssessmentProviderError, match="SELECTORS_MISMATCH"):
        flow.collect(req())
    assert provider.actions == 1


def test_unresolved_low_or_bounded_output_stays_internal(tmp_path):
    flow, provider, _ = setup(tmp_path)
    flow.prepare(req())
    flow.dispatch(req(), approval_bound_arguments=approval())
    provider.job_status = "completed"
    provider.stdout = output([HUNT, LENOVO_A, LENOVO_B, RawFinding(
        "Low","StartupFile","MapS.bat","startup batch file",
        r"C:\Users\LisaWalker\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\MapS.bat")],
        bounded=True)
    result = flow.collect(req(), additional_reviews=[
        verified("HUNTAgent"), verified("VantageCoreAddinIdleScheduleTask"),
        verified("LenovoMachineFixUser_OOBE_AUTO_Notification")])
    assert result.state == "investigating"
    assert not result.report_ready and result.assessment is not None
    assert result.assessment.unresolved_detail_count >= 1
    assert provider.actions == 1


def test_failed_job_does_not_trigger_automatic_retry(tmp_path):
    flow, provider, _ = setup(tmp_path)
    flow.prepare(req())
    flow.dispatch(req(), approval_bound_arguments=approval())
    provider.job_status = "failed"
    result = flow.collect(req())
    assert result.state == "human_review" and provider.actions == 1


def test_wait_bound_is_not_an_endless_loop(tmp_path):
    flow, provider, _ = setup(tmp_path)
    flow.prepare(req())
    flow.dispatch(req(), approval_bound_arguments=approval())
    for i in range(35):
        assert flow.collect(req()).state == "waiting_job"
    with pytest.raises(AssessmentProviderError, match="JOB_POLL_LIMIT"):
        flow.collect(req())
    assert provider.actions == 1


def test_all_actions_are_governed_and_bounded(tmp_path):
    flow, provider, _ = setup(tmp_path)
    flow.prepare(req())
    flow.dispatch(req(), approval_bound_arguments=approval())
    assert provider.actions == 1
    allowed = {"endpoint.device.search", "endpoint.device.read",
        "automation.component.search", "automation.component.execute"}
    assert {x[1] for x in provider.calls} == allowed
    # The coordinator requires a trusted existing per-request approval;
    # missing approval never triggers even one action (covered above).
    assert any(call[2].get("explicit_approval") is True
               for call in provider.calls if call[0] == "action")
