"""Isolated governed-read JSON integration, using the existing interpreter.

This is a source-only integration component for the existing JSON architecture,
not a registry, production dispatcher, alternative execution authority, or
provider client. Read-capability bindings are injected from the existing
Central Orchestrator port; no mutation can be dispatched in this mode.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping

from .playbook_autonomy_approval import PlaybookAutonomyApproval
from .playbook_document import PlaybookDocument
from .playbook_runtime import JsonPlaybookInterpreter

TERMINALS = frozenset({"complete", "human_review", "escalate"})
READ_TYPES = frozenset({"diagnostic", "verification"})


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class JsonShadowBoundaryError(RuntimeError):
    """A boundary or authoritative evidence failure; no mutation executed."""


@dataclass(frozen=True)
class JsonShadowResult:
    status: str
    step_id: str
    fingerprint: str
    history: tuple[Mapping[str, Any], ...]
    facts: Mapping[str, Any]
    due_at: str | None = None


class SQLiteJsonShadowState:
    """Private isolated run checkpoint, not a second playbook registry."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=10.0)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        os.chmod(self.path, 0o600)
        self.db.execute("""CREATE TABLE IF NOT EXISTS json_shadow_runs (
            run_id TEXT PRIMARY KEY,
            playbook_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            client_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            status TEXT NOT NULL,
            step_id TEXT NOT NULL,
            facts_json TEXT NOT NULL,
            history_json TEXT NOT NULL,
            due_at TEXT
        )""")

    def get(self, run_id: str) -> Mapping[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM json_shadow_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        keys = ("run_id", "playbook_id", "fingerprint", "client_id",
                "target_id", "status", "step_id", "facts_json",
                "history_json", "due_at")
        return dict(zip(keys, row))

    def put(self, row: Mapping[str, Any]) -> None:
        with self.db:
            self.db.execute("""INSERT INTO json_shadow_runs(
                run_id, playbook_id, fingerprint, client_id, target_id, status,
                step_id, facts_json, history_json, due_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id) DO UPDATE SET
                status=excluded.status, step_id=excluded.step_id,
                facts_json=excluded.facts_json,
                history_json=excluded.history_json, due_at=excluded.due_at
            WHERE json_shadow_runs.fingerprint=excluded.fingerprint
              AND json_shadow_runs.client_id=excluded.client_id
              AND json_shadow_runs.target_id=excluded.target_id
              AND json_shadow_runs.playbook_id=excluded.playbook_id
            """, tuple(row[key] for key in (
                "run_id", "playbook_id", "fingerprint", "client_id", "target_id",
                "status", "step_id", "facts_json", "history_json", "due_at")))
            if self.db.execute("SELECT changes()").fetchone()[0] != 1:
                raise JsonShadowBoundaryError("CHECKPOINT_IDENTITY_CHANGED")

    def close(self) -> None:
        self.db.close()


class GovernedJsonShadowIntegration:
    """Checkpointed read-only bridge to the canonical JSON interpreter.

    The injected read port must already be a governed observe-only port and
    the server-owned normalizer must prove source/provenance. No JSON metadata
    is treated as an approval. Mutations are never passed to any action port.
    """

    def __init__(
        self, *,
        document: PlaybookDocument,
        state: SQLiteJsonShadowState,
        read_port: Any,
        read_capabilities: frozenset[str],
        normalize: Callable[[str, Mapping[str, Any], Mapping[str, Any]],
                            Mapping[str, Any]],
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        promotion_store: Any | None = None,
        promotion_fact_name: str | None = None,
    ) -> None:
        if document.autonomy_activation != "shadow":
            raise JsonShadowBoundaryError("SHADOW_ACTIVATION_REQUIRED")
        if document.payload.get("scope", {}).get("direct_provider_access") is not False:
            raise JsonShadowBoundaryError("DIRECT_PROVIDER_ACCESS_FORBIDDEN")
        if not isinstance(read_capabilities, frozenset):
            raise JsonShadowBoundaryError("GOVERNED_READ_CAPABILITIES_REQUIRED")
        self.document = document
        self.interpreter = JsonPlaybookInterpreter(document)
        self.state = state
        self.read_port = read_port
        self.read_capabilities = read_capabilities
        self.normalize = normalize
        self.clock = clock
        if (promotion_store is None) != (promotion_fact_name is None):
            raise JsonShadowBoundaryError("EXACT_PROMOTION_ADAPTER_INCOMPLETE")
        if promotion_fact_name is not None and (
            not promotion_fact_name.endswith("_promotion_verified")
            or not any(
                step.get("type") == "decision" and any(
                    branch.get("when", {}).get("fact") == promotion_fact_name
                    for branch in step.get("branches", ())
                ) for step in document.payload["steps"]
            )
        ):
            raise JsonShadowBoundaryError("EXACT_PROMOTION_GATE_NOT_IN_DOCUMENT")
        self.promotion_store = promotion_store
        self.promotion_fact_name = promotion_fact_name
        self.mutation_capabilities = tuple(sorted({
            str(step["capability"]) for step in document.payload["steps"]
            if step.get("type") in {"remediation", "document"}
            and step.get("capability")
        }))

    def run(
        self, *, run_id: str, client_id: str, target_id: str,
        trusted_seed: Mapping[str, Any], max_steps: int = 100,
    ) -> JsonShadowResult:
        if not all(isinstance(x, str) and x.strip() and len(x) <= 128
                   for x in (run_id, client_id, target_id)):
            raise JsonShadowBoundaryError("EXACT_RUN_IDENTITY_REQUIRED")
        if not 1 <= max_steps <= 200:
            raise JsonShadowBoundaryError("STEP_BUDGET_INVALID")
        # The shared read port must be constructed by a trusted authority
        # factory scoped to the same client. Merely putting client_id in JSON
        # or in a request payload does not prove tenant isolation.
        if str(getattr(self.read_port, "bound_client_id", "") or "") != client_id:
            raise JsonShadowBoundaryError("GOVERNED_READ_PORT_CLIENT_SCOPE_UNVERIFIED")
        row = self.state.get(run_id)
        if row is None:
            if not isinstance(trusted_seed, Mapping):
                raise JsonShadowBoundaryError("TRUSTED_SEED_REQUIRED")
            facts = dict(trusted_seed)
            # Until an exact server-owned context loader is integrated, permit
            # only the two immutable targeting identifiers from the caller.
            # All health, eligibility, company and approval facts must be
            # derived from governed observations, never caller assertion.
            if set(facts) != {"client_id", "target_id"}:
                raise JsonShadowBoundaryError("SEED_FACTS_NOT_TRUSTED")
            if str(facts.get("client_id") or "") != client_id or (
                str(facts.get("target_id") or "") != target_id
            ):
                raise JsonShadowBoundaryError("SEED_IDENTITY_MISMATCH")
            record = {
                "run_id": run_id, "playbook_id": self.document.playbook_id,
                "fingerprint": self.document.fingerprint,
                "client_id": client_id, "target_id": target_id,
                "status": "ready", "step_id": self.document.entry_step,
                "facts_json": _json(facts), "history_json": "[]", "due_at": None,
            }
            self.state.put(record)
        else:
            if (row["fingerprint"] != self.document.fingerprint or
                row["playbook_id"] != self.document.playbook_id or
                row["client_id"] != client_id or row["target_id"] != target_id):
                raise JsonShadowBoundaryError("RUN_RESUME_IDENTITY_OR_VERSION_CHANGED")
            record = dict(row)
            facts = json.loads(row["facts_json"])
            history = json.loads(row["history_json"])
            if row["status"] in {
                "completed_readonly", "blocked_mutation", "needs_human_review",
                "failed_closed",
            }:
                return JsonShadowResult(row["status"], row["step_id"],
                                        self.document.fingerprint,
                                        tuple(history), facts, row["due_at"])
            if row["status"] == "waiting_event":
                return JsonShadowResult("waiting_event", row["step_id"],
                                        self.document.fingerprint,
                                        tuple(history), facts, row["due_at"])
            if row["due_at"] is not None and self.clock() < datetime.fromisoformat(row["due_at"]):
                return JsonShadowResult("waiting", row["step_id"],
                                        self.document.fingerprint,
                                        tuple(history), facts, row["due_at"])
            # A bounded local inspection pass may be resumed safely. The
            # prior completed reads stay persisted and are not redispatched.
            record["status"] = "ready"
            record["due_at"] = None

        for _ in range(max_steps):
            facts = json.loads(record["facts_json"])
            history = json.loads(record["history_json"])
            try:
                ephemeral = facts
                current_definition = self.interpreter._steps[record["step_id"]]
                if (
                    self.promotion_store is not None
                    and current_definition["type"] == "decision"
                ):
                    # Current exact promotion is only a planning input in
                    # shadow mode, never persisted as a standing authority or
                    # used to execute a mutation.
                    if not any(
                        event.get("result") == "governed_read_normalized"
                        for event in history
                    ):
                        raise JsonShadowBoundaryError("NO_GOVERNED_READ_BEFORE_PROMOTION")
                    found = self.promotion_store.find_scope_approved(
                        playbook_id=self.document.playbook_id,
                        playbook_version=self.document.version,
                        policy_id=f"playbook-autonomy:{self.document.playbook_id}",
                        required_capabilities=self.mutation_capabilities,
                        now=self.clock(),
                    )
                    if found is not None and not isinstance(found, PlaybookAutonomyApproval):
                        raise JsonShadowBoundaryError("PROMOTION_RECEIPT_TYPE_INVALID")
                    authorized = found is not None and all(
                        found.authorizes(
                            playbook_id=self.document.playbook_id,
                            playbook_version=self.document.version,
                            policy_id=f"playbook-autonomy:{self.document.playbook_id}",
                            capability=name, now=self.clock(),
                        ) for name in self.mutation_capabilities
                    )
                    ephemeral = {**facts, self.promotion_fact_name: authorized}
                instruction = self.interpreter.instruction(
                    step_id=record["step_id"], facts=ephemeral)
            except (KeyError, ValueError, JsonShadowBoundaryError) as exc:
                record["status"] = "failed_closed"
                history.append({"step_id": record["step_id"], "result": type(exc).__name__})
                record["history_json"] = _json(history)
                self.state.put(record)
                break
            event = {"step_id": instruction.step_id, "type": instruction.step_type}
            if instruction.step_type in TERMINALS:
                record["step_id"] = instruction.step_id
                read_count = sum(
                    h.get("result") == "governed_read_normalized" for h in history
                )
                if instruction.step_type == "complete" and read_count == 0:
                    # A bare terminal declaration cannot prove an observation
                    # or a completed real-world workflow.
                    record["status"] = "failed_closed"
                    event["result"] = "NO_AUTHORITATIVE_READ_EVIDENCE"
                else:
                    record["status"] = ("completed_readonly" if instruction.step_type == "complete"
                                        else "needs_human_review")
                history.append(event)
            elif instruction.step_type in READ_TYPES:
                capability = instruction.capability
                if (capability not in self.read_capabilities or
                    capability not in self.document.capabilities):
                    record["status"] = "failed_closed"
                    event["result"] = "READ_CAPABILITY_DENIED"
                    history.append(event)
                else:
                    # No raw provider output is persisted; server-owned
                    # reduction returns narrowly scoped JSON-serializable facts.
                    try:
                        result = self.read_port.execute(capability, dict(instruction.arguments))
                        if not isinstance(result, Mapping) or result.get("status") != "succeeded":
                            raise JsonShadowBoundaryError("GOVERNED_READ_FAILED")
                        observed = dict(self.normalize(capability, result, facts))
                        if any(k.endswith("_promotion_verified") or
                               k.endswith("_readback_verified") for k in observed):
                            raise JsonShadowBoundaryError("READ_REDUCER_MUST_NOT_MINT_APPROVAL")
                        if any(k in {"client_id", "target_id"} and facts.get(k) != v
                               for k, v in observed.items()):
                            raise JsonShadowBoundaryError("READ_CHANGED_SCOPE_IDENTITY")
                        facts.update(observed)
                        record["facts_json"] = _json(facts)
                        record["step_id"] = self.interpreter.next_step(
                            instruction.step_id, facts=facts)
                        event["result"] = "governed_read_normalized"
                        event["evidence_sha256"] = sha256(_json(observed).encode()).hexdigest()
                        history.append(event)
                    except Exception as exc:
                        record["status"] = "failed_closed"
                        event["result"] = type(exc).__name__
                        history.append(event)
            elif instruction.step_type == "wait":
                step = self.interpreter._steps[instruction.step_id]
                seconds = step.get("seconds")
                record["step_id"] = self.interpreter.next_step(instruction.step_id, facts=facts)
                if seconds is not None:
                    record["due_at"] = (self.clock() + timedelta(seconds=seconds)).isoformat()
                    record["status"] = "waiting"
                else:
                    # No fabricated external event. Human/normal scheduler must
                    # explicitly resume through a separately trusted adapter.
                    record["status"] = "waiting_event"
                history.append(event)
            else:
                # Document steps and every mutating operation fail closed here.
                # A future execution path must use exact approved existing
                # Central Orchestrator port and verified provider receipts.
                record["step_id"] = instruction.step_id
                record["status"] = "blocked_mutation"
                event["capability"] = instruction.capability
                event["result"] = "NO_MUTATION_IN_SHADOW"
                history.append(event)
            record["history_json"] = _json(history)
            self.state.put(record)
            if record["status"] != "ready":
                break
        else:
            record["status"] = "step_budget_exhausted"
            self.state.put(record)

        return JsonShadowResult(
            record["status"], record["step_id"], self.document.fingerprint,
            tuple(json.loads(record["history_json"])),
            json.loads(record["facts_json"]), record["due_at"],
        )
