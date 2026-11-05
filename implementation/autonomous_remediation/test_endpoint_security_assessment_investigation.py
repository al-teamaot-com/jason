"""Prove static-read recipe, evidence binding, and job-idempotent investigation."""
from __future__ import annotations

import json
import pytest

from .endpoint_security_assessment import (
    RawFinding, classify_finding, Disposition,
)
from .endpoint_security_assessment_investigation import (
    ReadOnlyInvestigator, available_recipe, normalize_investigation_output,
)
from .endpoint_security_assessment_workflow import (
    AssessmentGovernanceError, AssessmentProviderError,
)
from .test_endpoint_security_assessment import (
    HUNT, LENOVO_A, LENOVO_B, MAPS, output,
)
from .test_endpoint_security_assessment_workflow import (
    MockGovernedPort, DEVICE, approval, req, setup,
)

PROBE_JOB = "authoritative-readonly-probe-job"


def probe_output(finding, *, valid=True):
    if finding.name == HUNT.name:
        identity = dict(Name=HUNT.name, DisplayName="Datto EDR Agent",
                        State="Running", StartMode="Auto",
                        PathName=HUNT.path + " --service")
        path = HUNT.path
        signer = 'CN="Datto, LLC", O="Datto, LLC"'
    elif finding.name in (LENOVO_A.name, LENOVO_B.name):
        identity = dict(TaskName=finding.name,
                        TaskPath=r"\Lenovo\Vantage\Schedule\\"
                        if finding.name == LENOVO_A.name else r"\Lenovo\\",
                        executable=finding.path,
                        arguments="" if finding.name == LENOVO_A.name
                        else f'"{LENOVO_B.name}"')
        path = finding.path
        signer = "CN=Lenovo, O=Lenovo, C=US"
    else:
        raise ValueError("unsupported fixture")
    signature = dict(Path=path,
                     signature_status="Valid" if valid else "NotSigned",
                     signer_subject=signer)
    return ("Run Ad-Hoc PowerShell Command\n"
            "=======================================\n"
            + json.dumps(identity, separators=(",", ":")) + "\n"
            + json.dumps(signature, separators=(",", ":")) + "\n"
            "- Command run.\n  The exit code was 0.\n")


class ProbePort(MockGovernedPort):
    def __init__(self):
        super().__init__()
        self.probe_dispatches = 0
        self.probe_status = "active"
        self.probe_stdout = probe_output(HUNT)
        self.probe_stderr = ""

    def read(self, capability, arguments):
        if capability == "endpoint.powershell.read":
            self.probe_dispatches += 1
            self.calls.append(("read",capability,dict(arguments)))
            assert arguments["device_uid"] == DEVICE
            assert "Set-Service" not in arguments["command"]
            assert "Start-Process" not in arguments["command"]
            return {"status":"succeeded","evidence":{"data":{
                "status":"accepted", "job_uid":PROBE_JOB,
                "device_uid":DEVICE,
                "component_uid":"8a1c153c-feee-41c5-9c9b-58a48e0214fe"}}}
        if capability == "automation.job.read" and arguments.get("resource_id") == PROBE_JOB:
            return {"status":"succeeded","evidence":{"data":{
                "job":{"resource_id":PROBE_JOB,"status":self.probe_status}}}}
        if capability == "automation.job.output.read" and arguments.get("resource_id") == PROBE_JOB:
            stream=arguments["stream"]
            return {"status":"succeeded","evidence":{"data":{
                "resource_id":PROBE_JOB,
                "device_uid":DEVICE,
                "component_uid":"8a1c153c-feee-41c5-9c9b-58a48e0214fe",
                "match_count":1,
                "outputs":[{"component_uid":"8a1c153c-feee-41c5-9c9b-58a48e0214fe",
                            "text":self.probe_stdout if stream=="stdout"
                            else self.probe_stderr}]}}}
        return super().read(capability,arguments)


def make_investigator(tmp_path):
    port=ProbePort()
    coordinator,_,path=setup(tmp_path,port)
    coordinator.prepare(req())
    coordinator.dispatch(req(),approval_bound_arguments=approval())
    port.job_status="completed"
    port.stdout=output([HUNT,LENOVO_A,LENOVO_B],bounded=True)
    assert coordinator.collect(req()).state=="investigating"
    inv=ReadOnlyInvestigator(port,str(path))
    return inv,port,path


def test_readonly_investigation_deduplicates_and_survives_restart(tmp_path):
    inv,port,path=make_investigator(tmp_path)
    assert inv.dispatch_probe(req(),device_uid=DEVICE,finding=HUNT)==PROBE_JOB
    assert inv.dispatch_probe(req(),device_uid=DEVICE,finding=HUNT)==PROBE_JOB
    assert port.probe_dispatches==1
    assert inv.poll_probe(req(),device_uid=DEVICE,finding=HUNT) is None
    port.probe_status="completed"
    evidence=inv.poll_probe(req(),device_uid=DEVICE,finding=HUNT)
    assert evidence.name=="HUNTAgent"
    assert evidence.evidence_refs==("datto-rmm:job:"+PROBE_JOB,)
    assert classify_finding(HUNT,(evidence,)).disposition==Disposition.VERIFIED_EXPECTED
    after=ReadOnlyInvestigator(port,str(path))
    assert after.poll_probe(req(),device_uid=DEVICE,finding=HUNT)==evidence
    assert after.known_results(req(),device_uid=DEVICE)==(evidence,)
    assert port.probe_dispatches==1


def test_lenovo_recipes_verified_without_generating_unrestricted_commands(tmp_path):
    for f in (LENOVO_A,LENOVO_B):
        case_dir=tmp_path / f.name
        case_dir.mkdir()
        inv,port,_=make_investigator(case_dir)
        assert available_recipe(f)
        port.probe_stdout=probe_output(f)
        inv.dispatch_probe(req(),device_uid=DEVICE,finding=f)
        port.probe_status="completed"
        evidence=inv.poll_probe(req(),device_uid=DEVICE,finding=f)
        assert classify_finding(f,(evidence,)).disposition==Disposition.VERIFIED_EXPECTED
        assert port.probe_dispatches==1


def test_unknown_user_batch_file_does_not_create_generic_shell_probe(tmp_path):
    inv,port,_=make_investigator(tmp_path)
    assert not available_recipe(MAPS)
    assert inv.dispatch_probe(req(),device_uid=DEVICE,finding=MAPS) is None
    assert port.probe_dispatches==0


def test_invalid_signature_stays_unresolved(tmp_path):
    inv,port,_=make_investigator(tmp_path)
    port.probe_stdout=probe_output(HUNT,valid=False)
    inv.dispatch_probe(req(),device_uid=DEVICE,finding=HUNT)
    port.probe_status="completed"
    ev=inv.poll_probe(req(),device_uid=DEVICE,finding=HUNT)
    assert classify_finding(HUNT,(ev,)).disposition==Disposition.UNRESOLVED


def test_service_command_conflict_blocks_evidence_proof():
    raw=probe_output(HUNT).replace("agent.exe --service","agent.exe --unsafe")
    with pytest.raises(AssessmentProviderError, match="SERVICE_COMMAND_CONFLICT"):
        normalize_investigation_output(
            expected_finding=HUNT,stdout=raw,stderr="",job_uid=PROBE_JOB)


def test_cross_client_or_unprepared_probe_request_rejected(tmp_path):
    port=ProbePort()
    path=tmp_path/"assessment.db"
    inv=ReadOnlyInvestigator(port,str(path))
    with pytest.raises(AssessmentGovernanceError, match="BOUND"):
        inv.dispatch_probe(req(),device_uid=DEVICE,finding=HUNT)
    assert port.probe_dispatches==0


def test_denied_or_failing_probe_fails_closed_without_retry(tmp_path):
    inv,port,_=make_investigator(tmp_path)
    inv.dispatch_probe(req(),device_uid=DEVICE,finding=HUNT)
    port.probe_status="failed"
    with pytest.raises(AssessmentProviderError, match="JOB_FAILED"):
        inv.poll_probe(req(),device_uid=DEVICE,finding=HUNT)
    assert port.probe_dispatches==1
    with pytest.raises(AssessmentGovernanceError):
        inv.poll_probe(req(),device_uid=DEVICE,finding=HUNT)



@pytest.mark.parametrize("finding", [HUNT, LENOVO_A, LENOVO_B])
def test_real_datto_readonly_classifier_permits_exact_static_recipes(finding):
    from connectors.datto_rmm.readonly_powershell import ReadOnlyPowerShellClassifier
    from .endpoint_security_assessment_investigation import _RECIPES
    command = _RECIPES[finding.name][1]
    result = ReadOnlyPowerShellClassifier.classify(command)
    assert result.allowed_as_read_only, (finding.name, result.reasons)
    assert not result.active_probe
    assert not result.sensitive
    assert "$t=" not in command
    assert "Write-Output" not in command


def test_signature_must_match_exact_task_action_executable():
    raw = probe_output(LENOVO_A).replace(
        '"Path":"'+LENOVO_A.path.replace(chr(92), chr(92)*2)+'"',
        '"Path":"C:\\\\Users\\\\Public\\\\unrelated.exe"'
    )
    with pytest.raises(AssessmentProviderError, match="SIGNATURE_TARGET_MISMATCH"):
        normalize_investigation_output(
            expected_finding=LENOVO_A, stdout=raw, stderr="", job_uid=PROBE_JOB)
