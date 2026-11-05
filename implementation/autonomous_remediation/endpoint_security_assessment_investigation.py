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


def _build_task_probe(task_name: str) -> str:
    # Called with exact literals from _RECIPES, never user input.
    if task_name not in {
        "VantageCoreAddinIdleScheduleTask",
        "LenovoMachineFixUser_OOBE_AUTO_Notification",
    }:
        raise ValueError("TASK_NOT_AN_APPROVED_INVESTIGATION_RECIPE")
    return (
        "$t=Get-ScheduledTask -TaskName '" + task_name + "' -ErrorAction Stop;"
        "$a=$t.Actions|Select-Object -First 1;"
        "$s=Get-AuthenticodeSignature -LiteralPath $a.Execute -ErrorAction Stop;"
        "$o=[pscustomobject]@{name=$t.TaskName;source='scheduled_task';"
        "task_path=$t.TaskPath;executable=$a.Execute;arguments=$a.Arguments;"
        "signature_status=[string]$s.Status;"
        "signer_subject=[string]$s.SignerCertificate.Subject};"
        "Write-Output ('AOT_REVIEW_JSON:'+($o|ConvertTo-Json -Compress))"
    )


def _build_hunt_probe() -> str:
    return (
        "$svc=Get-CimInstance Win32_Service -Filter \"Name='HUNTAgent'\" -ErrorAction Stop;"
        "$expected='C:\\ProgramData\\CentraStage\\AEMAgent\\RMM.AdvancedThreatDetection\\agent.exe';"
        "$s=Get-AuthenticodeSignature -LiteralPath $expected -ErrorAction Stop;"
        "$o=[pscustomobject]@{name=$svc.Name;source='service';"
        "service_display_name=$svc.DisplayName;service_state=$svc.State;"
        "service_start_mode=$svc.StartMode;"
        "executable=$expected;service_command=$svc.PathName;"
        "signature_status=[string]$s.Status;"
        "signer_subject=[string]$s.SignerCertificate.Subject};"
        "Write-Output ('AOT_REVIEW_JSON:'+($o|ConvertTo-Json -Compress))"
    )


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
    records = [
        line[len(_SENTINEL):].strip()
        for line in stdout.splitlines()
        if line.strip().startswith(_SENTINEL)
    ]
    if len(records) != 1:
        raise AssessmentProviderError("SIGNED_INVENTORY_EVIDENCE_MISSING_OR_DUPLICATED")
    try:
        v = json.loads(records[0])
    except (ValueError, TypeError) as exc:
        raise AssessmentProviderError("EVIDENCE_JSON_INVALID") from exc
    if not isinstance(v, Mapping) or v.get("name") != expected_finding.name:
        raise AssessmentProviderError("PROBE_IDENTITY_DOES_NOT_MATCH_FINDING")
    kind = str(v.get("source") or "")
    path = str(v.get("executable") or "")
    signature = str(v.get("signature_status") or "")
    signer = str(v.get("signer_subject") or "")
    if not path or len(path) > 300 or len(signer) > 350:
        raise AssessmentProviderError("PROBE_IDENTITY_OR_SIGNER_INVALID")
    if kind == "service":
        if not _expected_service_command(str(v.get("service_command") or ""), path):
            raise AssessmentProviderError("DATTO_SERVICE_COMMAND_CONFLICT")
        return EvidenceReview(
            name=expected_finding.name, source=kind, executable=path,
            signature_status=signature, signer_subject=signer,
            service_display_name=str(v.get("service_display_name") or ""),
            service_state=str(v.get("service_state") or ""),
            service_start_mode=str(v.get("service_start_mode") or ""),
            arguments="--service",
            evidence_refs=(f"datto-rmm:job:{job_uid}",),
        )
    if kind == "scheduled_task":
        return EvidenceReview(
            name=expected_finding.name, source=kind, executable=path,
            signature_status=signature, signer_subject=signer,
            task_path=str(v.get("task_path") or ""),
            arguments=str(v.get("arguments") or ""),
            evidence_refs=(f"datto-rmm:job:{job_uid}",),
        )
    raise AssessmentProviderError("UNSUPPORTED_EVIDENCE_KIND")


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
