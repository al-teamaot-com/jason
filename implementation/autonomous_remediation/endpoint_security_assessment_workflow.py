"""Persisted governed Endpoint Security Assessment request coordinator.

This coordinator is NOT an authorization server and NOT a provider connector.
The caller injects Jason's existing governed read/action ports; an exact
technician approval is externally validated and carried unmodified.  There
is no direct Datto HTTP access, API credential, shell execution or bypass.
The coordinator is dormant until registered by a separately approved release.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Protocol, Sequence

from .endpoint_security_assessment import (
    Assessment, EvidenceReview, RawFinding, SweepObservation, parse_sweep_output,
    reconcile_assessment,
)
from .endpoint_security_assessment_report import render_security_pdf

COMPONENT_UID = "8ff72744-cb29-4cad-a11b-7a1c2a199f06"
COMPONENT_NAME = "Check RATs and Malicious Tools - AOT Ver 11042026"
_TERMINAL_JOBS = frozenset({"completed", "failed", "cancelled"})
_MAX_RECHECKS = 35


class GovernedCapabilityPort(Protocol):
    """This port MUST be the existing requester-bound Central Orchestrator."""

    def read(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def action(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


class AssessmentGovernanceError(PermissionError):
    pass


class AssessmentProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssessmentRequest:
    # Caller-minted immutable per-turn request key, not a raw hostname cache.
    request_id: str
    organization_id: str
    client_site_uid: str
    hostname: str
    requester_identity: str

    def __post_init__(self) -> None:
        for value in (self.request_id, self.organization_id, self.client_site_uid,
                      self.hostname, self.requester_identity):
            if not value.strip() or len(value) > 160:
                raise ValueError("REQUEST_IDENTITY_INCOMPLETE")


@dataclass(frozen=True)
class AssessmentProgress:
    state: str
    device_uid: str | None
    job_uid: str | None
    assessment: Assessment | None
    next_action: str
    report_ready: bool


class SqliteAssessmentState:
    """Persistent instance/job identity and duplicate-dispatch suppression.

    DB location must be outside immutable release images.  This store never
    holds provider credentials or full process command-lines/stdout.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        with sqlite3.connect(self.db_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS endpoint_security_assessment (
                request_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                client_site_uid TEXT NOT NULL,
                hostname TEXT NOT NULL,
                requester_identity TEXT NOT NULL,
                state TEXT NOT NULL,
                device_uid TEXT,
                component_uid TEXT,
                job_uid TEXT,
                recheck_count INTEGER NOT NULL DEFAULT 0,
                observed_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            )""")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS
              one_active_security_assessment_per_requester_and_device
              ON endpoint_security_assessment (
                organization_id,requester_identity,client_site_uid,hostname COLLATE NOCASE)
              WHERE state IN ('identified','waiting_device','waiting_approval',
                              'dispatched','waiting_job','investigating')""")

    def find_active(self, req: AssessmentRequest) -> Mapping[str, Any] | None:
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("""SELECT * FROM endpoint_security_assessment
                WHERE organization_id=? AND requester_identity=?
                  AND client_site_uid=? AND hostname=? COLLATE NOCASE
                  AND state IN ('identified','waiting_device','waiting_approval',
                                'dispatched','waiting_job','investigating')
                ORDER BY updated_at DESC LIMIT 1""", (
                req.organization_id,req.requester_identity,req.client_site_uid,
                req.hostname)).fetchone()
        return dict(row) if row else None

    def create_or_get(self, req: AssessmentRequest) -> Mapping[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                INSERT OR IGNORE INTO endpoint_security_assessment
                (request_id,organization_id,client_site_uid,hostname,
                 requester_identity,state,updated_at)
                VALUES (?,?,?,?,?,'identified',?)
            """, (req.request_id, req.organization_id, req.client_site_uid,
                  req.hostname, req.requester_identity, now))
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM endpoint_security_assessment WHERE request_id=?",
                             (req.request_id,)).fetchone()
        if row is None:
            raise AssessmentGovernanceError(
                "DUPLICATE_ACTIVE_ASSESSMENT_EXISTS_DO_NOT_REDISPATCH")
        result = dict(row)
        if any(result[key] != expected for key, expected in (
            ("organization_id", req.organization_id),
            ("client_site_uid", req.client_site_uid),
            ("hostname", req.hostname),
            ("requester_identity", req.requester_identity),
        )):
            raise AssessmentGovernanceError("REQUEST_ID_REUSED_WITH_DIFFERENT_TARGET_OR_PRINCIPAL")
        return result

    def reserve_dispatch(self, request_id: str) -> bool:
        """Atomically prevent two workers from dispatching one per-run action."""
        with sqlite3.connect(self.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute("""
                UPDATE endpoint_security_assessment
                SET state='dispatched',component_uid=?,updated_at=?
                WHERE request_id=? AND state='waiting_approval' AND job_uid IS NULL
            """, (COMPONENT_UID, datetime.now(timezone.utc).isoformat(), request_id))
            reserved = updated.rowcount == 1
        return reserved

    def update(self, request_id: str, **changes: Any) -> Mapping[str, Any]:
        permitted = {"state", "device_uid", "component_uid", "job_uid",
                     "recheck_count", "observed_json"}
        if not changes or set(changes) - permitted:
            raise ValueError("INVALID_ASSESSMENT_STATE_TRANSITION")
        with sqlite3.connect(self.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.row_factory = sqlite3.Row
            current = db.execute("SELECT * FROM endpoint_security_assessment WHERE request_id=?",
                                 (request_id,)).fetchone()
            if not current:
                raise LookupError("ASSESSMENT_NOT_FOUND")
            keys = list(changes)
            updates = ", ".join(f"{key}=?" for key in keys)
            vals = [changes[key] for key in keys]
            db.execute(f"UPDATE endpoint_security_assessment SET {updates}, updated_at=? WHERE request_id=?",
                       (*vals, datetime.now(timezone.utc).isoformat(), request_id))
            next_row = db.execute("SELECT * FROM endpoint_security_assessment WHERE request_id=?",
                                  (request_id,)).fetchone()
        return dict(next_row)


class GovernedAssessmentCoordinator:
    """Nonblocking, restart-safe coordinator for one explicitly requested device.

    'advance' resumes the same job when active; it never re-dispatches a
    component to compensate for missing job output, a polling delay, or a read
    error.  The caller (MCP/Teams integration) owns authorization, scheduling,
    evidence investigation and delivery.  No standing autonomy is implied.
    """

    def __init__(self, port: GovernedCapabilityPort,
                 store: SqliteAssessmentState) -> None:
        self.port = port
        self.store = store

    @staticmethod
    def _evidence(result: Mapping[str, Any]) -> Mapping[str, Any]:
        if result.get("status") not in {"succeeded", "ok"}:
            raise AssessmentProviderError("GOVERNED_CAPABILITY_REJECTED")
        return result.get("evidence") or {}

    def prepare(self, req: AssessmentRequest) -> AssessmentProgress:
        row = self.store.create_or_get(req)
        if row["device_uid"]:
            if row["state"] == "waiting_device":
                endpoint = self._evidence(self.port.read(
                    "endpoint.device.read", {"resource_id": row["device_uid"]})).get("record") or {}
                if (endpoint.get("resource_id") != row["device_uid"]
                    or endpoint.get("site_id") != req.client_site_uid
                    or endpoint.get("hostname", "").casefold() != req.hostname.casefold()
                    or endpoint.get("deleted") or endpoint.get("suspended")):
                    self.store.update(req.request_id, state="blocked")
                    raise AssessmentGovernanceError("WAITING_DEVICE_IDENTITY_OR_STATE_CHANGED")
                if endpoint.get("online") is True:
                    self.store.update(req.request_id, state="waiting_approval")
                    return AssessmentProgress("waiting_approval", row["device_uid"], None,
                                              None, "exact_technician_approval_required", False)
            return AssessmentProgress(row["state"], row["device_uid"], row["job_uid"],
                                      None, "resume_exact_job_or_request", False)
        found = self._evidence(self.port.read(
            "endpoint.device.search", {"hostname": req.hostname, "max": 100}))
        exact = [record for record in found.get("resource_matches", ())
                 if str(record.get("hostname", "")).casefold() == req.hostname.casefold()
                 and record.get("site_id") == req.client_site_uid]
        if len(exact) != 1:
            self.store.update(req.request_id, state="blocked")
            raise AssessmentGovernanceError("ENDPOINT_IDENTITY_AMBIGUOUS_OR_CROSS_CLIENT")
        uid = str(exact[0].get("resource_id") or "")
        if not uid:
            raise AssessmentGovernanceError("EXACT_DEVICE_UID_REQUIRED")
        endpoint = self._evidence(self.port.read(
            "endpoint.device.read", {"resource_id": uid})).get("record") or {}
        if (endpoint.get("hostname", "").casefold() != req.hostname.casefold()
            or endpoint.get("site_id") != req.client_site_uid
            or endpoint.get("resource_id") != uid):
            self.store.update(req.request_id, state="blocked")
            raise AssessmentGovernanceError("AUTHORITATIVE_DEVICE_MISMATCH")
        if endpoint.get("deleted") or endpoint.get("suspended"):
            self.store.update(req.request_id, state="blocked")
            raise AssessmentGovernanceError("INACTIVE_OR_RETIRED_DEVICE")
        catalog = self._evidence(self.port.read("automation.component.search",
                                                {"name": COMPONENT_NAME}))
        components = [entry for entry in catalog.get("resource_matches", ())
                      if entry.get("resource_id") == COMPONENT_UID
                      and entry.get("name") == COMPONENT_NAME]
        if len(components) != 1:
            self.store.update(req.request_id, state="blocked")
            raise AssessmentGovernanceError("EXACT_COMPONENT_NOT_AVAILABLE")
        next_state = "waiting_approval" if endpoint.get("online") else "waiting_device"
        self.store.update(req.request_id, device_uid=uid, state=next_state)
        return AssessmentProgress(next_state, uid, None, None,
                                  "verify_exact_technician_authority", False)

    def dispatch(self, req: AssessmentRequest,
                 *, approval_bound_arguments: Mapping[str, Any] | None) -> AssessmentProgress:
        """Only Central Orchestrator may validate/issue the exact action argument set.

        This method never constructs 'explicit_approval' or a reviewer decision.
        It cannot grant an execution right by changing stored playbook state.
        """
        row = self.store.create_or_get(req)
        if row["job_uid"]:
            return AssessmentProgress(row["state"], row["device_uid"], row["job_uid"],
                                      None, "poll_original_job", False)
        if row["state"] != "waiting_approval" or not row["device_uid"]:
            raise AssessmentGovernanceError("DEVICE_NOT_READY_FOR_DISPATCH")
        if not approval_bound_arguments:
            return AssessmentProgress("waiting_approval", row["device_uid"], None,
                                      None, "exact_technician_approval_required", False)
        args = dict(approval_bound_arguments)
        if (args.get("device_uid") != row["device_uid"]
            or args.get("component_uid") != COMPONENT_UID
            or args.get("component_name") != COMPONENT_NAME):
            raise AssessmentGovernanceError("APPROVAL_BINDING_TARGET_OR_COMPONENT_MISMATCH")
        if not args.get("explicit_approval"):
            raise AssessmentGovernanceError("PER_RUN_COMPONENT_APPROVAL_REQUIRED")
        # Only already-validated arguments from a trusted, requester-bound
        # gateway reach this operation. The gateway independently checks all
        # approval/identity/least-disruptive constraints again. Persist the
        # dispatch intent *before* the provider side effect. On crash or an
        # ambiguous response, preserve 'dispatched' and NEVER submit again
        # without reconciling the exact operation in the governed ledger.
        if not self.store.reserve_dispatch(req.request_id):
            latest = self.store.create_or_get(req)
            return AssessmentProgress(latest["state"], latest["device_uid"],
                                      latest["job_uid"], None,
                                      "reconcile_existing_dispatch_do_not_redispatch",
                                      False)
        result = self.port.action("automation.component.execute", args)
        if result.get("status") != "succeeded":
            raise AssessmentProviderError("GOVERNED_COMPONENT_EXECUTION_NOT_ACCEPTED")
        data = result.get("result") or {}
        uid = str(data.get("job_uid") or "")
        if (not uid or data.get("status") != "accepted"
            or data.get("device_uid") != row["device_uid"]
            or data.get("component_uid") != COMPONENT_UID):
            # A provider might have accepted the job despite a malformed
            # response. Fail closed; do NOT re-dispatch automatically.
            self.store.update(req.request_id, state="blocked")
            raise AssessmentProviderError("ACTION_ACCEPTANCE_EVIDENCE_INCOMPLETE")
        self.store.update(req.request_id, state="waiting_job",
                          component_uid=COMPONENT_UID, job_uid=uid)
        return AssessmentProgress("waiting_job", row["device_uid"], uid, None,
                                  "poll_original_job_only", False)

    def collect(self, req: AssessmentRequest,
                *, additional_reviews: Sequence[EvidenceReview] = (),
                additional_findings: Sequence[RawFinding] = ()) -> AssessmentProgress:
        row = self.store.create_or_get(req)
        uid = str(row["device_uid"] or "")
        job_uid = str(row["job_uid"] or "")
        if not uid or not job_uid or row["component_uid"] != COMPONENT_UID:
            raise AssessmentGovernanceError("NO_ACCEPTED_JOB_FOR_THIS_REQUEST")
        if row["state"] not in {"waiting_job", "investigating", "report_ready", "human_review"}:
            raise AssessmentGovernanceError("INVALID_ASSESSMENT_COLLECT_STATE")
        job = self._evidence(self.port.read(
            "automation.job.read", {"resource_id": job_uid}))
        status = str((job.get("data") or {}).get("job", {}).get("status") or "")
        if status not in _TERMINAL_JOBS:
            if status != "active":
                raise AssessmentProviderError("UNRECOGNIZED_JOB_STATE")
            count = int(row["recheck_count"]) + 1
            if count > _MAX_RECHECKS:
                self.store.update(req.request_id, state="blocked", recheck_count=count)
                raise AssessmentProviderError("JOB_POLL_LIMIT_REACHED_NO_REDISPATCH")
            self.store.update(req.request_id, state="waiting_job", recheck_count=count)
            return AssessmentProgress("waiting_job", uid, job_uid, None,
                                      "recheck_same_job_later", False)
        if status != "completed":
            self.store.update(req.request_id, state="human_review")
            return AssessmentProgress("human_review", uid, job_uid, None,
                                      "verify_failed_job_evidence", False)
        outs = {}
        for stream in ("stdout", "stderr"):
            raw = self._evidence(self.port.read(
                "automation.job.output.read", {
                    "resource_id": job_uid, "device_uid": uid,
                    "component_uid": COMPONENT_UID, "stream": stream,
                }))
            data = raw.get("data") or {}
            if (data.get("resource_id") != job_uid or
                data.get("device_uid") != uid or
                data.get("component_uid") != COMPONENT_UID or
                data.get("match_count") != 1):
                raise AssessmentProviderError("JOB_OUTPUT_SELECTORS_MISMATCH")
            outputs = data.get("outputs") or ()
            if len(outputs) != 1 or outputs[0].get("component_uid") != COMPONENT_UID:
                raise AssessmentProviderError("JOB_OUTPUT_NOT_EXACT")
            outs[stream] = str(outputs[0].get("text") or "")
        endpoint = self._evidence(self.port.read(
            "endpoint.device.read", {"resource_id": uid})).get("record") or {}
        if (endpoint.get("resource_id") != uid
            or endpoint.get("site_id") != req.client_site_uid
            or endpoint.get("hostname", "").casefold() != req.hostname.casefold()):
            self.store.update(req.request_id, state="blocked")
            raise AssessmentGovernanceError("POST_JOB_CLIENT_OR_IDENTITY_MISMATCH")
        full_findings = None
        complete_finding_read = getattr(self.port, "read_assessment_findings", None)
        if (callable(complete_finding_read)
            and "AOT_SECURITY_JSON_END" not in outs["stdout"]):
            try:
                full_findings = complete_finding_read(
                    job_uid=job_uid, device_uid=uid,
                    component_uid=COMPONENT_UID, hostname=req.hostname,
                )
            except (ValueError, LookupError, RuntimeError, PermissionError):
                # A denied/partial structured detail read never creates
                # new privilege or a duplicate scan: the bounded original
                # report remains explicitly incomplete for the client.
                full_findings = None
        sweep = parse_sweep_output(
            hostname=req.hostname, job_uid=job_uid, stdout=outs["stdout"],
            stderr=outs["stderr"], job_status=status, component_uid=COMPONENT_UID,
            evidence_refs=(f"datto-rmm:job:{job_uid}",),
            complete_findings=full_findings)
        assessment = reconcile_assessment(
            company=str(endpoint.get("site") or ""),
            site_uid=req.client_site_uid, device_uid=uid,
            device_hostname=req.hostname, antivirus=endpoint.get("antivirus") or {},
            sweep=sweep, reviews=additional_reviews,
            external_findings=additional_findings,
            evidence_refs=(f"datto-rmm:device:{uid}",))
        next_state = "report_ready" if assessment.report_publishable else "investigating"
        # Only sanitized status, counts and evidence IDs. Full stdout, command
        # lines and process paths are not persisted in this generic store.
        saved = {"counts": dict(sweep.counts), "inventory": dict(sweep.inventory),
                 "status": assessment.status, "report_publishable": assessment.report_publishable,
                 "unresolved_detail_count": assessment.unresolved_detail_count,
                 "review_evidence_refs": list(assessment.evidence_refs)}
        self.store.update(req.request_id, state=next_state,
                          observed_json=json.dumps(saved, sort_keys=True))
        return AssessmentProgress(next_state, uid, job_uid, assessment,
                                  ("render_report" if assessment.report_publishable
                                   else "investigate_bounded_or_missing_findings"),
                                  assessment.report_publishable)

    @staticmethod
    def render(progress: AssessmentProgress, *, audience: str) -> bytes:
        if progress.assessment is None:
            raise ValueError("NO_VERIFIED_ASSESSMENT_TO_RENDER")
        return render_security_pdf(progress.assessment, audience=audience)
