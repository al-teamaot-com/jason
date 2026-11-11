"""Fail-closed tests for the reusable Endpoint Security Assessment domain."""
from __future__ import annotations

from dataclasses import replace
import json
import pytest

from .endpoint_security_assessment import (
    AssessmentStage, Disposition, EvidenceReview, RawFinding, classify_finding,
    parse_sweep_output, reconcile_assessment,
)

COMPONENT = "8ff72744-cb29-4cad-a11b-7a1c2a199f06"
HOST = "CCPC-50960"
JOB = "119676ad-2cad-4bed-a69a-60aa88ad98c8"
BASE_SCANNED = {
    "processes": 258, "established_tcp": 16, "services": 305,
    "scheduled_tasks": 304, "autorun_values": 15,
    "startup_files": 1, "wmi_consumers": 0,
    "installed_programs": 29, "defender_detections": 0,
}
HUNT = RawFinding(
    "Medium", "Service", "HUNTAgent",
    "Persistent service in writable location or suspicious command",
    r"C:\ProgramData\CentraStage\AEMAgent\RMM.AdvancedThreatDetection\agent.exe",
    ("job:" + JOB,),
)
LENOVO_A = RawFinding(
    "Medium", "ScheduledTask", "VantageCoreAddinIdleScheduleTask",
    "Scheduled persistence using writable path or suspicious arguments",
    r"C:\ProgramData\Lenovo\Vantage\Addins\VantageCoreAddin\1.1.0.67\x86\IdleScheduleEventAction.exe",
    ("job:" + JOB,),
)
LENOVO_B = RawFinding(
    "Medium", "ScheduledTask", "LenovoMachineFixUser_OOBE_AUTO_Notification",
    "Scheduled persistence using writable path or suspicious arguments",
    r"C:\ProgramData\Lenovo\Vantage\Addins\LenovoMachineFixUserAddin\1.0.10.608\ScheduleEventAction.exe",
    ("job:" + JOB,),
)
MAPS = RawFinding(
    "Low", "StartupFile", "MapS.bat", "Startup file with executable extension",
    r"C:\Users\LisaWalker\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\MapS.bat",
    ("job:" + JOB,),
)


def verified(name: str) -> EvidenceReview:
    if name == "HUNTAgent":
        return EvidenceReview(name=name, source="service", executable=HUNT.path,
            signature_status="Valid",
            signer_subject='CN="Datto, LLC", O="Datto, LLC", C=US',
            service_display_name="Datto EDR Agent", service_state="Running",
            service_start_mode="Auto", arguments="--service",
            evidence_refs=("diagnostic:Datto-EDR",))
    if name == LENOVO_A.name:
        return EvidenceReview(name=name, source="scheduled_task",
            executable=LENOVO_A.path, signature_status="Valid",
            signer_subject="CN=Lenovo, O=Lenovo, C=US",
            task_path=r"\Lenovo\Vantage\Schedule\\",
            evidence_refs=("diagnostic:Vantage-idle",))
    if name == LENOVO_B.name:
        return EvidenceReview(name=name, source="scheduled_task",
            executable=LENOVO_B.path, signature_status="Valid",
            signer_subject="CN=Lenovo, O=Lenovo, C=US",
            task_path=r"\Lenovo\\", arguments=f'"{LENOVO_B.name}"',
            evidence_refs=("diagnostic:Vantage-oobe",))
    raise ValueError("unknown test fixture")


def output(findings=(), *, bounded=False, status="complete", omitted=0):
    severity = {s: sum(f.severity == s for f in findings) for s in ("High", "Medium", "Low", "Info")}
    summary = dict(high=severity["High"], medium=severity["Medium"],
                   low=severity["Low"], info=severity["Info"],
                   omitted_findings=omitted, sections_with_errors=0)
    info = dict(
        schema_version="1.0", collector="AOT-Hidden-RAT-Threat-Sweep",
        read_only=True, computer=HOST, collection_status=status,
        summary=summary, scanned=dict(BASE_SCANNED),
        findings=[
            dict(severity=f.severity, category=f.category, name=f.name,
                 title=f.title, path=f.path)
            for f in findings
        ],
    )
    lines = ["<-Start Result->",
        f"AOT Security Sweep | Computer={HOST} | Collection={status} | DurationSec=6.9",
        ("Findings | High={High} Medium={Medium} Low={Low} Info={Info} "
         "Omitted={Omitted}").format(**severity, Omitted=omitted),
        ("Coverage | DefenderAV=inactive Preferences=skipped_inactive "
         "DefenderDetections=collected SignedSecurityInventory=6"),
    ]
    if bounded:
        lines.extend([
            f"REVIEW [{f.severity}] {f.category} - {f.title} - {f.name} - {f.path}"
            for f in findings if f.severity in ("High", "Medium")
        ])
    lines.extend(["AOT_SECURITY_JSON_BEGIN",
                  json.dumps(info, separators=(",", ":")) if not bounded else
                  json.dumps(info, separators=(",", ":"))[:650] + "...[bounded]"])
    if not bounded:
        lines.append("AOT_SECURITY_JSON_END")
    return "\n".join(lines) + "\n"


def parse(text):
    return parse_sweep_output(hostname=HOST, job_uid=JOB, stdout=text,
        stderr="", job_status="completed", component_uid=COMPONENT,
        evidence_refs=("job:"+JOB,))


def assessment(scan, reviews=()):
    return reconcile_assessment(
        company="Robert B. Hansen", site_uid="site:rbh",
        device_uid="device:ccpc", device_hostname=HOST,
        antivirus={"antivirusProduct": "Datto AV",
                   "antivirusStatus": "RunningAndUpToDate"},
        sweep=scan, reviews=reviews)


def test_full_json_and_all_findings_verified_rule_only():
    s = parse(output([LENOVO_A, LENOVO_B, HUNT]))
    assert s.finding_detail_complete and not s.raw_output_bounded
    assert s.inventory["processes"] == 258
    a = assessment(s, [verified(x.name) for x in (LENOVO_A, LENOVO_B, HUNT)])
    assert a.report_publishable
    assert a.status == "no_elevated_indicators_identified"
    assert [x.disposition for x in a.reviewed] == [Disposition.VERIFIED_EXPECTED] * 3
    assert a.antivirus_status == "RunningAndUpToDate"


def test_bounded_data_blocks_unfounded_client_all_clear():
    s = parse(output([LENOVO_A, LENOVO_B, HUNT, MAPS], bounded=True))
    assert s.raw_output_bounded and not s.finding_detail_complete
    a = assessment(s, [verified(x.name) for x in (LENOVO_A, LENOVO_B, HUNT)])
    assert not a.report_publishable
    assert a.unresolved_detail_count >= 1
    assert a.status == "assessment_incomplete"


@pytest.mark.parametrize("bad", [
    replace(verified("HUNTAgent"), signature_status="NotSigned"),
    replace(verified("HUNTAgent"), signer_subject="O=Evil Software"),
    replace(verified("HUNTAgent"), executable=r"C:\Users\Public\agent.exe"),
    replace(verified("HUNTAgent"), arguments="--service --danger"),
    replace(verified("HUNTAgent"), service_state="Stopped"),
    replace(verified("HUNTAgent"), evidence_refs=()),
    replace(verified("HUNTAgent"), service_display_name="UnknownAgent"),
])
def test_huntagent_fails_closed_without_every_trust_condition(bad):
    assert classify_finding(HUNT, (bad,)).disposition == Disposition.UNRESOLVED


@pytest.mark.parametrize("bad", [
    replace(verified(LENOVO_A.name), signature_status="NotSigned"),
    replace(verified(LENOVO_A.name), signer_subject="O=Other Vendor"),
    replace(verified(LENOVO_A.name), executable=r"C:\Users\Public\IdleScheduleEventAction.exe"),
    replace(verified(LENOVO_A.name), task_path=r"\Other\\"),
    replace(verified(LENOVO_A.name), arguments="-EncodedCommand suspicious"),
])
def test_lenovo_fails_closed_on_masquerade_or_suspicious_args(bad):
    assert classify_finding(LENOVO_A, (bad,)).disposition == Disposition.UNRESOLVED


def test_unknown_low_batch_file_never_marked_trusted_from_name():
    review = EvidenceReview(name="MapS.bat", source="startup_file",
        executable=MAPS.path, signature_status="Valid",
        signer_subject="CN=Microsoft Corporation, O=Microsoft Corporation",
        evidence_refs=("diagnostic:file",))
    assert classify_finding(MAPS, (review,)).disposition == Disposition.UNRESOLVED


def test_valid_component_not_sufficient_if_av_status_unknown():
    scan = parse(output([HUNT]))
    a = reconcile_assessment(company="Client",site_uid="site",device_uid="device",
        device_hostname=HOST,antivirus={"antivirusProduct":"Datto AV",
        "antivirusStatus":"Unknown"},sweep=scan,reviews=(verified("HUNTAgent"),))
    assert not a.report_publishable and a.status == "assessment_incomplete"


def test_job_readback_and_identity_is_obligatory():
    text = output()
    for kwargs in (
        {"job_status":"active"},
        {"component_uid":"different"},
        {"hostname":"different"},
        {"stderr":"Security warning"},
        {"job_uid":""},
    ):
        arguments=dict(hostname=HOST,job_uid=JOB,stdout=text,stderr="",
                       job_status="completed",component_uid=COMPONENT)
        arguments.update(kwargs)
        with pytest.raises(ValueError):
            parse_sweep_output(**arguments)


def test_summary_conflict_and_missing_json_fail_closed():
    text = output([HUNT])
    with pytest.raises(ValueError, match="FINDING_SUMMARY_CONFLICT"):
        parse(text.replace('"medium":1', '"medium":0'))
    with pytest.raises(ValueError, match="STRUCTURED_REPORT_MISSING"):
        parse(text.replace("AOT_SECURITY_JSON_BEGIN", "NotAReport"))


def test_incomplete_source_never_publishable():
    scan = parse(output([], status="partial"))
    assert not assessment(scan).report_publishable
    assert assessment(scan).status == "assessment_incomplete"


def test_omitted_findings_never_publishable():
    s = parse(output([], omitted=1))
    assert not assessment(s).report_publishable


def test_duplicate_conflicting_review_evidence_fails_closed():
    findings = (HUNT,)
    results = [verified("HUNTAgent"), replace(verified("HUNTAgent"), signature_status="NotSigned")]
    a = assessment(parse(output(findings)), results)
    assert not a.report_publishable


def test_provider_is_not_invoked_by_evaluator():
    assert all(
        name not in globals()
        for name in ("requests", "subprocess", "DattoRmmClient")
    )



def test_actual_datto_v2_header_without_coverage_line_is_supported():
    # 2026-11-04 live Al / Al-Samsung output emitted incomplete sections,
    # not a Coverage summary. Never invent Defender preference success.
    fixture = output([HUNT], bounded=True, status="partial")
    fixture = fixture.replace(
        "Coverage | DefenderAV=inactive Preferences=skipped_inactive "
        "DefenderDetections=collected SignedSecurityInventory=6",
        "Incomplete sections: DefenderPreference",
    ).replace('"sections_with_errors":0', '"sections_with_errors":1')
    parsed = parse(fixture)
    assert parsed.collection_status == "partial"
    assert parsed.defender["DefenderAV"] == "not_reported"
    assert parsed.defender["Preferences"] == "incomplete"
    assert parsed.error_sections == 1
    assert not assessment(parsed).report_publishable
