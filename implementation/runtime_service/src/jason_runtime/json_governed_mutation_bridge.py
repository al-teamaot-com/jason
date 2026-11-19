"""Source-only JSON mutation planning through the existing governed action port.

No production composition imports this component. No provider credentials or
new action authority exist here. The existing Central Orchestrator action
gateway enforces exact Owner promotion; this bridge only protects a replay
boundary around one immutable interpreter-produced instruction. Synthetic
tests exclusively use mocked provider output, never live provider writes.

No automatic retry of an indeterminate mutation is allowed. When a prior
attempt may have reached a provider, the exact state must be reconciled from
authoritative readback rather than dispatching again.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import os
import sqlite3
from typing import Any, Mapping

from autonomous_remediation.playbook_document import PlaybookDocument
from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
from autonomous_remediation.playbook_ticket_evidence import (
    handoff_identity_facts, UntrustedTicketEvidence,
)
from .autonomy_worker_runtime import GovernedAutonomyActionPort, PlaybookScope


class JsonGovernedMutationBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class JsonMutationPlan:
    run_id: str
    client_id: str
    target_id: str
    document_fingerprint: str
    playbook_id: str
    playbook_version: str
    step_id: str
    capability: str
    arguments: Mapping[str, Any]
    intent_fingerprint: str
    approval_classification: str
    expected_verified_fields: frozenset[str]


class SQLiteJsonMutationCheckpoint:
    """One-shot mutation claim receipts, not a playbook/approval registry."""

    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        os.chmod(self.path, 0o600)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS json_mutation_checkpoints (
            run_id TEXT NOT NULL, step_id TEXT NOT NULL,
            client_id TEXT NOT NULL, target_id TEXT NOT NULL,
            playbook_id TEXT NOT NULL, playbook_version TEXT NOT NULL,
            document_fingerprint TEXT NOT NULL,
            intent_fingerprint TEXT NOT NULL,
            capability TEXT NOT NULL, state TEXT NOT NULL,
            evidence_sha256 TEXT,
            PRIMARY KEY(run_id,step_id)
        );
        """)

    def claim(self, plan: JsonMutationPlan) -> tuple[str, bool]:
        with self.db:
            # BEGIN IMMEDIATE is safe with the default autocommit connection;
            # no write-side effects occur before a durable receipt is stored.
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                "SELECT * FROM json_mutation_checkpoints "
                "WHERE run_id=? AND step_id=?",
                (plan.run_id, plan.step_id),
            ).fetchone()
            if row is not None:
                required = {
                    "client_id": plan.client_id, "target_id": plan.target_id,
                    "playbook_id": plan.playbook_id,
                    "playbook_version": plan.playbook_version,
                    "document_fingerprint": plan.document_fingerprint,
                    "intent_fingerprint": plan.intent_fingerprint,
                    "capability": plan.capability,
                }
                if any(row[key] != value for key, value in required.items()):
                    raise JsonGovernedMutationBoundaryError("MUTATION_INTENT_SCOPE_CHANGED")
                return str(row["state"]), False
            self.db.execute(
                "INSERT INTO json_mutation_checkpoints("
                "run_id,step_id,client_id,target_id,playbook_id,"
                "playbook_version,document_fingerprint,intent_fingerprint,"
                "capability,state) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    plan.run_id, plan.step_id, plan.client_id, plan.target_id,
                    plan.playbook_id, plan.playbook_version,
                    plan.document_fingerprint, plan.intent_fingerprint,
                    plan.capability, "indeterminate",
                ),
            )
            return "indeterminate", True

    def complete(self, plan: JsonMutationPlan, *, evidence: Mapping[str, Any]) -> None:
        digest = sha256(_canonical(evidence).encode()).hexdigest()
        with self.db:
            updated = self.db.execute(
                "UPDATE json_mutation_checkpoints SET state='verified',"
                "evidence_sha256=? WHERE run_id=? AND step_id=?"
                " AND intent_fingerprint=? AND state='indeterminate'",
                (digest, plan.run_id, plan.step_id, plan.intent_fingerprint),
            )
            if updated.rowcount != 1:
                raise JsonGovernedMutationBoundaryError("MUTATION_COMPLETION_RECEIPT_MISSING")

    def read(self, plan: JsonMutationPlan) -> Mapping[str, Any] | None:
        record = self.db.execute(
            "SELECT * FROM json_mutation_checkpoints "
            "WHERE run_id=? AND step_id=?",
            (plan.run_id, plan.step_id),
        ).fetchone()
        return dict(record) if record is not None else None

    def close(self) -> None:
        self.db.close()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_json_mutation_plan(
    *,
    document: PlaybookDocument,
    run_id: str,
    client_id: str,
    target_id: str,
    step_id: str,
    trusted_facts: Mapping[str, Any],
    expected_verified_fields: frozenset[str],
) -> JsonMutationPlan:
    if not all(isinstance(v, str) and v.strip() and len(v) <= 128
               for v in (run_id, client_id, target_id, step_id)):
        raise JsonGovernedMutationBoundaryError("MUTATION_EXACT_IDENTITY_REQUIRED")
    if document.autonomy_activation != "shadow" or (
        document.payload.get("scope", {}).get("direct_provider_access") is not False
    ):
        raise JsonGovernedMutationBoundaryError("MUTATION_SOURCE_BOUNDARY_UNVERIFIED")
    if not isinstance(expected_verified_fields, frozenset) or not expected_verified_fields:
        raise JsonGovernedMutationBoundaryError("MUTATION_EXACT_VERIFICATION_FIELDS_REQUIRED")
    if not isinstance(trusted_facts, Mapping) or (
        str(trusted_facts.get("client_id") or "") != client_id or
        str(trusted_facts.get("target_id") or "") != target_id
    ):
        raise JsonGovernedMutationBoundaryError("MUTATION_TRUSTED_SCOPE_MISMATCH")
    interpreter = JsonPlaybookInterpreter(document)
    instruction = interpreter.instruction(step_id=step_id, facts=trusted_facts)
    if (instruction.step_type != "remediation" or
            not instruction.approval_required or
            instruction.approval_classification != "modifying" or
            not instruction.capability or
            instruction.capability not in document.capabilities):
        raise JsonGovernedMutationBoundaryError("MUTATION_NOT_EXACT_APPROVAL_BOUND")
    intent = {
        "run_id": run_id, "client_id": client_id, "target_id": target_id,
        "source_fingerprint": document.fingerprint,
        "step_id": instruction.step_id,
        "capability": instruction.capability,
        "arguments": dict(instruction.arguments),
        "approval_classification": instruction.approval_classification,
        "required_readback_fields": sorted(expected_verified_fields),
    }
    digest = sha256(_canonical(intent).encode()).hexdigest()
    return JsonMutationPlan(
        run_id=run_id, client_id=client_id, target_id=target_id,
        document_fingerprint=document.fingerprint,
        playbook_id=document.playbook_id, playbook_version=document.version,
        step_id=instruction.step_id, capability=instruction.capability,
        arguments=dict(instruction.arguments),
        intent_fingerprint=digest,
        approval_classification="modifying",
        expected_verified_fields=expected_verified_fields,
    )


def _readback_verified(plan: JsonMutationPlan, response: Mapping[str, Any]) -> bool:
    data = response.get("data") if isinstance(response, Mapping) else None
    fields = data.get("jasonVerification") if isinstance(data, Mapping) else None
    if not isinstance(fields, Mapping):
        return False
    verified = fields.get("verifiedFields")
    if not isinstance(verified, list):
        return False
    return (fields.get("readbackVerified") is True and
            plan.expected_verified_fields.issubset(set(map(str, verified))))



def _bounded_ticket_read(
    read_port: Any,
    *,
    plan: JsonMutationPlan,
    document: PlaybookDocument,
) -> Mapping[str, Any]:
    """Independent exact PSA readback; never trust action result alone."""
    if (str(getattr(read_port, "client_id", "") or
            getattr(read_port, "bound_client_id", "")) != plan.client_id):
        raise JsonGovernedMutationBoundaryError("MUTATION_READ_PORT_CLIENT_UNBOUND")
    if plan.capability != "service.ticket.update":
        raise JsonGovernedMutationBoundaryError("MUTATION_READBACK_CAPABILITY_UNSUPPORTED")
    try:
        ticket_id = int(plan.target_id)
    except (TypeError, ValueError) as exc:
        raise JsonGovernedMutationBoundaryError("MUTATION_TARGET_NOT_TICKET") from exc
    response = read_port.execute("service.ticket.read", {"ticket_id": ticket_id})
    if response.get("status") != "succeeded":
        raise JsonGovernedMutationBoundaryError("MUTATION_READBACK_UNAVAILABLE")
    evidence = response.get("evidence")
    data = evidence.get("data") if isinstance(evidence, Mapping) else None
    if not isinstance(data, Mapping):
        raise JsonGovernedMutationBoundaryError("MUTATION_READBACK_DATA_MISSING")
    items = data.get("items")
    if items is None:
        item = data.get("item", data.get("record"))
        items = [item] if isinstance(item, Mapping) else None
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], Mapping):
        raise JsonGovernedMutationBoundaryError("MUTATION_READBACK_NOT_UNIQUE")
    ticket = items[0]
    expected = document.payload.get("expected_state", {})
    if (str(ticket.get("id")) != str(ticket_id)
            or str(ticket.get("companyID")) != plan.client_id
            or ticket.get("queueID") != expected.get("queue_id")
            or ticket.get("status") != expected.get("status_id")):
        raise JsonGovernedMutationBoundaryError("MUTATION_READBACK_STATE_MISMATCH")
    return dict(ticket)


def _assert_exact_mutation_intent(
    plan: JsonMutationPlan, document: PlaybookDocument,
) -> None:
    """Recalculate immutable source/target/argument intent before any claim."""
    if (plan.playbook_id != document.playbook_id or
        plan.playbook_version != document.version or
        plan.document_fingerprint != document.fingerprint or
        plan.capability != "service.ticket.update" or
        plan.step_id != "handoff_update" or
        plan.expected_verified_fields != frozenset({"queueID", "status"})):
        raise JsonGovernedMutationBoundaryError("MUTATION_EXACT_SOURCE_INTENT_REQUIRED")
    try:
        ticket_id = int(plan.target_id)
    except (TypeError, ValueError) as exc:
        raise JsonGovernedMutationBoundaryError("MUTATION_EXACT_TARGET_REQUIRED") from exc
    if plan.arguments != {"payload": {
        "id": ticket_id, "queueID": "Help Desk I", "status": "Human Review"
    }}:
        raise JsonGovernedMutationBoundaryError("MUTATION_ACTION_TARGET_OR_FIELDS_CHANGED")
    intent = {
        "run_id": plan.run_id, "client_id": plan.client_id,
        "target_id": plan.target_id,
        "source_fingerprint": document.fingerprint,
        "step_id": plan.step_id, "capability": plan.capability,
        "arguments": dict(plan.arguments),
        "approval_classification": plan.approval_classification,
        "required_readback_fields": sorted(plan.expected_verified_fields),
    }
    if (plan.approval_classification != "modifying" or
        sha256(_canonical(intent).encode()).hexdigest() != plan.intent_fingerprint):
        raise JsonGovernedMutationBoundaryError("MUTATION_INTENT_FINGERPRINT_CHANGED")


def _preflight_handoff(
    *,
    plan: JsonMutationPlan,
    document: PlaybookDocument,
    read_port: Any,
    source_snapshot: Mapping[str, Any],
    expected_note_body: str,
    source_status_label: str,
    review_reason: str,
    owned_by_jason: bool,
) -> None:
    """Build exact current ticket/managed-note facts from existing governed reads."""
    if (str(getattr(read_port, "client_id", "") or
            getattr(read_port, "bound_client_id", "")) != plan.client_id):
        raise JsonGovernedMutationBoundaryError("MUTATION_READ_PORT_CLIENT_UNBOUND")
    if plan.playbook_id != "unsupported_triage_human_review":
        raise JsonGovernedMutationBoundaryError("MUTATION_PREFLIGHT_NOT_IMPLEMENTED")
    if plan.capability != "service.ticket.update":
        raise JsonGovernedMutationBoundaryError("MUTATION_CAPABILITY_NOT_ALLOWED")
    try:
        ticket_id = int(plan.target_id)
    except (ValueError, TypeError) as exc:
        raise JsonGovernedMutationBoundaryError("MUTATION_INVALID_TICKET_ID") from exc
    allowlist = frozenset(document.payload.get("trigger", {}).get("exact_ticket_ids", ()))
    if ticket_id not in allowlist:
        raise JsonGovernedMutationBoundaryError("MUTATION_NOT_IN_SOURCE_PILOT")
    if str(source_snapshot.get("companyID")) != plan.client_id:
        raise JsonGovernedMutationBoundaryError("MUTATION_CLIENT_SCOPE_CHANGED")
    result = read_port.execute(
        "service.ticket.search", {"resource_id": ticket_id, "page_size": 2})
    notes = read_port.execute(
        "service.ticket.notes.search", {"ticket_id": ticket_id})
    try:
        evidence = handoff_identity_facts(
            source_snapshot=source_snapshot,
            source_queue="Jason",
            owned_by_jason=owned_by_jason,
            source_status_label=source_status_label,
            review_reason=review_reason,
            ticket_search_result=result,
            notes_search_result=notes,
            expected_note_body=expected_note_body,
            permitted_ticket_ids=allowlist,
        )
    except UntrustedTicketEvidence as exc:
        raise JsonGovernedMutationBoundaryError(
            "MUTATION_CURRENT_EVIDENCE_INCONCLUSIVE"
        ) from exc
    if evidence["ticket_id"] != ticket_id:
        raise JsonGovernedMutationBoundaryError("MUTATION_TARGET_CHANGED")


def dispatch_json_mutation_once(
    *,
    plan: JsonMutationPlan,
    document: PlaybookDocument,
    checkpoint: SQLiteJsonMutationCheckpoint,
    actions: GovernedAutonomyActionPort,
    read_port: Any,
    source_snapshot: Mapping[str, Any],
    expected_note_body: str,
    source_status_label: str,
    review_reason: str,
    owned_by_jason: bool,
) -> Mapping[str, Any]:
    """One-shot exact handoff, no automatic retry; existing authority required."""
    if (plan.document_fingerprint != document.fingerprint or
        plan.playbook_id != document.playbook_id or
        plan.playbook_version != document.version):
        raise JsonGovernedMutationBoundaryError("MUTATION_SOURCE_VERSION_CHANGED")
    _assert_exact_mutation_intent(plan, document)
    existing = checkpoint.read(plan)
    if existing is not None:
        state, new_claim = checkpoint.claim(plan)
        assert not new_claim
        return {
            "state": state, "provider_call_attempted": False,
            "requires_readback_reconciliation": state != "verified",
        }
    _preflight_handoff(
        plan=plan, document=document, read_port=read_port,
        source_snapshot=source_snapshot,
        expected_note_body=expected_note_body,
        source_status_label=source_status_label,
        review_reason=review_reason,
        owned_by_jason=owned_by_jason,
    )
    state, first = checkpoint.claim(plan)
    if not first:
        return {
            "state": state, "provider_call_attempted": False,
            "requires_readback_reconciliation": state != "verified",
        }
    scope = PlaybookScope(
        playbook_id=plan.playbook_id, playbook_version=plan.playbook_version,
        policy_id=f"playbook-autonomy:{plan.playbook_id}",
        required_action_capabilities=(plan.capability,),
    )
    try:
        response = actions.execute(scope, plan.capability, plan.arguments)
    except Exception:
        # Provider may have committed before a transport error. No retry.
        return {
            "state": "indeterminate", "provider_call_attempted": True,
            "requires_readback_reconciliation": True,
        }
    try:
        if not _readback_verified(plan, response):
            raise JsonGovernedMutationBoundaryError("MUTATION_ACTION_PROOF_INCOMPLETE")
        observed = _bounded_ticket_read(read_port, plan=plan, document=document)
    except Exception:
        return {
            "state": "indeterminate", "provider_call_attempted": True,
            "requires_readback_reconciliation": True,
        }
    checkpoint.complete(plan, evidence=observed)
    return {
        "state": "verified", "provider_call_attempted": True,
        "requires_readback_reconciliation": False,
    }


def reconcile_indeterminate_json_mutation(
    *,
    plan: JsonMutationPlan,
    document: PlaybookDocument,
    checkpoint: SQLiteJsonMutationCheckpoint,
    read_port: Any,
) -> bool:
    """Fresh independent governed PSA read; no caller-supplied success flags."""
    _assert_exact_mutation_intent(plan, document)
    existing = checkpoint.read(plan)
    if not existing or existing["state"] != "indeterminate":
        return False
    if (existing["intent_fingerprint"] != plan.intent_fingerprint or
        existing["client_id"] != plan.client_id or
        existing["target_id"] != plan.target_id or
        existing["document_fingerprint"] != document.fingerprint):
        raise JsonGovernedMutationBoundaryError("MUTATION_RECONCILE_SCOPE_CHANGED")
    try:
        observed = _bounded_ticket_read(
            read_port, plan=plan, document=document,
        )
    except JsonGovernedMutationBoundaryError:
        return False
    checkpoint.complete(plan, evidence=observed)
    return True
