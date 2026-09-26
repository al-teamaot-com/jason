"""Production autonomous ticket worker for bounded approved playbooks.

The worker is deliberately narrower than generic "AI autonomy".  It continuously
reviews the approved Autotask intake queues, claims only tickets that satisfy a
deterministic operational playbook, executes only capabilities covered by an
exact durable owner promotion, verifies provider outcomes independently, and
fails closed whenever identity, evidence, authority, or verification is
ambiguous.

The first production executor is the health-only Datto EDR/AV path.  It may:
* claim an exact ticket with an existing active CI whose DRMM UID is authoritative;
* run the standing-safe EDR/AV health component;
* when health is not proven, run the separately standing-safe Force Reinstall
  component once;
* rerun the authoritative health component;
* document and close only after Status=Healthy is observed.

It never handles threat-triggered tickets, never schedules a reboot, never runs
generic PowerShell, and never performs the clean-uninstall recovery branch.
Those remain approval-gated by design.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from autonomous_remediation.autonomous_principal import (
    AutonomousRequestFactory,
    StandingPolicyAuthorization,
)
from autonomous_remediation.autotask_queue_source import (
    AutotaskQueueDiscoveryConfig,
    AutotaskQueueSource,
)
from autonomous_remediation.playbook_autonomy_approval import (
    SQLitePlaybookAutonomyApprovalStore,
)
from autonomous_remediation.datto_edr_av_playbook import PLAYBOOK_VERSION as EDR_PLAYBOOK_VERSION
from autonomous_remediation.datto_edr_av_runtime_contract import VERIFIED_COMPONENTS


@dataclass(frozen=True, slots=True)
class PlaybookScope:
    playbook_id: str
    playbook_version: str
    policy_id: str
    required_action_capabilities: tuple[str, ...]


PLAYBOOK_ID = "datto_edr_av"
PLAYBOOK_VERSION = EDR_PLAYBOOK_VERSION
POLICY_ID = "playbook-autonomy:datto_edr_av"
REQUIRED_ACTION_CAPABILITIES = (
    "automation.component.execute",
    "service.ticket.note.create",
    "service.ticket.update",
)
EDR_SCOPE = PlaybookScope(
    playbook_id=PLAYBOOK_ID,
    playbook_version=PLAYBOOK_VERSION,
    policy_id=POLICY_ID,
    required_action_capabilities=REQUIRED_ACTION_CAPABILITIES,
)
DNS_SCOPE = PlaybookScope(
    playbook_id="dns_agent_diagnostic",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:dns_agent_diagnostic",
    required_action_capabilities=REQUIRED_ACTION_CAPABILITIES,
)
PLAYBOOK_SCOPES = {
    EDR_SCOPE.playbook_id: EDR_SCOPE,
    DNS_SCOPE.playbook_id: DNS_SCOPE,
}

HEALTH_COMPONENT_NAME = "Check Datto EDR/AV Status AOT Ver 12122025-1"
REPAIR_COMPONENT_NAME = "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024"
DNS_DIAGNOSTIC_COMPONENT_NAME = "DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026"
DNS_DIAGNOSTIC_COMPONENT_UID = "c3340a58-48d5-457b-bc30-5fd79e5ad8b1"
TERMINAL_PHASES = frozenset({"complete", "escalated", "blocked", "approval_pending"})


class OperationalAutonomyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OperationalWork:
    ticket_id: int
    ticket_number: str
    title: str
    playbook_id: str
    source_queue: str
    company_id: int
    configuration_item_id: int
    device_uid: str
    hostname: str
    phase: str
    job_uid: str | None = None
    component_uid: str | None = None
    repair_attempts: int = 0
    last_reason: str = ""
    updated_at: str = ""


class SQLiteOperationalWorkStore:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS autonomy_operational_work (
        ticket_id INTEGER PRIMARY KEY,
        ticket_number TEXT NOT NULL,
        title TEXT NOT NULL,
        playbook_id TEXT NOT NULL DEFAULT 'datto_edr_av',
        source_queue TEXT NOT NULL,
        company_id INTEGER NOT NULL,
        configuration_item_id INTEGER NOT NULL,
        device_uid TEXT NOT NULL,
        hostname TEXT NOT NULL,
        phase TEXT NOT NULL,
        job_uid TEXT,
        component_uid TEXT,
        repair_attempts INTEGER NOT NULL DEFAULT 0,
        last_reason TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL
    );
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(self.path), timeout=10.0, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(self._SCHEMA)
        columns = {
            str(row["name"])
            for row in self._connection.execute(
                "PRAGMA table_info(autonomy_operational_work)"
            ).fetchall()
        }
        if "playbook_id" not in columns:
            self._connection.execute(
                "ALTER TABLE autonomy_operational_work "
                "ADD COLUMN playbook_id TEXT NOT NULL DEFAULT 'datto_edr_av'"
            )
        os.chmod(self.path, 0o600)

    def get(self, ticket_id: int) -> OperationalWork | None:
        row = self._connection.execute(
            "SELECT * FROM autonomy_operational_work WHERE ticket_id=?",
            (int(ticket_id),),
        ).fetchone()
        return None if row is None else self._row(row)

    def list_open(self) -> tuple[OperationalWork, ...]:
        rows = self._connection.execute(
            "SELECT * FROM autonomy_operational_work "
            "WHERE phase NOT IN ('complete','escalated','blocked','approval_pending') "
            "ORDER BY updated_at,ticket_id"
        ).fetchall()
        return tuple(self._row(row) for row in rows)

    def put(self, work: OperationalWork) -> None:
        value = work.updated_at or datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO autonomy_operational_work(
                    ticket_id,ticket_number,title,playbook_id,source_queue,company_id,
                    configuration_item_id,device_uid,hostname,phase,job_uid,
                    component_uid,repair_attempts,last_reason,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ticket_id) DO UPDATE SET
                    ticket_number=excluded.ticket_number,
                    title=excluded.title,
                    playbook_id=excluded.playbook_id,
                    source_queue=excluded.source_queue,
                    company_id=excluded.company_id,
                    configuration_item_id=excluded.configuration_item_id,
                    device_uid=excluded.device_uid,
                    hostname=excluded.hostname,
                    phase=excluded.phase,
                    job_uid=excluded.job_uid,
                    component_uid=excluded.component_uid,
                    repair_attempts=excluded.repair_attempts,
                    last_reason=excluded.last_reason,
                    updated_at=excluded.updated_at
                """,
                (
                    work.ticket_id,
                    work.ticket_number,
                    work.title,
                    work.playbook_id,
                    work.source_queue,
                    work.company_id,
                    work.configuration_item_id,
                    work.device_uid,
                    work.hostname,
                    work.phase,
                    work.job_uid,
                    work.component_uid,
                    work.repair_attempts,
                    work.last_reason,
                    value,
                ),
            )

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _row(row: sqlite3.Row) -> OperationalWork:
        return OperationalWork(
            ticket_id=int(row["ticket_id"]),
            ticket_number=str(row["ticket_number"]),
            title=str(row["title"]),
            playbook_id=str(row["playbook_id"]),
            source_queue=str(row["source_queue"]),
            company_id=int(row["company_id"]),
            configuration_item_id=int(row["configuration_item_id"]),
            device_uid=str(row["device_uid"]),
            hostname=str(row["hostname"]),
            phase=str(row["phase"]),
            job_uid=row["job_uid"],
            component_uid=row["component_uid"],
            repair_attempts=int(row["repair_attempts"]),
            last_reason=str(row["last_reason"]),
            updated_at=str(row["updated_at"]),
        )


class GovernedAutonomyActionPort:
    def __init__(
        self,
        *,
        request_factory: AutonomousRequestFactory,
        orchestrator,
        promotion_store: SQLitePlaybookAutonomyApprovalStore,
    ) -> None:
        self.request_factory = request_factory
        self.orchestrator = orchestrator
        self.promotion_store = promotion_store

    def _standing_policy(
        self, scope: PlaybookScope, capability: str
    ) -> StandingPolicyAuthorization:
        promotion = self.promotion_store.find_scope_approved(
            playbook_id=scope.playbook_id,
            playbook_version=scope.playbook_version,
            policy_id=scope.policy_id,
            required_capabilities=scope.required_action_capabilities,
        )
        if promotion is None or capability not in promotion.allowed_capabilities:
            raise OperationalAutonomyError(
                f"{scope.playbook_id} lacks exact durable owner promotion"
            )
        return StandingPolicyAuthorization(
            playbook_id=scope.playbook_id,
            playbook_version=scope.playbook_version,
            policy_id=scope.policy_id,
            promotion_approval_id=promotion.approval_id,
        )

    def execute(
        self,
        scope: PlaybookScope,
        capability: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        request = self.request_factory.build(
            capability_name=capability,
            arguments=dict(arguments),
            client_id=None,
            standing_policy=self._standing_policy(scope, capability),
        )
        result = self.orchestrator.execute(request)
        status = getattr(getattr(result, "status", None), "value", "")
        if status != "succeeded":
            raise OperationalAutonomyError(
                "governed autonomous action failed: "
                + str(getattr(result, "error_code", None) or getattr(result, "reason_codes", ()))
            )
        output = getattr(result, "output", None)
        return dict(output) if isinstance(output, Mapping) else {}


class OperationalAutonomyMaintenance:
    """Bounded production ticket worker.

    The runtime's HTTP server invokes tick frequently on its owning thread.  This
    object performs work only when its cadence is due, so it never spawns a
    competing SQLite thread or a second unmanaged scheduler.
    """

    def __init__(
        self,
        *,
        queue_source: AutotaskQueueSource,
        reads,
        actions: GovernedAutonomyActionPort,
        store: SQLiteOperationalWorkStore,
        promotion_store: SQLitePlaybookAutonomyApprovalStore,
        max_active_work_items: int = 2,
        interval_seconds: int = 60,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 1 <= int(max_active_work_items) <= 20:
            raise ValueError("max_active_work_items must be between 1 and 20")
        if int(interval_seconds) < 30:
            raise ValueError("operational autonomy interval must be at least 30 seconds")
        self.queue_source = queue_source
        self.reads = reads
        self.actions = actions
        self.store = store
        self.promotion_store = promotion_store
        self.max_active_work_items = int(max_active_work_items)
        self.interval_seconds = int(interval_seconds)
        self.monotonic = monotonic
        self._next_due = 0.0

    def tick(self) -> None:
        now = self.monotonic()
        if now < self._next_due:
            return
        self._next_due = now + self.interval_seconds

        try:
            candidates = tuple(self.queue_source.reconcile_candidates())
        except Exception:
            # Provider/read failures are never authority to mutate or redispatch.
            # A later cadence retry will reconcile again.
            return
        by_id = {int(item.resource_id): item for item in candidates}

        active = list(self.store.list_open())
        processed: set[int] = set()
        for work in active[: self.max_active_work_items]:
            candidate = by_id.get(work.ticket_id)
            if candidate is None:
                self._block(
                    work,
                    "Ticket left the governed queue set while autonomous work was active.",
                )
                continue
            try:
                self._advance(work, candidate.context)
            except Exception as exc:
                self._block(
                    work,
                    f"Execution failed closed: {type(exc).__name__}: {str(exc)[:350]}",
                )
            processed.add(work.ticket_id)

        slots = max(0, self.max_active_work_items - len(self.store.list_open()))
        if slots == 0:
            return

        eligible: list[tuple[Any, PlaybookScope]] = []
        for item in candidates:
            if (
                int(item.resource_id) in processed
                or self.store.get(int(item.resource_id)) is not None
            ):
                continue
            scope = self._match_scope(item.context)
            if scope is None or not self._scope_is_promoted(scope):
                continue
            eligible.append((item, scope))

        eligible.sort(
            key=lambda pair: (
                -int(pair[0].urgent),
                -int(pair[0].owned_by_jason),
                -pair[0].priority,
                int(pair[0].resource_id),
            )
        )
        for candidate, scope in eligible[:slots]:
            try:
                work = self._admit(candidate, scope)
                self._advance(work, candidate.context)
            except Exception as exc:
                self._record_admission_failure(candidate, scope, exc)

    @staticmethod
    def _is_health_only_edr_ticket(ticket: Mapping[str, Any]) -> bool:
        title = str(ticket.get("title") or "").strip().casefold()
        return (
            "antivirus status" in title
            and "security threat detected" not in title
        )

    @staticmethod
    def _is_dns_agent_ticket(ticket: Mapping[str, Any]) -> bool:
        title = str(ticket.get("title") or "").strip().casefold()
        return "dns agent" in title or "dnsfilter" in title

    def _match_scope(self, ticket: Mapping[str, Any]) -> PlaybookScope | None:
        if self._is_health_only_edr_ticket(ticket):
            return EDR_SCOPE
        if self._is_dns_agent_ticket(ticket):
            return DNS_SCOPE
        return None

    def _scope_is_promoted(self, scope: PlaybookScope) -> bool:
        return self.promotion_store.find_scope_approved(
            playbook_id=scope.playbook_id,
            playbook_version=scope.playbook_version,
            policy_id=scope.policy_id,
            required_capabilities=scope.required_action_capabilities,
        ) is not None

    @staticmethod
    def _scope_for_work(work: OperationalWork) -> PlaybookScope:
        scope = PLAYBOOK_SCOPES.get(work.playbook_id)
        if scope is None:
            raise OperationalAutonomyError(
                f"unknown autonomous playbook scope: {work.playbook_id}"
            )
        return scope

    def _admit(self, candidate, scope: PlaybookScope) -> OperationalWork:
        ticket = candidate.context
        ticket_id = self._positive_int(ticket.get("id"), "ticket id")
        company_id = self._positive_int(ticket.get("companyID"), "company id")
        ci_id = self._positive_int(
            ticket.get("configurationItemID"), "configuration item id"
        )

        ci = self._read_data(
            "service.configuration.read", {"resource_id": ci_id}
        )
        if "item" in ci and isinstance(ci["item"], Mapping):
            ci = dict(ci["item"])
        if int(ci.get("id") or 0) != ci_id:
            raise OperationalAutonomyError("configuration identity readback mismatch")
        if int(ci.get("companyID") or -1) != company_id:
            raise OperationalAutonomyError("configuration belongs to another company")
        if ci.get("isActive") is not True:
            raise OperationalAutonomyError("configuration is inactive")

        device_uid = str(ci.get("referenceNumber") or "").strip()
        hostname = str(ci.get("referenceTitle") or "").strip()
        if not device_uid or not hostname:
            raise OperationalAutonomyError("configuration lacks exact DRMM identity")

        endpoint = self._read_record(
            "endpoint.device.read", {"resource_id": device_uid}
        )
        endpoint_uid = str(
            endpoint.get("resource_id")
            or endpoint.get("uid")
            or endpoint.get("deviceUid")
            or ""
        ).strip()
        endpoint_hostname = str(
            endpoint.get("hostname")
            or endpoint.get("hostName")
            or endpoint.get("name")
            or ""
        ).strip()
        if endpoint_uid != device_uid:
            raise OperationalAutonomyError("DRMM device identity mismatch")
        if endpoint_hostname.casefold() != hostname.casefold():
            raise OperationalAutonomyError(
                "Autotask CI and DRMM hostname do not match"
            )
        if endpoint.get("online") is not True:
            raise OperationalAutonomyError("endpoint is not currently online")

        return OperationalWork(
            ticket_id=ticket_id,
            ticket_number=str(ticket.get("ticketNumber") or ticket.get("ticket_number") or ticket_id),
            title=str(ticket.get("title") or ""),
            playbook_id=scope.playbook_id,
            source_queue=str(candidate.source_queue),
            company_id=company_id,
            configuration_item_id=ci_id,
            device_uid=device_uid,
            hostname=hostname,
            phase="claim",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _advance(self, work: OperationalWork, ticket: Mapping[str, Any]) -> None:
        scope = self._scope_for_work(work)
        if not self._scope_is_promoted(scope):
            self._block(work, "Durable playbook promotion is no longer active.")
            return

        if work.phase == "claim":
            self.actions.execute(
                scope,
                "service.ticket.update",
                {
                    "payload": {
                        "id": work.ticket_id,
                        "queueID": "Jason",
                        "status": "In Progress",
                        "billingCodeID": "Remote Support",
                    }
                },
            )
            next_phase = (
                "health_dispatch"
                if work.playbook_id == EDR_SCOPE.playbook_id
                else "dns_diagnostic_dispatch"
            )
            work = self._replace(work, phase=next_phase)
            self.store.put(work)

        if work.playbook_id == DNS_SCOPE.playbook_id:
            if work.phase == "dns_diagnostic_dispatch":
                self._dispatch_component(
                    work,
                    DNS_DIAGNOSTIC_COMPONENT_NAME,
                    "dns_diagnostic_wait",
                )
                return
            if work.phase == "dns_diagnostic_wait":
                self._poll_dns_diagnostic(work)
                return

        if work.phase == "health_dispatch":
            self._dispatch_component(work, HEALTH_COMPONENT_NAME, "health_wait")
            return

        if work.phase == "repair_dispatch":
            self._dispatch_component(work, REPAIR_COMPONENT_NAME, "repair_wait")
            return

        if work.phase == "verify_dispatch":
            self._dispatch_component(work, HEALTH_COMPONENT_NAME, "verify_wait")
            return

        if work.phase in {"health_wait", "repair_wait", "verify_wait"}:
            self._poll_job(work)

    def _dispatch_component(
        self, work: OperationalWork, component_name: str, next_phase: str
    ) -> None:
        scope = self._scope_for_work(work)
        if component_name == DNS_DIAGNOSTIC_COMPONENT_NAME:
            component_uid = DNS_DIAGNOSTIC_COMPONENT_UID
            resolved_component_name = DNS_DIAGNOSTIC_COMPONENT_NAME
            step = "dns_diagnostic"
        else:
            identity = VERIFIED_COMPONENTS[component_name]
            component_uid = identity.uid
            resolved_component_name = identity.name
            step = (
                "health"
                if next_phase == "health_wait"
                else "repair"
                if next_phase == "repair_wait"
                else "verify"
            )
        output = self.actions.execute(
            scope,
            "automation.component.execute",
            {
                "device_uid": work.device_uid,
                "component_uid": component_uid,
                "component_name": resolved_component_name,
                "variables": {},
                "job_name": f"Jason autonomous {scope.playbook_id} {step} T{work.ticket_id}",
                "idempotency_key": (
                    f"autonomy:{scope.playbook_id}:{scope.playbook_version}:"
                    f"{work.ticket_id}:{work.device_uid}:{step}"
                ),
            },
        )
        data = self._action_data(output)
        job_uid = str(data.get("job_uid") or "").strip()
        if not job_uid:
            raise OperationalAutonomyError("component dispatch returned no durable job UID")
        repair_attempts = work.repair_attempts + (1 if step == "repair" else 0)
        self.store.put(
            self._replace(
                work,
                phase=next_phase,
                job_uid=job_uid,
                component_uid=component_uid,
                repair_attempts=repair_attempts,
                last_reason=f"Dispatched {resolved_component_name}.",
            )
        )

    def _poll_dns_diagnostic(self, work: OperationalWork) -> None:
        if not work.job_uid or not work.component_uid:
            self._block(work, "Persisted DNS diagnostic job identity is incomplete.")
            return
        job_data = self._read_data(
            "automation.job.read", {"resource_id": work.job_uid}
        )
        job = job_data.get("job") if isinstance(job_data.get("job"), Mapping) else job_data
        status = str(job.get("status") or "").strip().casefold()
        if status in {"active", "running", "queued", "pending", "scheduled"}:
            return
        if status in {"stale_or_unknown", "unknown"}:
            self._block(
                work,
                "DNS diagnostic job state became stale or unknown; no redispatch allowed.",
            )
            return
        if status not in {"completed", "complete", "success", "succeeded", "finished"}:
            self._escalate(
                work,
                f"DNS diagnostic job ended with provider status {status or 'unknown'}.",
            )
            return

        output = self._read_data(
            "automation.job.output.read",
            {
                "resource_id": work.job_uid,
                "device_uid": work.device_uid,
                "component_uid": work.component_uid,
                "stream": "stdout",
            },
        )
        text = self._output_text(output)
        if not text:
            self._block(work, "DNS diagnostic completed without readable stdout.")
            return

        summary = self._bounded_health_summary(text)
        self._write_note(
            work,
            (
                "Jason autonomous DNS Agent diagnostic completed using the "
                "standing-safe dedicated diagnostic component. "
                f"Evidence summary: {summary}. "
                "No service restart, DNS/NIC change, reinstall, uninstall, registry "
                "change, or reboot was attempted. Repair/install remains separately "
                "gated pending its controlled acceptance."
            ),
            "Jason - Autonomous DNS Agent Diagnostic",
        )
        self.store.put(
            self._replace(
                work,
                phase="escalated",
                job_uid=None,
                component_uid=None,
                last_reason=(
                    "Standing-safe DNS diagnostic completed; remediation branch "
                    "requires separate accepted authority."
                ),
            )
        )

    def _poll_job(self, work: OperationalWork) -> None:
        if not work.job_uid or not work.component_uid:
            self._block(work, "Persisted automation job identity is incomplete.")
            return
        job_data = self._read_data(
            "automation.job.read", {"resource_id": work.job_uid}
        )
        job = job_data.get("job") if isinstance(job_data.get("job"), Mapping) else job_data
        status = str(job.get("status") or "").strip().casefold()
        if status in {"active", "running", "queued", "pending", "scheduled"}:
            return
        if status in {"stale_or_unknown", "unknown"}:
            self._block(work, "Provider job state became stale or unknown; no redispatch allowed.")
            return

        successful_terminal = {
            "completed",
            "complete",
            "success",
            "succeeded",
            "finished",
        }
        if work.phase == "repair_wait":
            if status not in successful_terminal:
                self._escalate(
                    work,
                    f"EDR repair job ended with provider status {status or 'unknown'}.",
                )
                return
            self.store.put(
                self._replace(
                    work,
                    phase="verify_dispatch",
                    job_uid=None,
                    component_uid=None,
                    last_reason=(
                        "Repair job completed; authoritative health verification "
                        "required."
                    ),
                )
            )
            return

        if status not in successful_terminal:
            self._block(
                work,
                "Authoritative health job ended without provider success "
                f"(status={status or 'unknown'}); no remediation was dispatched.",
            )
            return

        output = self._read_data(
            "automation.job.output.read",
            {
                "resource_id": work.job_uid,
                "device_uid": work.device_uid,
                "component_uid": work.component_uid,
                "stream": "stdout",
            },
        )
        text = self._output_text(output)
        if not text:
            self._block(work, "Authoritative health job produced no readable stdout.")
            return

        if self._status_healthy(text):
            self._complete(work, text)
            return

        if work.phase == "health_wait" and work.repair_attempts == 0:
            self.store.put(
                self._replace(
                    work,
                    phase="repair_dispatch",
                    job_uid=None,
                    component_uid=None,
                    last_reason="Authoritative health check did not return Status=Healthy.",
                )
            )
            return

        self._escalate(
            work,
            "EDR/AV remains non-Healthy after the single standing-safe repair attempt.",
        )

    def _complete(self, work: OperationalWork, stdout: str) -> None:
        summary = self._bounded_health_summary(stdout)
        note = (
            "Jason autonomous EDR/AV playbook completed. "
            f"Endpoint {work.hostname} returned authoritative Status=Healthy"
            + (" after one standing-safe repair attempt." if work.repair_attempts else ".")
            + f" Verification: {summary}"
        )
        self._write_note(work, note, "Jason - Autonomous EDR/AV Resolution")
        self.actions.execute(
            EDR_SCOPE,
            "service.ticket.update",
            {"payload": {"id": work.ticket_id, "status": "Complete"}},
        )
        self.store.put(
            self._replace(
                work,
                phase="complete",
                job_uid=None,
                component_uid=None,
                last_reason="Verified healthy and ticket completion readback succeeded.",
            )
        )

    def _escalate(self, work: OperationalWork, reason: str) -> None:
        if work.playbook_id == DNS_SCOPE.playbook_id:
            body = (
                "Jason autonomous DNS Agent diagnostic stopped for technician review. "
                f"{reason} No service restart, DNS/NIC change, reinstall, uninstall, "
                "registry change, generic PowerShell, or reboot was attempted."
            )
            title = "Jason - Autonomous DNS Agent Escalation"
        else:
            body = (
                "Jason autonomous EDR/AV playbook stopped for technician review. "
                f"{reason} No reboot, clean uninstall, generic PowerShell, or other "
                "user-disruptive action was attempted."
            )
            title = "Jason - Autonomous EDR/AV Escalation"
        self._write_note(work, body, title)
        self.store.put(
            self._replace(
                work,
                phase="escalated",
                job_uid=None,
                component_uid=None,
                last_reason=reason,
            )
        )

    def _block(self, work: OperationalWork, reason: str) -> None:
        try:
            self._write_note(
                work,
                "Jason autonomous work blocked safely. " + reason,
                "Jason - Autonomous Work Blocked",
            )
        finally:
            self.store.put(
                self._replace(
                    work,
                    phase="blocked",
                    job_uid=None,
                    component_uid=None,
                    last_reason=reason,
                )
            )

    def _record_admission_failure(
        self, candidate, scope: PlaybookScope, error: Exception
    ) -> None:
        # Offline is transient.  Do not claim or permanently suppress the ticket;
        # simply let the next reconciliation re-evaluate endpoint availability.
        if "endpoint is not currently online" in str(error).casefold():
            return
        ticket_id = int(candidate.resource_id)
        context = candidate.context
        ci_value = context.get("configurationItemID")
        try:
            ci_id = int(ci_value)
        except (TypeError, ValueError):
            ci_id = 0
        work = OperationalWork(
            ticket_id=ticket_id,
            ticket_number=str(context.get("ticketNumber") or ticket_id),
            title=str(context.get("title") or ""),
            playbook_id=scope.playbook_id,
            source_queue=str(candidate.source_queue),
            company_id=int(context.get("companyID") or 0),
            configuration_item_id=ci_id,
            device_uid="",
            hostname="",
            phase="blocked",
            last_reason=str(error)[:500],
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.put(work)

    def _write_note(self, work: OperationalWork, body: str, title: str) -> None:
        self.actions.execute(
            self._scope_for_work(work),
            "service.ticket.note.create",
            {
                "payload": {
                    "ticketID": int(work.ticket_id),
                    "title": title,
                    "description": body,
                    "noteType": 3,
                    "publish": 1,
                }
            },
        )

    def _read_data(self, capability: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        result = self.reads.execute(capability, arguments)
        if str(result.get("status") or "") != "succeeded":
            raise OperationalAutonomyError(
                "governed read failed: "
                + str(result.get("error_code") or result.get("reason_codes"))
            )
        evidence = result.get("evidence")
        if not isinstance(evidence, Mapping):
            raise OperationalAutonomyError("governed read returned no evidence mapping")
        data = evidence.get("data")
        return dict(data) if isinstance(data, Mapping) else dict(evidence)

    def _read_record(self, capability: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        data = self._read_data(capability, arguments)
        record = data.get("record")
        return dict(record) if isinstance(record, Mapping) else data

    @staticmethod
    def _action_data(output: Mapping[str, Any]) -> dict[str, Any]:
        data = output.get("data")
        return dict(data) if isinstance(data, Mapping) else dict(output)

    @staticmethod
    def _output_text(data: Mapping[str, Any]) -> str:
        outputs = data.get("outputs")
        if not isinstance(outputs, Sequence) or isinstance(outputs, (str, bytes)):
            return str(data.get("text") or "").strip()
        return "\n".join(
            str(item.get("text") or "")
            for item in outputs
            if isinstance(item, Mapping)
        ).strip()

    @staticmethod
    def _status_healthy(text: str) -> bool:
        for line in str(text).splitlines():
            normalized = line.strip().replace(" ", "").casefold()
            if normalized in {"status=healthy", "status:healthy"}:
                return True
        return False

    @staticmethod
    def _bounded_health_summary(text: str) -> str:
        selected = []
        for line in str(text).splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if any(
                token in stripped.casefold()
                for token in ("password", "secret", "token", "authorization")
            ):
                continue
            selected.append(stripped[:200])
            if len(selected) >= 6:
                break
        return " | ".join(selected)[:900] or "Status=Healthy"

    @staticmethod
    def _positive_int(value: Any, label: str) -> int:
        if isinstance(value, bool):
            raise OperationalAutonomyError(f"{label} must be a positive integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise OperationalAutonomyError(
                f"{label} must be a positive integer"
            ) from exc
        if parsed < 1:
            raise OperationalAutonomyError(f"{label} must be a positive integer")
        return parsed

    @staticmethod
    def _replace(work: OperationalWork, **changes: Any) -> OperationalWork:
        values = {
            "ticket_id": work.ticket_id,
            "ticket_number": work.ticket_number,
            "title": work.title,
            "playbook_id": work.playbook_id,
            "source_queue": work.source_queue,
            "company_id": work.company_id,
            "configuration_item_id": work.configuration_item_id,
            "device_uid": work.device_uid,
            "hostname": work.hostname,
            "phase": work.phase,
            "job_uid": work.job_uid,
            "component_uid": work.component_uid,
            "repair_attempts": work.repair_attempts,
            "last_reason": work.last_reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        values.update(changes)
        return OperationalWork(**values)
