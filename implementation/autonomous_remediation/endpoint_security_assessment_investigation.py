"""Persisted, allow-listed read-only evidence recipes for security findings.

The recipes are *not* generic script execution. Every command is a constant,
selected only from an exact known finding identity; the existing governed
endpoint.powershell.read authorizer classifies and executes it. Follow-up
jobs use exact, persisted Datto selectors and cannot be resubmitted on polling
or output-read failure. Unknown findings remain unresolved.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import re
import sqlite3
from typing import Any, Mapping, Protocol

from .endpoint_security_assessment import EvidenceReview, RawFinding
from .endpoint_security_assessment_workflow import (
    AssessmentGovernanceError, AssessmentProviderError, AssessmentRequest,
    COMPONENT_UID, GovernedCapabilityPort, SqliteAssessmentState,
)

_SENTINEL = "AOT_REVIEW_JSON:"
_OUTPUT_COMPONENT = "8a1c153c-feee-41c5-9c9b-58a48e0214fe"
_MAX_EVIDENCE_SIZE = 5000


def _signature_json_pipe() -> str:
    # Only read-only commands, no variable assignments, Write-Output, method
    # invocation, scripts-on-disk or dynamic shell. This string is used only
    # for known signed publisher evidence selected from fixed allowlisted names.
    return (
        "Select-Object Path,"
        "@{Name='signature_status';Expression={[string]$_.Status}},"
        "@{Name='signer_subject';Expression={[string]$_.SignerCertificate.Subject}}"
        " | ConvertTo-Json -Compress"
    )


def _build_task_probe(task_name: str) -> str:
    # Called with exact literals from _RECIPES, never user input.
    if task_name not in {
        "VantageCoreAddinIdleScheduleTask",
        "LenovoMachineFixUser_OOBE_AUTO_Notification",
    }:
        raise ValueError("TASK_NOT_AN_APPROVED_INVESTIGATION_RECIPE")
    task = "Get-ScheduledTask -TaskName '" + task_name + "' -ErrorAction Stop"
    # Two short structured *read* outputs: task identity/action, then the
    # Authenticode status of that exact action executable. All commands must
    # pass DattoRmmReadOnlyPowerShellPolicy without changing its classifier.
    task_json = (
        task + " | Select-Object TaskName,TaskPath,"
        "@{Name='executable';Expression={$_.Actions[0].Execute}},"
        "@{Name='arguments';Expression={$_.Actions[0].Arguments}}"
        " | ConvertTo-Json -Compress"
    )
    signature_json = (
        task + " | ForEach-Object {Get-AuthenticodeSignature "
        "-FilePath $_.Actions[0].Execute -ErrorAction Stop | "
        + _signature_json_pipe() + "}"
    )
    return task_json + ";" + signature_json


def _build_hunt_probe() -> str:
    service_json = (
        "Get-CimInstance Win32_Service -Filter \"Name='HUNTAgent'\" "
        "-ErrorAction Stop | Select-Object Name,DisplayName,State,StartMode,"
        "PathName | ConvertTo-Json -Compress"
    )
    signer_json = (
        "Get-AuthenticodeSignature -FilePath "
        "'C:\\ProgramData\\CentraStage\\AEMAgent\\RMM.AdvancedThreatDetection\\agent.exe' "
        "-ErrorAction Stop | " + _signature_json_pipe()
    )
    return service_json + ";" + signer_json


_RECIPES = {
    "VantageCoreAddinIdleScheduleTask": ("ScheduledTask", _build_task_probe(
        "VantageCoreAddinIdleScheduleTask")),
    "LenovoMachineFixUser_OOBE_AUTO_Notification": ("ScheduledTask", _build_task_probe(
        "LenovoMachineFixUser_OOBE_AUTO_Notification")),
    "HUNTAgent": ("Service", _build_hunt_probe()),
}


def available_recipe(finding: RawFinding) -> bool:
    found = _RECIPES.get(finding.name)
    return found is not None and found[0].casefold() == finding.category.casefold()


def _expected_service_command(cmd: str, path: str) -> bool:
    # Never launch command; check against the exact expected Datto service form.
    p = path.replace("/", "\\").casefold()
    c = cmd.replace("/", "\\").strip().casefold()
    return c in {p + " --service", '"' + p + '" --service'}


def normalize_investigation_output(*, expected_finding: RawFinding,
                                   stdout: str, stderr: str,
                                   job_uid: str) -> EvidenceReview:
    if not available_recipe(expected_finding):
        raise AssessmentGovernanceError("INVESTIGATION_RECIPE_UNREGISTERED")
    if stderr.strip() or not stdout or len(stdout) > _MAX_EVIDENCE_SIZE:
        raise AssessmentProviderError("PROBE_OUTPUT_UNTRUSTED_OR_UNBOUNDED")
    if "The exit code was 0" not in stdout or "- Command run." not in stdout:
        raise AssessmentProviderError("PROBE_NOT_VERIFIED_COMPLETED")
    records = []
    for line in stdout.splitlines():
        payload = line.strip()
        if not payload.startswith("{"):
            continue
        if not payload.endswith("}"):
            raise AssessmentProviderError("PROBE_JSON_TRUNCATED")
        try:
            item = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise AssessmentProviderError("EVIDENCE_JSON_INVALID") from exc
        if not isinstance(item, Mapping):
            raise AssessmentProviderError("EVIDENCE_NOT_STRUCTURED")
        records.append(item)
    if len(records) != 2:
        raise AssessmentProviderError("SIGNED_INVENTORY_EVIDENCE_MISSING_OR_DUPLICATED")
    identity, signed_file = records
    # First object is the task/service read. Second is the independently
    # queried signature of the same executable. Do not rely on friendly names.
    path = str(identity.get("executable") or "")
    if expected_finding.category.casefold() == "service":
        kind = "service"
        if identity.get("Name") != expected_finding.name:
            raise AssessmentProviderError("PROBE_IDENTITY_DOES_NOT_MATCH_FINDING")
        path = (
            "C:\\ProgramData\\CentraStage\\AEMAgent\\"
            "RMM.AdvancedThreatDetection\\agent.exe"
        )
        if not _expected_service_command(str(identity.get("PathName") or ""), path):
            raise AssessmentProviderError("DATTO_SERVICE_COMMAND_CONFLICT")
    elif expected_finding.category.casefold() == "scheduledtask":
        kind = "scheduled_task"
        if identity.get("TaskName") != expected_finding.name:
            raise AssessmentProviderError("PROBE_IDENTITY_DOES_NOT_MATCH_FINDING")
        if not path:
            raise AssessmentProviderError("TASK_ACTION_PATH_MISSING")
    else:
        raise AssessmentProviderError("UNSUPPORTED_EVIDENCE_KIND")
    signed_path = str(signed_file.get("Path") or "")
    if not path or len(path) > 300 or (
        signed_path.replace("/", "\\").casefold() !=
        path.replace("/", "\\").casefold()
    ):
        raise AssessmentProviderError("SIGNATURE_TARGET_MISMATCH")
    signature = str(signed_file.get("signature_status") or "")
    signer = str(signed_file.get("signer_subject") or "")
    if len(signer) > 350:
        raise AssessmentProviderError("PROBE_IDENTITY_OR_SIGNER_INVALID")
    if kind == "service":
        return EvidenceReview(
            name=expected_finding.name, source=kind, executable=path,
            signature_status=signature, signer_subject=signer,
            service_display_name=str(identity.get("DisplayName") or ""),
            service_state=str(identity.get("State") or ""),
            service_start_mode=str(identity.get("StartMode") or ""),
            arguments="--service",
            evidence_refs=(f"datto-rmm:job:{job_uid}",),
        )
    return EvidenceReview(
        name=expected_finding.name, source=kind, executable=path,
        signature_status=signature, signer_subject=signer,
        task_path=str(identity.get("TaskPath") or ""),
        arguments=str(identity.get("arguments") or ""),
        evidence_refs=(f"datto-rmm:job:{job_uid}",),
    )


class ReadOnlyInvestigator:
    """One authorized read job per exact recipe per request; restart-safe."""

    def __init__(self, port: GovernedCapabilityPort, db_path: str) -> None:
        self.port = port
        self.db_path = str(db_path)
        self.assessments = SqliteAssessmentState(self.db_path)
        with sqlite3.connect(self.db_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS endpoint_security_evidence (
                request_id TEXT NOT NULL,
                device_uid TEXT NOT NULL,
                finding_name TEXT NOT NULL,
                category TEXT NOT NULL,
                state TEXT NOT NULL,
                job_uid TEXT,
                verified_json TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(request_id,device_uid,finding_name)
            )""")

    def _row(self, req: AssessmentRequest, device_uid: str,
             name: str) -> Mapping[str, Any] | None:
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("""SELECT * FROM endpoint_security_evidence
                WHERE request_id=? AND device_uid=? AND finding_name=?""",
                (req.request_id, device_uid, name)).fetchone()
        return dict(row) if row else None

    def _require_bound_request(self, req: AssessmentRequest, device_uid: str) -> None:
        row = self.assessments.create_or_get(req)
        if (not device_uid or row["device_uid"] != device_uid
            or row["component_uid"] != COMPONENT_UID
            or not row["job_uid"]
            or row["state"] not in {"investigating", "report_ready"}):
            raise AssessmentGovernanceError("PROBE_NOT_BOUND_TO_COMPLETED_ASSESSMENT")

    def dispatch_probe(self, req: AssessmentRequest, *,
                       device_uid: str, finding: RawFinding) -> str | None:
        self._require_bound_request(req, device_uid)
        if not available_recipe(finding):
            return None
        # Atomic reservation guards against duplicate probe execution.
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as db:
            entry = db.execute("""INSERT OR IGNORE INTO endpoint_security_evidence
                 (request_id,device_uid,finding_name,category,state,updated_at)
                 VALUES (?,?,?,?,'dispatching',?)""",
                 (req.request_id, device_uid, finding.name, finding.category, now))
            inserted = entry.rowcount == 1
        if not inserted:
            row = self._row(req, device_uid, finding.name)
            return row.get("job_uid") if row else None
        # This is an already-governed read capability, not a raw shell.
        result = self.port.read("endpoint.powershell.read", {
            "device_uid": device_uid, "command": _RECIPES[finding.name][1],
            "timeout_seconds": 30,
        })
        data = (result.get("evidence") or {}).get("data") or {}
        if result.get("status") != "succeeded" or data.get("status") != "accepted":
            self._set(req,device_uid,finding.name,state="blocked")
            raise AssessmentProviderError("READONLY_INVESTIGATION_DENIED")
        if (data.get("device_uid") != device_uid or
            data.get("component_uid") != _OUTPUT_COMPONENT or
            not data.get("job_uid")):
            self._set(req,device_uid,finding.name,state="blocked")
            raise AssessmentProviderError("INVESTIGATION_JOB_IDENTITY_INCOMPLETE")
        job_uid = str(data["job_uid"])
        self._set(req,device_uid,finding.name,state="waiting_job",job_uid=job_uid)
        return job_uid

    def _set(self, req,device_uid,name,**updates):
        permitted={"state","job_uid","verified_json"}
        if not updates or set(updates)-permitted:
            raise ValueError("INVALID_PROBE_UPDATE")
        with sqlite3.connect(self.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            cols = list(updates)
            statement = ", ".join(f"{col}=?" for col in cols)
            db.execute(f"""UPDATE endpoint_security_evidence SET
                 {statement},updated_at=?
                 WHERE request_id=? AND device_uid=? AND finding_name=?""",
                (*[updates[col] for col in cols],
                 datetime.now(timezone.utc).isoformat(),
                 req.request_id,device_uid,name))

    @staticmethod
    def _restore_review(serialized: str) -> EvidenceReview:
        raw = json.loads(serialized)
        raw["evidence_refs"] = tuple(raw.get("evidence_refs") or ())
        return EvidenceReview(**raw)

    def poll_probe(self, req: AssessmentRequest, *, device_uid: str,
                   finding: RawFinding) -> EvidenceReview | None:
        self._require_bound_request(req, device_uid)
        row=self._row(req,device_uid,finding.name)
        if row is None or row["category"] != finding.category:
            raise AssessmentGovernanceError("PROBE_NOT_ADMITTED_FOR_EXACT_FINDING")
        if row["state"] == "verified":
            return self._restore_review(row["verified_json"])
        if row["state"] != "waiting_job" or not row["job_uid"]:
            raise AssessmentGovernanceError("PROBE_NOT_WAITING_ON_EXACT_JOB")
        job_uid=row["job_uid"]
        job=self.port.read("automation.job.read", {"resource_id": job_uid})
        if job.get("status") != "succeeded":
            raise AssessmentProviderError("INVESTIGATION_JOB_READ_FAILED")
        state=((job.get("evidence") or {}).get("data") or {}).get("job") or {}
        if state.get("resource_id") != job_uid:
            raise AssessmentProviderError("INVESTIGATION_JOB_ID_MISMATCH")
        if state.get("status") == "active":
            return None
        if state.get("status") != "completed":
            self._set(req,device_uid,finding.name,state="blocked")
            raise AssessmentProviderError("INVESTIGATION_JOB_FAILED")
        outputs={}
        for stream in ("stdout","stderr"):
            response=self.port.read("automation.job.output.read", {
                "resource_id":job_uid,"device_uid":device_uid,
                "component_uid":_OUTPUT_COMPONENT,"stream":stream,
            })
            if response.get("status") != "succeeded":
                raise AssessmentProviderError("INVESTIGATION_OUTPUT_READ_DENIED")
            data=(response.get("evidence") or {}).get("data") or {}
            if (data.get("resource_id") != job_uid or data.get("device_uid") != device_uid
                or data.get("component_uid") != _OUTPUT_COMPONENT
                or data.get("match_count") != 1):
                raise AssessmentProviderError("INVESTIGATION_OUTPUT_SELECTOR_MISMATCH")
            chunks=data.get("outputs") or ()
            if len(chunks)!=1 or chunks[0].get("component_uid") != _OUTPUT_COMPONENT:
                raise AssessmentProviderError("INVESTIGATION_OUTPUT_NOT_EXACT")
            outputs[stream]=str(chunks[0].get("text") or "")
        evidence=normalize_investigation_output(
            expected_finding=finding,stdout=outputs["stdout"],
            stderr=outputs["stderr"],job_uid=job_uid)
        self._set(req,device_uid,finding.name,state="verified",
                  verified_json=json.dumps(asdict(evidence),sort_keys=True))
        return evidence

    def known_results(self, req: AssessmentRequest, *, device_uid: str) -> tuple[EvidenceReview, ...]:
        with sqlite3.connect(self.db_path) as db:
            db.row_factory=sqlite3.Row
            items=db.execute("""SELECT verified_json FROM endpoint_security_evidence
                WHERE request_id=? AND device_uid=? AND state='verified'""",
                (req.request_id,device_uid)).fetchall()
        return tuple(self._restore_review(row["verified_json"]) for row in items)
