"""Provider-neutral evidence reconciliation for a governed endpoint security assessment.

No provider calls, credential access, script execution, malware removal or client
communications are made here.  Caller supplies *already authorized* observations.
A heuristic warning is never silently suppressed, and an incomplete/bounded result
cannot be converted into a reassuring client-facing all-clear.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import re
from typing import Any, Mapping, Sequence


_SWEEP_HEADER = re.compile(
    r"^AOT Security Sweep \| Computer=(?P<name>[^|]+) \| "
    r"Collection=(?P<status>complete|partial|failed) \| DurationSec=\d+(?:\.\d+)?$"
)
_COUNT = re.compile(
    r"^Findings \| High=(\d+) Medium=(\d+) Low=(\d+) Info=(\d+) Omitted=(\d+)$"
)
_COVERAGE = re.compile(r"^Coverage \| (?P<fields>.+)$")
_REVIEW = re.compile(
    r"^REVIEW \[(High|Medium|Low|Info)\] ([^-]+?) - (.*?) - (.*?) - (.+)$"
)
_NUMERIC_KEYS = ("processes", "established_tcp", "services", "scheduled_tasks",
                 "autorun_values", "startup_files", "wmi_consumers",
                 "installed_programs", "defender_detections")
_ALLOWED_CATEGORIES = {"High", "Medium", "Low", "Info"}
_MAX_FINDINGS = 300
_MAX_OUTPUT = 65536


class AssessmentStage(str, Enum):
    WAITING_DEVICE = "waiting_device"
    WAITING_APPROVAL = "waiting_approval"
    DISPATCHED = "dispatched"
    WAITING_JOB = "waiting_job"
    INVESTIGATING = "investigating"
    REVIEW_READY = "review_ready"
    REPORT_READY = "report_ready"
    BLOCKED = "blocked"
    HUMAN_REVIEW = "human_review"
    COMPLETE = "complete"


class Disposition(str, Enum):
    VERIFIED_EXPECTED = "verified_expected"
    CONCERN = "concern"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class RawFinding:
    severity: str
    category: str
    name: str
    title: str
    path: str = ""
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.severity not in _ALLOWED_CATEGORIES or not self.category or not self.name:
            raise ValueError("invalid security finding")


@dataclass(frozen=True)
class EvidenceReview:
    """A bounded normalized investigation result from a governed *read*.

    Matching a friendly filename or signature alone is insufficient.  The
    evidence requires the provider task/service identity, exact execution path,
    valid executable signature and trusted signer. No caller can declare an
    arbitrary finding 'safe' through a boolean or a comment string.
    """
    name: str
    source: str
    executable: str
    signature_status: str
    signer_subject: str
    service_display_name: str = ""
    service_state: str = ""
    service_start_mode: str = ""
    task_path: str = ""
    arguments: str = ""
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewedFinding:
    raw: RawFinding
    disposition: Disposition
    explanation: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SweepObservation:
    hostname: str
    collection_status: str
    counts: Mapping[str, int]
    inventory: Mapping[str, int]
    defender: Mapping[str, str]
    optional_coverage: tuple[str, ...]
    findings: tuple[RawFinding, ...]
    finding_detail_complete: bool
    raw_output_bounded: bool
    error_sections: int
    job_uid: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Assessment:
    hostname: str
    company: str
    site_uid: str
    device_uid: str
    antivirus_product: str
    antivirus_status: str
    sweep: SweepObservation
    reviewed: tuple[ReviewedFinding, ...]
    unresolved_detail_count: int
    status: str
    report_publishable: bool
    limitations: tuple[str, ...]
    evidence_refs: tuple[str, ...]


def _capture_json_object(text: str, name: str) -> Mapping[str, Any] | None:
    match = re.search(r'"' + re.escape(name) + r'":(\{[^{}]*\})', text)
    if not match:
        return None
    data = json.loads(match.group(1))
    if not isinstance(data, Mapping):
        raise ValueError("invalid normalized JSON section")
    return data


def parse_sweep_output(*, hostname: str, job_uid: str, stdout: str,
                       stderr: str, job_status: str, component_uid: str,
                       evidence_refs: Sequence[str] = (),
                       complete_findings: Sequence[RawFinding] | None = None) -> SweepObservation:
    """Validate one *terminal* exact-job output; support bounded JSON excerpts.

    Parsed finding lines are not silently equated with full finding inventory.
    If StdOut/JSON is bounded and low/info lines are absent, report publication
    remains blocked until independent finding-level evidence is supplied.
    """
    if job_status != "completed":
        raise ValueError("JOB_NOT_TERMINAL_COMPLETED")
    if component_uid != "8ff72744-cb29-4cad-a11b-7a1c2a199f06":
        raise ValueError("COMPONENT_IDENTITY_MISMATCH")
    if not job_uid.strip() or not hostname.strip():
        raise ValueError("EXACT_JOB_AND_DEVICE_REQUIRED")
    if stderr.strip():
        raise ValueError("STDERR_NOT_EMPTY_REQUIRES_REVIEW")
    if not stdout or len(stdout) > _MAX_OUTPUT:
        raise ValueError("STDOUT_EMPTY_OR_EXCEEDS_BOUND")
    lines = [line.strip() for line in stdout.splitlines()]
    if not lines or lines[0] != "<-Start Result->":
        raise ValueError("DATTO_RESULT_MARKER_MISSING")
    header = next((m for line in lines if (m := _SWEEP_HEADER.match(line))), None)
    if header is None or header.group("name").casefold() != hostname.casefold():
        raise ValueError("SWEEP_HOSTNAME_MISMATCH_OR_HEADER_MISSING")
    line_counts = next((m for line in lines if (m := _COUNT.match(line))), None)
    if line_counts is None:
        raise ValueError("FINDING_COUNTS_MISSING")
    counts = dict(zip(("High", "Medium", "Low", "Info", "Omitted"),
                      (int(v) for v in line_counts.groups()), strict=True))
    if sum(counts.values()) > _MAX_FINDINGS:
        raise ValueError("FINDING_LIMIT_EXCEEDED")
    coverage_line = next((m for line in lines if (m := _COVERAGE.match(line))), None)
    # The live 2026-11-04 V2 component does not emit a "Coverage |"
    # summary line; its actual output uses "Incomplete sections:"
    # followed by structured JSON. Preserve unknown rather than
    # refusing the whole assessment or inventing collected coverage.
    defender = {
        "DefenderAV": "not_reported",
        "Preferences": "not_reported",
        "DefenderDetections": "count_only",
    }
    if coverage_line:
        for pair in coverage_line.group("fields").split():
            key, sep, value = pair.partition("=")
            if sep:
                defender[key] = value
    for item in lines:
        if item.startswith("Incomplete sections:") and "DefenderPreference" in item:
            defender["Preferences"] = "incomplete"
    if "AOT_SECURITY_JSON_BEGIN" not in lines:
        raise ValueError("STRUCTURED_REPORT_MISSING")

    # Full JSON is preferred, but the chat retrieval gateway currently returns
    # an initial bounded excerpt (~2K chars).  Inventory metadata is in its
    # complete prefix; no concealed details are inferred from that excerpt.
    bounded = ("...[bounded]" in stdout or "AOT_SECURITY_JSON_END" not in lines)
    section = _capture_json_object(stdout, "scanned")
    summary = _capture_json_object(stdout, "summary")
    if section is None or summary is None:
        raise ValueError("STRUCTURED_INVENTORY_OR_SUMMARY_UNAVAILABLE")
    if any(k not in section or not isinstance(section[k], int) or section[k] < 0
           for k in _NUMERIC_KEYS):
        raise ValueError("INVENTORY_COUNTS_INVALID")
    for severity, json_key in (("High", "high"), ("Medium", "medium"),
                               ("Low", "low"), ("Info", "info"),
                               ("Omitted", "omitted_findings")):
        if summary.get(json_key) != counts[severity]:
            raise ValueError("FINDING_SUMMARY_CONFLICT")
    err_sections = summary.get("sections_with_errors")
    if type(err_sections) is not int or err_sections < 0:
        raise ValueError("ERROR_SECTION_COUNT_INVALID")

    raw: list[RawFinding] = []
    for line in lines:
        m = _REVIEW.match(line)
        if not m:
            continue
        sev, cat, title, name, path = m.groups()
        raw.append(RawFinding(sev, cat.strip(), name.strip(), title.strip(),
                              path.strip(), tuple(evidence_refs)))
    complete_detail = False
    if not bounded:
        try:
            beg = stdout.index("AOT_SECURITY_JSON_BEGIN") + len("AOT_SECURITY_JSON_BEGIN")
            end = stdout.index("AOT_SECURITY_JSON_END", beg)
            payload = json.loads(stdout[beg:end])
            if payload.get("computer", "").casefold() != hostname.casefold():
                raise ValueError("FULL_REPORT_HOSTNAME_MISMATCH")
            if payload.get("read_only") is not True:
                raise ValueError("NOT_REPORT_ONLY")
            json_findings = payload.get("findings")
            if not isinstance(json_findings, list):
                raise ValueError("FINDING_ARRAY_REQUIRED")
            raw = [RawFinding(
                severity=str(item["severity"]),
                category=str(item["category"]),
                name=str(item["name"]),
                title=str(item["title"]),
                path=str(item.get("path") or ""),
                evidence_refs=tuple(evidence_refs),
            ) for item in json_findings]
            if len(raw) != (counts["High"] + counts["Medium"] +
                            counts["Low"] + counts["Info"]):
                raise ValueError("FINDING_DETAIL_COUNT_MISMATCH")
            complete_detail = counts["Omitted"] == 0
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("FULL_STRUCTURED_FINDINGS_INVALID") from exc
    if bounded and complete_findings is not None:
        # This supplemental inventory MUST come from the requester-authorized
        # server-side job output projection, not unverified caller-supplied
        # finding names or a general OS inventory.
        full = tuple(complete_findings)
        if (counts["Omitted"] != 0 or
            len(full) != sum(counts[key] for key in ("High","Medium","Low","Info"))):
            raise ValueError("SUPPLEMENTAL_FINDING_COUNT_MISMATCH")
        for severity in ("High","Medium","Low","Info"):
            if sum(item.severity==severity for item in full)!=counts[severity]:
                raise ValueError("SUPPLEMENTAL_FINDING_SEVERITY_CONFLICT")
        for preview in raw:
            # Some V2 preview lines truncate long paths, so require exact
            # finding name/severity/category and a full-path prefix match.
            if not any(
                item.name == preview.name
                and item.severity == preview.severity
                and item.category.casefold() == preview.category.casefold()
                and (not preview.path or
                     item.path.casefold().startswith(preview.path.casefold()))
                for item in full
            ):
                raise ValueError("SUPPLEMENTAL_FINDINGS_CONFLICT_WITH_STDOUT")
        if any(f"datto-rmm:job:{job_uid}" not in item.evidence_refs for item in full):
            raise ValueError("SUPPLEMENTAL_FINDINGS_NOT_JOB_BOUND")
        raw=list(full)
        complete_detail=True
    return SweepObservation(
        hostname=hostname,
        collection_status=header.group("status"),
        counts=counts, inventory=dict(section),
        defender=defender,
        optional_coverage=tuple(
            line for line in lines if line.startswith("Optional coverage:")
        ),
        findings=tuple(raw),
        finding_detail_complete=complete_detail,
        raw_output_bounded=bounded,
        error_sections=err_sections,
        job_uid=job_uid,
        evidence_refs=tuple(evidence_refs),
    )


# Exact identity templates. Third-party signature validity is not an all-clear:
# matched facts are "expected component" inventory only, not endpoint health.
_RULES = {
    "VantageCoreAddinIdleScheduleTask": (
        "Lenovo Vantage idle-schedule task",
        re.compile(r"(?i)^[A-Z]:\\ProgramData\\Lenovo\\Vantage\\Addins\\VantageCoreAddin\\[0-9.]+\\x86\\IdleScheduleEventAction\.exe$"),
    ),
    "LenovoMachineFixUser_OOBE_AUTO_Notification": (
        "Lenovo Vantage onboarding notification task",
        re.compile(r"(?i)^[A-Z]:\\ProgramData\\Lenovo\\Vantage\\Addins\\LenovoMachineFixUserAddin\\[0-9.]+\\ScheduleEventAction\.exe$"),
    ),
}


def _canonical_path(path: str) -> str:
    return path.replace("/", "\\").rstrip("\\").casefold()


def classify_finding(finding: RawFinding, reviews: Sequence[EvidenceReview]) -> ReviewedFinding:
    matched = [item for item in reviews if item.name == finding.name]
    if len(matched) != 1:
        return ReviewedFinding(finding, Disposition.UNRESOLVED,
                               "Insufficient unique authenticated diagnostic evidence.",
                               finding.evidence_refs)
    ev = matched[0]
    if not ev.evidence_refs or ev.signature_status != "Valid" or not ev.executable:
        return ReviewedFinding(finding, Disposition.UNRESOLVED,
                               "Executable origin and signature were not both verified.",
                               (*finding.evidence_refs, *ev.evidence_refs))
    if finding.path and _canonical_path(ev.executable) != _canonical_path(finding.path):
        # V2's first-line summary truncates the long Lenovo notification
        # executable just after the dot. This exact known task may be
        # resolved only using its independently read task action and Lenovo
        # signature; generic prefix-matching is NEVER sufficient.
        known_truncated = (
            finding.name == "LenovoMachineFixUser_OOBE_AUTO_Notification"
            and finding.category.casefold() == "scheduledtask"
            and finding.path.endswith("ScheduleEventAction.")
            and _canonical_path(ev.executable).startswith(_canonical_path(finding.path))
        )
        if not known_truncated:
            return ReviewedFinding(finding, Disposition.UNRESOLVED,
                                   "Investigated executable does not match flagged path.",
                                   (*finding.evidence_refs, *ev.evidence_refs))
    refs = tuple(dict.fromkeys((*finding.evidence_refs, *ev.evidence_refs)))
    if finding.name in _RULES and finding.category.casefold() == "scheduledtask":
        title, pattern = _RULES[finding.name]
        if (ev.source == "scheduled_task" and
            re.search(r"(?i)\bO=Lenovo\b", ev.signer_subject) and
            pattern.fullmatch(ev.executable) and
            ev.task_path.startswith("\\Lenovo\\") and
            (not ev.arguments if finding.name == "VantageCoreAddinIdleScheduleTask"
             else ev.arguments.strip('" ') == finding.name)):
            return ReviewedFinding(finding, Disposition.VERIFIED_EXPECTED,
                                   f"{title}; expected task action and valid Lenovo signature verified.",
                                   refs)
    if finding.name == "HUNTAgent" and finding.category.casefold() == "service":
        if (ev.source == "service" and
            re.search(r"(?i)\bO=[\"']?Datto, LLC\b", ev.signer_subject) and
            re.fullmatch(r"(?i)[A-Z]:\\ProgramData\\CentraStage\\AEMAgent\\RMM\.AdvancedThreatDetection\\agent\.exe", ev.executable) and
            ev.service_display_name == "Datto EDR Agent" and
            ev.service_state.casefold() == "running" and
            ev.service_start_mode.casefold() in {"auto", "automatic"} and
            ev.arguments == "--service"):
            return ReviewedFinding(finding, Disposition.VERIFIED_EXPECTED,
                                   "Datto EDR Agent; running managed security service with expected path and valid Datto signature.",
                                   refs)
    return ReviewedFinding(finding, Disposition.UNRESOLVED,
                           "Available evidence does not satisfy the exact expected-software rule.",
                           refs)


def reconcile_assessment(*, company: str, site_uid: str, device_uid: str,
                         device_hostname: str, antivirus: Mapping[str, Any],
                         sweep: SweepObservation,
                         reviews: Sequence[EvidenceReview] = (),
                         external_findings: Sequence[RawFinding] = (),
                         evidence_refs: Sequence[str] = ()) -> Assessment:
    """Produce a fail-closed client-publication decision for a single endpoint."""
    if not all((company.strip(), site_uid.strip(), device_uid.strip(),
                device_hostname.strip())):
        raise ValueError("EXACT_ENDPOINT_AND_COMPANY_REQUIRED")
    if sweep.hostname.casefold() != device_hostname.casefold():
        raise ValueError("CROSS_ENDPOINT_REPORT_FORBIDDEN")
    # User-supplied review findings can add context but never reduce the source
    # count or make an unknown item go away.
    findings = tuple(sweep.findings) + tuple(external_findings)
    outcomes = tuple(classify_finding(f, reviews) for f in findings)
    counts = sweep.counts
    recognized = {
        s: sum(f.severity == s for f in sweep.findings)
        for s in ("High", "Medium", "Low", "Info")
    }
    missing = sum(max(0, counts[s]-recognized[s]) for s in recognized)
    if sweep.finding_detail_complete and missing:
        raise ValueError("INCONSISTENT_COMPLETE_REPORT")
    av_product = str(antivirus.get("antivirusProduct") or "Unknown")
    av_status = str(antivirus.get("antivirusStatus") or "Unknown")
    healthy_av = av_status == "RunningAndUpToDate" and bool(av_product.strip()) and av_product != "Unknown"
    unresolved = tuple(o for o in outcomes if o.disposition == Disposition.UNRESOLVED
                       and o.raw.severity in {"High", "Medium", "Low"})
    concern = tuple(o for o in outcomes if o.disposition == Disposition.CONCERN)
    limits: list[str] = ["Targeted read-only indicator review, not a full-disk or memory malware scan."]
    if sweep.raw_output_bounded and not sweep.finding_detail_complete:
        limits.append("Provider output excerpt is bounded; complete finding details were not retrievable.")
    if counts.get("Omitted", 0):
        limits.append("The source report omitted one or more findings due to its output cap.")
    if sweep.defender.get("Preferences") != "collected":
        limits.append("Microsoft Defender preferences/exclusions were not checked; this does not establish Datto AV health.")
    if not healthy_av:
        limits.append("Managed antivirus health could not be independently confirmed.")
    if missing:
        limits.append(f"{missing} finding details remain unretrieved and unclassified.")
    if sweep.collection_status != "complete" or sweep.error_sections:
        limits.append("One or more diagnostic collection sections were incomplete.")

    complete_evidence = (
        healthy_av and
        sweep.collection_status == "complete" and
        sweep.error_sections == 0 and
        counts.get("Omitted", 0) == 0 and
        missing == 0 and not unresolved and not concern
    )
    if concern or counts["High"]:
        status = "security_review_required"
    elif (unresolved or missing or not healthy_av
          or sweep.collection_status != "complete"
          or sweep.error_sections != 0
          or counts.get("Omitted", 0) != 0):
        status = "assessment_incomplete"
    else:
        status = "no_elevated_indicators_identified"
    return Assessment(
        hostname=device_hostname, company=company, site_uid=site_uid,
        device_uid=device_uid,
        antivirus_product=av_product, antivirus_status=av_status,
        sweep=sweep, reviewed=outcomes, unresolved_detail_count=missing,
        status=status, report_publishable=complete_evidence,
        limitations=tuple(limits),
        evidence_refs=tuple(dict.fromkeys((*evidence_refs, *sweep.evidence_refs))),
    )
