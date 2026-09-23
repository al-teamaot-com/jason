from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from uuid import uuid4

from .contracts import ArtifactReference, OrchestrationRequest, OrchestrationResult, OrchestrationStatus, ExecutionStage
from .execution_plan import ExecutionPlan


def intent_fingerprint(*, principal_id: str, organization_id: str, client_id: str | None, capability_name: str, arguments: Mapping[str, Any]) -> str:
    payload = {
        "principal_id": principal_id,
        "organization_id": organization_id,
        "client_id": client_id,
        "capability_name": capability_name,
        "arguments": arguments,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


# Compatibility alias retained for older callers/audit readers.
action_fingerprint = intent_fingerprint


@dataclass(frozen=True, slots=True)
class ApprovalReservation:
    approval_id: str
    intent_fingerprint: str
    idempotency_key: str
    request_id: str
    created: bool
    expires_at: datetime

    @property
    def action_fingerprint(self) -> str:
        return self.intent_fingerprint


@dataclass(frozen=True, slots=True)
class IntentCheck:
    intent_fingerprint: str
    replay_result: OrchestrationResult | None = None


@dataclass(frozen=True, slots=True)
class ExecutionPlanBinding:
    intent_fingerprint: str
    execution_plan_fingerprint: str


@dataclass(frozen=True, slots=True)
class SQLiteGovernedExecutionLedger:
    database_path: str

    def initialize(self) -> None:
        path = Path(self.database_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS governed_action_approvals (
              approval_id TEXT PRIMARY KEY,
              action_fingerprint TEXT NOT NULL UNIQUE,
              idempotency_key TEXT NOT NULL UNIQUE,
              principal_id TEXT NOT NULL, organization_id TEXT NOT NULL, client_id TEXT,
              capability_name TEXT NOT NULL, request_id TEXT NOT NULL, state TEXT NOT NULL,
              execution_id TEXT, correlation_id TEXT, result_json TEXT,
              created_at TEXT NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT, completed_at TEXT,
              intent_fingerprint TEXT, execution_plan_fingerprint TEXT,
              execution_plan_json TEXT, failure_reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_governed_action_state ON governed_action_approvals(state, expires_at);
            """)
            columns = {row["name"] for row in c.execute("PRAGMA table_info(governed_action_approvals)")}
            migrations = {
                "request_id": "TEXT NOT NULL DEFAULT ''",
                "intent_fingerprint": "TEXT",
                "execution_plan_fingerprint": "TEXT",
                "execution_plan_json": "TEXT",
                "failure_reason": "TEXT",
            }
            for name, ddl in migrations.items():
                if name not in columns:
                    c.execute(f"ALTER TABLE governed_action_approvals ADD COLUMN {name} {ddl}")
            c.execute(
                "UPDATE governed_action_approvals SET intent_fingerprint=action_fingerprint "
                "WHERE intent_fingerprint IS NULL OR intent_fingerprint=''"
            )

    def reserve_approval(self, *, principal_id: str, organization_id: str, client_id: str | None, capability_name: str, arguments: Mapping[str, Any], request_id: str, ttl_seconds: int = 300) -> ApprovalReservation:
        fp = intent_fingerprint(principal_id=principal_id, organization_id=organization_id, client_id=client_id, capability_name=capability_name, arguments=arguments)
        now = datetime.now(timezone.utc); expires = now + timedelta(seconds=ttl_seconds)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT * FROM governed_action_approvals WHERE action_fingerprint=?", (fp,)).fetchone()
            if row is not None:
                exp=datetime.fromisoformat(row['expires_at'])
                if exp > now:
                    c.commit(); return ApprovalReservation(row['approval_id'], fp, row['idempotency_key'], row['request_id'], False, exp)
                c.execute("DELETE FROM governed_action_approvals WHERE action_fingerprint=?", (fp,))
            approval_id=f"approval_mcp_{uuid4().hex}"; idem=f"idem_mcp_action_{uuid4().hex}"
            c.execute(
                "INSERT INTO governed_action_approvals(approval_id,action_fingerprint,intent_fingerprint,idempotency_key,principal_id,organization_id,client_id,capability_name,request_id,state,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (approval_id,fp,fp,idem,principal_id,organization_id,client_id,capability_name,request_id,'reserved',now.isoformat(),expires.isoformat())
            )
            c.commit(); return ApprovalReservation(approval_id, fp, idem, request_id, True, expires)

    def check_intent(self, request: OrchestrationRequest) -> IntentCheck:
        row, fp = self._validated_row(request)
        if row['state'] == 'succeeded' and row['result_json']:
            return IntentCheck(fp, self._result_from_json(json.loads(row['result_json'])))
        if row['state'] != 'reserved':
            raise PermissionError("approval has already been consumed")
        return IntentCheck(fp, None)

    def authorize_execution_plan(self, request: OrchestrationRequest, plan: ExecutionPlan) -> ExecutionPlanBinding:
        if not request.approval_id:
            raise PermissionError("approval_id is required for approval-governed execution")
        fp = intent_fingerprint(
            principal_id=request.principal_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            capability_name=request.capability_name,
            arguments=request.arguments,
        )
        plan_fp = plan.fingerprint
        plan_json = json.dumps(plan.canonical_material(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        now = datetime.now(timezone.utc)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT * FROM governed_action_approvals WHERE approval_id=?", (request.approval_id,)).fetchone()
            self._validate_row_values(row, request=request, fp=fp, now=now)
            if row['state'] != 'reserved':
                raise PermissionError("approval has already been consumed")
            c.execute(
                "UPDATE governed_action_approvals SET state='consumed',execution_id=?,correlation_id=?,consumed_at=?,execution_plan_fingerprint=?,execution_plan_json=? WHERE approval_id=? AND state='reserved'",
                (request.execution_id,request.correlation_id,now.isoformat(),plan_fp,plan_json,request.approval_id),
            )
            if c.total_changes != 1:
                raise PermissionError("approval has already been consumed")
            c.commit()
        return ExecutionPlanBinding(fp, plan_fp)

    def verify_execution_plan(self, request: OrchestrationRequest, plan: ExecutionPlan) -> ExecutionPlanBinding:
        if not request.approval_id:
            raise PermissionError("approval_id is required for approval-governed execution")
        fp = intent_fingerprint(
            principal_id=request.principal_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            capability_name=request.capability_name,
            arguments=request.arguments,
        )
        now=datetime.now(timezone.utc)
        with self._connect() as c:
            row=c.execute("SELECT * FROM governed_action_approvals WHERE approval_id=?", (request.approval_id,)).fetchone()
            self._validate_row_values(row, request=request, fp=fp, now=now)
            if row['state'] != 'consumed':
                raise PermissionError("approval is not in executable consumed state")
            expected=str(row['execution_plan_fingerprint'] or '')
            if not expected:
                raise PermissionError("approval has no authorized execution plan")
            if expected != plan.fingerprint:
                raise PermissionError("concrete execution plan does not match authorized execution plan")
            return ExecutionPlanBinding(fp, expected)

    # Compatibility method for callers that have not yet adopted concrete plans.
    # It intentionally cannot consume a new approval because that would recreate
    # the post-approval normalization gap.
    def begin(self, request: OrchestrationRequest) -> IntentCheck:
        return self.check_intent(request)

    def complete(self, request: OrchestrationRequest, result: OrchestrationResult) -> None:
        if not request.approval_id: return
        payload=self._result_to_json(result); now=datetime.now(timezone.utc).isoformat()
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE governed_action_approvals SET state='succeeded',result_json=?,completed_at=?,failure_reason=NULL WHERE approval_id=? AND state='consumed'", (json.dumps(payload,sort_keys=True,separators=(",",":"),default=str),now,request.approval_id))
            if c.total_changes != 1: raise PermissionError("approval completion state mismatch")
            c.commit()

    def fail(self, request: OrchestrationRequest, *, reason: str | None = None) -> None:
        if not request.approval_id: return
        with self._connect() as c:
            c.execute(
                "UPDATE governed_action_approvals SET state='failed',completed_at=?,failure_reason=? WHERE approval_id=? AND state='consumed'",
                (datetime.now(timezone.utc).isoformat(), reason, request.approval_id),
            )

    def evidence(self, approval_id: str) -> dict[str, Any] | None:
        with self._connect() as c:
            r=c.execute("SELECT * FROM governed_action_approvals WHERE approval_id=?", (approval_id,)).fetchone()
            return dict(r) if r else None

    def _validated_row(self, request: OrchestrationRequest) -> tuple[sqlite3.Row, str]:
        if not request.approval_id:
            raise PermissionError("approval_id is required for approval-governed execution")
        fp=intent_fingerprint(principal_id=request.principal_id, organization_id=request.organization_id, client_id=request.client_id, capability_name=request.capability_name, arguments=request.arguments)
        now=datetime.now(timezone.utc)
        with self._connect() as c:
            row=c.execute("SELECT * FROM governed_action_approvals WHERE approval_id=?", (request.approval_id,)).fetchone()
            self._validate_row_values(row, request=request, fp=fp, now=now)
            return row, fp

    @staticmethod
    def _validate_row_values(row: sqlite3.Row | None, *, request: OrchestrationRequest, fp: str, now: datetime) -> None:
        if row is None: raise PermissionError("approval is not registered for governed execution")
        stored_intent=str(row['intent_fingerprint'] or row['action_fingerprint'] or '')
        if stored_intent != fp: raise PermissionError("approval arguments do not match approved intent fingerprint")
        if row['idempotency_key'] != request.idempotency_key: raise PermissionError("idempotency key does not match approval")
        if datetime.fromisoformat(row['expires_at']) <= now: raise PermissionError("approval has expired")

    @staticmethod
    def _result_to_json(r: OrchestrationResult) -> dict[str, Any]:
        return {
            "execution_id": r.execution_id,
            "correlation_id": r.correlation_id,
            "capability_name": r.capability_name,
            "status": r.status.value,
            "stage": r.stage.value,
            "reason_codes": list(r.reason_codes),
            "output": dict(r.output),
            "artifact_references": [
                {"reference": a.reference, "media_type": a.media_type, "sha256": a.sha256}
                for a in r.artifact_references
            ],
            "attempts": r.attempts,
            "provider_id": r.provider_id,
            "error_code": r.error_code,
        }

    @staticmethod
    def _result_from_json(d: Mapping[str, Any]) -> OrchestrationResult:
        return OrchestrationResult(
            execution_id=str(d["execution_id"]),
            correlation_id=str(d["correlation_id"]),
            capability_name=str(d["capability_name"]),
            status=OrchestrationStatus(str(d["status"])),
            stage=ExecutionStage(str(d["stage"])),
            reason_codes=tuple(d["reason_codes"]),
            resolution=None,
            output=dict(d.get("output") or {}),
            artifact_references=tuple(
                ArtifactReference(
                    reference=str(item["reference"]),
                    media_type=item.get("media_type"),
                    sha256=item.get("sha256"),
                )
                for item in d.get("artifact_references") or []
            ),
            attempts=int(d.get("attempts") or 0),
            provider_id=d.get("provider_id"),
            error_code=d.get("error_code"),
        )

    def _connect(self) -> sqlite3.Connection:
        c=sqlite3.connect(self.database_path,timeout=10.0,isolation_level=None); c.row_factory=sqlite3.Row; c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA synchronous=FULL"); return c
