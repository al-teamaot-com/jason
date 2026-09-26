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
import re
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
SECURITY_LOG_SCOPE = PlaybookScope(
    playbook_id="security_log_self_heal",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:security_log_self_heal",
    required_action_capabilities=REQUIRED_ACTION_CAPABILITIES,
)
POST_SCOPE = PlaybookScope(
    playbook_id="post_error_investigation",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:post_error_investigation",
    required_action_capabilities=(
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
UNEXPECTED_SHUTDOWN_SCOPE = PlaybookScope(
    playbook_id="unexpected_shutdown",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:unexpected_shutdown",
    required_action_capabilities=(
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
BACKUPIQ_SCOPE = PlaybookScope(
    playbook_id="backupiq_endpoint_backup",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:backupiq_endpoint_backup",
    required_action_capabilities=(
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
LOW_DISK_SCOPE = PlaybookScope(
    playbook_id="low_disk_space",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:low_disk_space",
    required_action_capabilities=(
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
VULSCAN_SCOPE = PlaybookScope(
    playbook_id="vulscan_missing_patch",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:vulscan_missing_patch",
    required_action_capabilities=(
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
DISK_BAD_BLOCK_SCOPE = PlaybookScope(
    playbook_id="disk_bad_block_event_7",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:disk_bad_block_event_7",
    required_action_capabilities=(
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
IDLE_LOG_OFF_SCOPE = PlaybookScope(
    playbook_id="idle_log_off",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:idle_log_off",
    required_action_capabilities=(
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
PLAYBOOK_SCOPES = {
    EDR_SCOPE.playbook_id: EDR_SCOPE,
    DNS_SCOPE.playbook_id: DNS_SCOPE,
    SECURITY_LOG_SCOPE.playbook_id: SECURITY_LOG_SCOPE,
    POST_SCOPE.playbook_id: POST_SCOPE,
    UNEXPECTED_SHUTDOWN_SCOPE.playbook_id: UNEXPECTED_SHUTDOWN_SCOPE,
    BACKUPIQ_SCOPE.playbook_id: BACKUPIQ_SCOPE,
    LOW_DISK_SCOPE.playbook_id: LOW_DISK_SCOPE,
    VULSCAN_SCOPE.playbook_id: VULSCAN_SCOPE,
    DISK_BAD_BLOCK_SCOPE.playbook_id: DISK_BAD_BLOCK_SCOPE,
    IDLE_LOG_OFF_SCOPE.playbook_id: IDLE_LOG_OFF_SCOPE,
}

HEALTH_COMPONENT_NAME = "Check Datto EDR/AV Status AOT Ver 12122025-1"
REPAIR_COMPONENT_NAME = "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024"
DNS_DIAGNOSTIC_COMPONENT_NAME = "DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026"
DNS_DIAGNOSTIC_COMPONENT_UID = "c3340a58-48d5-457b-bc30-5fd79e5ad8b1"
SECURITY_LOG_QUICK_TEST_NAME = "Security Log Quick Test [WIN] AOT Ver 12012025-1"
SECURITY_LOG_QUICK_TEST_UID = "a50d486b-2cce-4658-9e11-64fb6bf9ab9d"
SECURITY_LOG_SELF_HEAL_NAME = "Security Log Self-Heal [WIN] AOT Ver 11262025-2"
SECURITY_LOG_SELF_HEAL_UID = "cdd297b4-378f-4ffc-b272-56833e926c81"
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
        started = 0
        for candidate, scope in eligible:
            if started >= slots:
                break
            try:
                work = self._admit(candidate, scope)
            except Exception as exc:
                # Transient admission failures (notably an offline endpoint) do
                # not consume an active-work slot. Continue scanning so one or
                # two offline high-priority tickets cannot permanently starve
                # a lower-priority online eligible ticket.
                self._record_admission_failure(candidate, scope, exc)
                continue
            started += 1
            try:
                self._advance(work, candidate.context)
            except Exception as exc:
                self._block(
                    work,
                    f"Execution failed closed: {type(exc).__name__}: {str(exc)[:350]}",
                )

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

    @staticmethod
    def _is_security_log_ticket(ticket: Mapping[str, Any]) -> bool:
        title = str(ticket.get("title") or "").strip().casefold()
        return "security log unreadable" in title

    @staticmethod
    def _is_post_error_ticket(ticket: Mapping[str, Any]) -> bool:
        title = str(ticket.get("title") or "").strip().casefold()
        return (
            "power-on-self-test" in title
            or "post errors occurred" in title
        )

    @staticmethod
    def _is_unexpected_shutdown_ticket(ticket: Mapping[str, Any]) -> bool:
        title = str(ticket.get("title") or "").strip().casefold()
        return (
            "previous system shutdown" in title
            and "unexpected" in title
        )

    @staticmethod
    def _is_backupiq_ticket(ticket: Mapping[str, Any]) -> bool:
        title = str(ticket.get("title") or "").strip().casefold()
        return title.startswith("backupiq:") and "backup" in title

    @staticmethod
    def _is_low_disk_ticket(ticket: Mapping[str, Any]) -> bool:
        title = str(ticket.get("title") or "").strip().casefold()
        return (
            "low disk space" in title
            or "critical low disk space" in title
            or "hard disk full" in title
        )

    @staticmethod
    def _is_vulscan_ticket(ticket: Mapping[str, Any]) -> bool:
        title = str(ticket.get("title") or "").strip().casefold()
        return (
            "vulnerability detected by vulscan" in title
            or "missing critical security patch" in title
        )

    @staticmethod
    def _is_disk_bad_block_ticket(ticket: Mapping[str, Any]) -> bool:
        material = (
            str(ticket.get("title") or "") + " " + str(ticket.get("description") or "")
        ).casefold()
        return (
            "bad block" in material
            or "event id 7" in material
            or ("\\device\\harddisk" in material and "\\dr" in material)
        )

    @staticmethod
    def _is_idle_log_off_ticket(ticket: Mapping[str, Any]) -> bool:
        title = str(ticket.get("title") or "").strip().casefold()
        return (
            "get idle log off status" in title
            and ("compliant: false" in title or "enabled: false" in title)
        )

    def _match_scope(self, ticket: Mapping[str, Any]) -> PlaybookScope | None:
        if self._is_health_only_edr_ticket(ticket):
            return EDR_SCOPE
        if self._is_dns_agent_ticket(ticket):
            return DNS_SCOPE
        if self._is_security_log_ticket(ticket):
            return SECURITY_LOG_SCOPE
        if self._is_post_error_ticket(ticket):
            return POST_SCOPE
        if self._is_unexpected_shutdown_ticket(ticket):
            return UNEXPECTED_SHUTDOWN_SCOPE
        if self._is_backupiq_ticket(ticket):
            return BACKUPIQ_SCOPE
        if self._is_low_disk_ticket(ticket):
            return LOW_DISK_SCOPE
        if self._is_vulscan_ticket(ticket):
            return VULSCAN_SCOPE
        if self._is_disk_bad_block_ticket(ticket):
            return DISK_BAD_BLOCK_SCOPE
        if self._is_idle_log_off_ticket(ticket):
            return IDLE_LOG_OFF_SCOPE
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
        if (
            endpoint.get("online") is not True
            and scope.playbook_id not in {
                BACKUPIQ_SCOPE.playbook_id,
                VULSCAN_SCOPE.playbook_id,
            }
        ):
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
            if work.playbook_id == EDR_SCOPE.playbook_id:
                next_phase = "health_dispatch"
            elif work.playbook_id == DNS_SCOPE.playbook_id:
                next_phase = "dns_diagnostic_dispatch"
            elif work.playbook_id == SECURITY_LOG_SCOPE.playbook_id:
                next_phase = "security_quick_dispatch"
            elif work.playbook_id == POST_SCOPE.playbook_id:
                next_phase = "post_investigate"
            elif work.playbook_id == UNEXPECTED_SHUTDOWN_SCOPE.playbook_id:
                next_phase = "shutdown_investigate"
            elif work.playbook_id == BACKUPIQ_SCOPE.playbook_id:
                next_phase = "backupiq_investigate"
            elif work.playbook_id == LOW_DISK_SCOPE.playbook_id:
                next_phase = "low_disk_investigate"
            elif work.playbook_id == VULSCAN_SCOPE.playbook_id:
                next_phase = "vulscan_investigate"
            elif work.playbook_id == DISK_BAD_BLOCK_SCOPE.playbook_id:
                next_phase = "disk_bad_block_investigate"
            elif work.playbook_id == IDLE_LOG_OFF_SCOPE.playbook_id:
                next_phase = "idle_log_off_investigate"
            else:
                raise OperationalAutonomyError(
                    f"unsupported autonomous playbook: {work.playbook_id}"
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

        if work.playbook_id == POST_SCOPE.playbook_id:
            if work.phase == "post_investigate":
                self._investigate_post_error(work)
                return

        if work.playbook_id == UNEXPECTED_SHUTDOWN_SCOPE.playbook_id:
            if work.phase == "shutdown_investigate":
                self._investigate_unexpected_shutdown(work)
                return

        if work.playbook_id == BACKUPIQ_SCOPE.playbook_id:
            if work.phase == "backupiq_investigate":
                self._investigate_backupiq(work, ticket)
                return

        if work.playbook_id == LOW_DISK_SCOPE.playbook_id:
            if work.phase == "low_disk_investigate":
                self._investigate_low_disk(work)
                return

        if work.playbook_id == VULSCAN_SCOPE.playbook_id:
            if work.phase == "vulscan_investigate":
                self._investigate_vulscan(work, ticket)
                return

        if work.playbook_id == DISK_BAD_BLOCK_SCOPE.playbook_id:
            if work.phase == "disk_bad_block_investigate":
                self._investigate_disk_bad_block(work)
                return

        if work.playbook_id == IDLE_LOG_OFF_SCOPE.playbook_id:
            if work.phase == "idle_log_off_investigate":
                self._investigate_idle_log_off(work)
                return

        if work.playbook_id == SECURITY_LOG_SCOPE.playbook_id:
            if work.phase == "security_quick_dispatch":
                self._dispatch_component(
                    work,
                    SECURITY_LOG_QUICK_TEST_NAME,
                    "security_quick_wait",
                )
                return
            if work.phase == "security_repair_dispatch":
                self._dispatch_component(
                    work,
                    SECURITY_LOG_SELF_HEAL_NAME,
                    "security_repair_wait",
                )
                return
            if work.phase == "security_verify_dispatch":
                self._dispatch_component(
                    work,
                    SECURITY_LOG_QUICK_TEST_NAME,
                    "security_verify_wait",
                )
                return
            if work.phase in {
                "security_quick_wait",
                "security_repair_wait",
                "security_verify_wait",
            }:
                self._poll_security_log(work)
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
        elif component_name == SECURITY_LOG_QUICK_TEST_NAME:
            component_uid = SECURITY_LOG_QUICK_TEST_UID
            resolved_component_name = SECURITY_LOG_QUICK_TEST_NAME
            step = (
                "security_verify"
                if next_phase == "security_verify_wait"
                else "security_quick"
            )
        elif component_name == SECURITY_LOG_SELF_HEAL_NAME:
            component_uid = SECURITY_LOG_SELF_HEAL_UID
            resolved_component_name = SECURITY_LOG_SELF_HEAL_NAME
            step = "security_repair"
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
        repair_attempts = work.repair_attempts + (
            1 if step in {"repair", "security_repair"} else 0
        )
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

    def _investigate_idle_log_off(self, work: OperationalWork) -> None:
        endpoint = self._read_record(
            "endpoint.device.read", {"resource_id": work.device_uid}
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
        if endpoint_uid != work.device_uid or endpoint_hostname.casefold() != work.hostname.casefold():
            self._block(work, "Idle Log Off device identity changed during execution.")
            return

        role = endpoint.get("device_type")
        role_text = (
            json.dumps(role, sort_keys=True, default=str)
            if isinstance(role, (Mapping, list))
            else str(role or "")
        )
        role_material = (
            f"{role_text} {endpoint.get('operating_system') or endpoint.get('operatingSystem') or ''}"
        ).casefold()
        protected = any(
            token in role_material
            for token in ("server", "domain controller", "rds", "terminal server", "kiosk")
        )

        history = self._read_data(
            "endpoint.alert.history.search", {"resource_id": work.device_uid}
        )
        alerts = history.get("alerts")
        if not isinstance(alerts, list):
            alerts = []
        idle_alerts: list[Mapping[str, Any]] = []
        for alert in alerts:
            if not isinstance(alert, Mapping):
                continue
            material = json.dumps(alert, sort_keys=True, default=str).casefold()
            if "idle log off" in material or "compliant: false" in material or "enabled: false" in material:
                idle_alerts.append(alert)
        exact = next(
            (
                item for item in idle_alerts
                if str(item.get("ticketNumber") or "").strip() == work.ticket_number
            ),
            None,
        )
        if exact is None and idle_alerts:
            exact = max(idle_alerts, key=lambda item: int(item.get("timestamp") or 0))

        alert_material = (
            json.dumps(exact, sort_keys=True, default=str).casefold()
            if exact is not None
            else work.title.casefold()
        )
        plumbing_error = any(
            token in alert_material
            for token in (
                "invalid myfiledestination",
                "powershell",
                "runtime mismatch",
                "missing variable",
                "script exception",
            )
        )
        if protected:
            classification = "protected_or_exception_role"
            reason = "Idle Log Off diagnostic complete; protected/exception role requires human policy review."
        elif plumbing_error:
            classification = "monitor_execution_failure"
            reason = "Idle Log Off diagnostic identified monitor/plumbing failure; endpoint noncompliance is not proven."
        else:
            classification = "reported_noncompliance_policy_verification_required"
            reason = (
                "Idle Log Off diagnostic found a noncompliance signal; applicability and "
                "per-run setter approval remain required."
            )

        note = (
            "Jason autonomous Idle Log Off diagnostic completed using governed endpoint "
            "and alert-history evidence. "
            f"Device={work.hostname}; Online={'Yes' if endpoint.get('online') is True else 'No'}; "
            f"DeviceType={role_text[:180] or 'unknown'}; "
            f"ProtectedOrExceptionRole={'Yes' if protected else 'No'}; "
            f"MatchingIdleAlerts={len(idle_alerts)}; "
            f"Classification={classification}. "
            "The setter 'Set Idle Log Off AOT Ver 02042026-1' remains per-run approval "
            "only because it intentionally affects future user sessions and Component "
            "Control rejected standing-safe promotion. Jason did not run the setter, "
            "resolve an alert, force a logoff, change policy, run generic PowerShell, "
            "or perform any other modifying/user-disruptive action."
        )
        self._write_note(work, note, "Jason - Autonomous Idle Log Off Diagnostic")
        self.store.put(
            self._replace(work, phase="escalated", last_reason=reason)
        )

    def _investigate_disk_bad_block(self, work: OperationalWork) -> None:
        endpoint = self._read_record(
            "endpoint.device.read", {"resource_id": work.device_uid}
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
        if endpoint_uid != work.device_uid or endpoint_hostname.casefold() != work.hostname.casefold():
            self._block(work, "Disk Event ID 7 device identity changed during execution.")
            return
        if endpoint.get("online") is not True:
            self._block(work, "Disk Event ID 7 target went offline before evidence collection.")
            return

        history = self._read_data(
            "endpoint.alert.history.search", {"resource_id": work.device_uid}
        )
        alerts = history.get("alerts")
        if not isinstance(alerts, list):
            alerts = []
        bad_block_alerts: list[Mapping[str, Any]] = []
        for alert in alerts:
            if not isinstance(alert, Mapping):
                continue
            context = alert.get("alertContext")
            context_map = context if isinstance(context, Mapping) else {}
            code = str(context_map.get("code") or "").strip()
            description = str(context_map.get("description") or "")
            material = json.dumps(alert, sort_keys=True, default=str).casefold()
            if code == "7" or "bad block" in description.casefold() or "bad block" in material:
                bad_block_alerts.append(alert)

        exact = next(
            (
                item for item in bad_block_alerts
                if str(item.get("ticketNumber") or "").strip() == work.ticket_number
            ),
            None,
        )
        if exact is None and bad_block_alerts:
            exact = max(
                bad_block_alerts,
                key=lambda item: int(item.get("timestamp") or 0),
            )
        if exact is None:
            self._escalate(
                work,
                "No authoritative Event ID 7/bad-block alert was found in governed history.",
            )
            return

        context = exact.get("alertContext")
        context_map = context if isinstance(context, Mapping) else {}
        description = str(context_map.get("description") or "").strip()
        disk_match = re.search(
            r"\\Device\\Harddisk(\d+)\\DR(\d+)",
            description,
            flags=re.IGNORECASE,
        )
        harddisk = disk_match.group(1) if disk_match else "unknown"
        dr = disk_match.group(2) if disk_match else "unknown"

        audit = self._read_data("endpoint.audit.read", {"resource_id": work.device_uid})
        attached = audit.get("attachedDevices")
        logical = audit.get("logicalDisks")
        if attached is None and isinstance(audit.get("audit"), Mapping):
            attached = audit["audit"].get("attachedDevices")
            logical = audit["audit"].get("logicalDisks")
        attached = attached if isinstance(attached, list) else []
        logical = logical if isinstance(logical, list) else []
        removable_hints = 0
        for device in attached:
            if not isinstance(device, Mapping):
                continue
            material = json.dumps(device, sort_keys=True, default=str).casefold()
            if any(token in material for token in ("usb", "removable", "mass-storage", "sd card")):
                removable_hints += 1

        note = (
            "Jason autonomous Disk Event ID 7 diagnostic completed using governed "
            "read-only alert-history and endpoint-audit evidence. "
            f"Device={work.hostname}; AlertUid={str(exact.get('alertUid') or '')[:90] or 'unknown'}; "
            f"HarddiskX={harddisk}; DRX={dr}; "
            f"LogicalDiskCount={len(logical)}; AttachedDeviceCount={len(attached)}; "
            f"RemovableDeviceHints={removable_hints}. "
            "Current provider audit does not authoritatively map Windows HarddiskX/DRX "
            "to a physical disk model/serial/bus. The preferred comprehensive storage "
            "diagnostic remains standing-safe blocked by Component Control, so Jason did "
            "not guess whether the affected disk is internal or removable. No disk repair, "
            "CHKDSK repair, formatting, firmware/driver change, alert resolution, ticket "
            "completion, reboot, or other modifying action was attempted."
        )
        self._write_note(work, note, "Jason - Autonomous Disk Event ID 7 Diagnostic")
        self.store.put(
            self._replace(
                work,
                phase="escalated",
                last_reason=(
                    "Disk Event ID 7 diagnostic complete; authoritative physical-disk "
                    "mapping remains component/technician gated."
                ),
            )
        )

    def _investigate_vulscan(
        self,
        work: OperationalWork,
        ticket: Mapping[str, Any],
    ) -> None:
        endpoint = self._read_record(
            "endpoint.device.read", {"resource_id": work.device_uid}
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
        if endpoint_uid != work.device_uid or endpoint_hostname.casefold() != work.hostname.casefold():
            self._block(work, "VulScan device identity changed during execution.")
            return

        material = " ".join(
            str(ticket.get(key) or "")
            for key in ("title", "description", "resolution")
        )
        kbs = sorted(set(re.findall(r"KB\s*(\d{6,8})", material, flags=re.IGNORECASE)))
        if not kbs:
            self._escalate(
                work,
                "No exact KB identity could be extracted from the VulScan ticket.",
            )
            return

        rows: list[tuple[str, str, bool]] = []
        for kb_digits in kbs:
            kb = f"KB{kb_digits}"
            patch_data = self._read_data(
                "endpoint.patch.search",
                {"resource_id": work.device_uid, "kb": kb},
            )
            items = patch_data.get("items")
            if items is None:
                items = patch_data.get("patches")
            if not isinstance(items, Sequence) or isinstance(items, (str, bytes)) or len(items) != 1:
                rows.append((kb, "AMBIGUOUS_OR_MISSING", False))
                continue
            item = items[0]
            if not isinstance(item, Mapping):
                rows.append((kb, "AMBIGUOUS_OR_MISSING", False))
                continue
            status = str(item.get("installStatus") or "").strip().upper() or "UNKNOWN"
            rows.append((kb, status, bool(item.get("rebootRequired"))))

        statuses = {status for _, status, _ in rows}
        if "NOT_APPROVED" in statuses:
            classification = "approval_blocked"
        elif statuses & {"INSTALL_ERROR", "FAILED", "ERROR"}:
            classification = "install_failure"
        elif "APPROVED_PENDING" in statuses or "PENDING" in statuses:
            classification = "approved_pending"
        elif statuses and statuses <= {"INSTALLED"}:
            classification = "stale_or_recovered_finding"
        elif "AMBIGUOUS_OR_MISSING" in statuses:
            classification = "patch_identity_or_supersedence_review"
        else:
            classification = "patch_state_review"

        patch_summary = "; ".join(
            f"{kb}={status}{'/RebootRequired' if reboot else ''}"
            for kb, status, reboot in rows
        )
        online = endpoint.get("online") is True
        note = (
            "Jason autonomous VulScan diagnostic completed using governed endpoint and "
            "exact patch-inventory reads. "
            f"Device={work.hostname}; Online={'Yes' if online else 'No'}; "
            f"EndpointRebootRequired={'Yes' if bool(endpoint.get('reboot_required')) else 'No'}; "
            f"PatchStates={patch_summary}; Classification={classification}. "
            "No patch approval, forced installation, Windows Update repair, WSUS-policy "
            "change, reboot scheduling, reboot, or other modifying action was attempted. "
        )
        if classification == "approval_blocked":
            note += (
                "At least one reported KB is currently NOT_APPROVED; the playbook will "
                "not approve patches autonomously."
            )
            reason = "VulScan diagnostic complete; one or more exact KBs are not approved."
        elif classification == "stale_or_recovered_finding":
            note += (
                "All exact reported KBs are installed. Automatic ticket completion remains "
                "gated until stale/recovered VulScan closure is separately accepted."
            )
            reason = "VulScan diagnostic complete; reported KBs appear installed, closure gated."
        elif classification == "approved_pending":
            note += (
                "At least one exact KB is approved/pending. Patch-window timing and any "
                "reboot action remain separately gated."
            )
            reason = "VulScan diagnostic complete; approved-pending patch requires window/recheck logic."
        else:
            note += (
                "Technician review or a separately accepted Windows Update remediation branch "
                "is required before modifying the endpoint."
            )
            reason = f"VulScan diagnostic classified {classification}; remediation remains gated."

        self._write_note(work, note, "Jason - Autonomous VulScan Diagnostic")
        self.store.put(
            self._replace(
                work,
                phase="escalated",
                last_reason=reason,
            )
        )

    def _investigate_low_disk(self, work: OperationalWork) -> None:
        endpoint = self._read_record(
            "endpoint.device.read", {"resource_id": work.device_uid}
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
        if endpoint_uid != work.device_uid or endpoint_hostname.casefold() != work.hostname.casefold():
            self._block(work, "Low-disk device identity changed during execution.")
            return
        if endpoint.get("online") is not True:
            self._block(work, "Low-disk target went offline before evidence collection.")
            return

        audit = self._read_data(
            "endpoint.audit.read", {"resource_id": work.device_uid}
        )
        logical_disks = audit.get("logicalDisks")
        if logical_disks is None and isinstance(audit.get("audit"), Mapping):
            logical_disks = audit["audit"].get("logicalDisks")
        if not isinstance(logical_disks, list) or not logical_disks:
            self._block(work, "Low-disk endpoint audit contained no logical-disk evidence.")
            return

        fixed = [
            disk for disk in logical_disks
            if isinstance(disk, Mapping)
            and str(disk.get("description") or "").casefold() == "local fixed disk"
        ]
        candidates = fixed or [disk for disk in logical_disks if isinstance(disk, Mapping)]
        disk = min(
            candidates,
            key=lambda item: (
                (float(item.get("freespace") or 0) / float(item.get("size") or 1))
                if float(item.get("size") or 0) > 0 else 1.0
            ),
        )
        size = float(disk.get("size") or 0)
        free = float(disk.get("freespace") or 0)
        free_pct = (free / size * 100.0) if size > 0 else 0.0
        drive = str(disk.get("diskIdentifier") or "unknown")

        role = endpoint.get("device_type")
        role_text = (
            json.dumps(role, sort_keys=True, default=str)
            if isinstance(role, (Mapping, list))
            else str(role or "")
        )
        role_material = (
            f"{role_text} {endpoint.get('operating_system') or endpoint.get('operatingSystem') or ''}"
        ).casefold()
        protected = any(
            token in role_material
            for token in (
                "server",
                "domain controller",
                "hyper-v",
                "hyperv",
                "database",
                "backup repository",
            )
        )

        alerts_data = self._read_data(
            "endpoint.alert.history.search", {"resource_id": work.device_uid}
        )
        alerts = alerts_data.get("alerts")
        if not isinstance(alerts, list):
            alerts = []
        storage_risk_hits = 0
        for alert in alerts:
            if not isinstance(alert, Mapping):
                continue
            material = json.dumps(alert, sort_keys=True, default=str).casefold()
            if any(
                token in material
                for token in (
                    '"code":"7"',
                    '"code": "7"',
                    "bad block",
                    "ntfs",
                    "storport",
                    "storage controller",
                    "smart error",
                )
            ):
                storage_risk_hits += 1

        note = (
            "Jason autonomous low-disk diagnostic completed using governed read-only "
            "endpoint audit and alert-history evidence. "
            f"Device={work.hostname}; Drive={drive}; "
            f"SizeGB={size / (1024**3):.2f}; FreeGB={free / (1024**3):.2f}; "
            f"FreePercent={free_pct:.2f}; DeviceType={role_text[:180] or 'unknown'}; "
            f"ProtectedRole={'Yes' if protected else 'No'}; "
            f"StorageRiskEvidenceCount={storage_risk_hits}; "
            f"RebootRequired={'Yes' if bool(endpoint.get('reboot_required')) else 'No'}. "
            "No files were deleted, no cleanup component was run, and no service, "
            "process, BitLocker, reboot, or other user-disruptive change was attempted. "
        )
        if protected:
            reason = "Low-disk diagnostic complete; protected/server role requires human review."
            note += "Server/protected-role cleanup is intentionally not autonomous."
        elif storage_risk_hits:
            reason = "Low-disk diagnostic complete; storage-health evidence requires technician review."
            note += "Storage-health evidence takes priority over space cleanup."
        else:
            reason = (
                "Low-disk diagnostic complete; exact safe-cleanup target and cleanup "
                "authority remain separately gated."
            )
            note += (
                "Workstation diagnostics are complete, but cleanup remains gated until an "
                "exact standing-safe target/action is positively identified."
            )

        self._write_note(work, note, "Jason - Autonomous Low Disk Diagnostic")
        self.store.put(
            self._replace(
                work,
                phase="escalated",
                last_reason=reason,
            )
        )

    @staticmethod
    def _parse_iso_timestamp(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _investigate_backupiq(
        self,
        work: OperationalWork,
        ticket: Mapping[str, Any],
    ) -> None:
        endpoint = self._read_record(
            "endpoint.device.read", {"resource_id": work.device_uid}
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
        if endpoint_uid != work.device_uid or endpoint_hostname.casefold() != work.hostname.casefold():
            self._block(work, "BackupIQ device identity changed during execution.")
            return

        asset_data = self._read_data(
            "backup.endpoint.asset.search",
            {
                "company_id": work.company_id,
                "name": work.hostname,
                "page_size": 100,
            },
        )
        items = asset_data.get("items")
        if not isinstance(items, list):
            self._block(work, "BackupIQ provider asset evidence is unavailable or malformed.")
            return
        exact_assets = [
            item for item in items
            if isinstance(item, Mapping)
            and str(item.get("name") or "").strip().casefold() == work.hostname.casefold()
        ]
        if len(exact_assets) != 1:
            classification = (
                "asset_identity_or_lifecycle_issue"
                if len(exact_assets) == 0
                else "duplicate_or_ambiguous_provider_asset"
            )
            self._write_note(
                work,
                (
                    "Jason autonomous BackupIQ diagnostic stopped before remediation. "
                    f"Device={work.hostname}; ExactProviderAssetMatches={len(exact_assets)}; "
                    f"Classification={classification}. Exact DRMM/provider asset identity "
                    "was not uniquely proven. No reinstall, clean install, policy change, "
                    "backup deletion, retention change, or other modifying backup action "
                    "was attempted."
                ),
                "Jason - Autonomous BackupIQ Asset Validation",
            )
            self.store.put(
                self._replace(
                    work,
                    phase="escalated",
                    last_reason=(
                        "BackupIQ provider asset identity was not uniquely established; "
                        "technician review required."
                    ),
                )
            )
            return

        asset = exact_assets[0]
        provider_status = str(asset.get("status") or "").strip().casefold()
        backup_enabled = asset.get("backupEnabled") is True
        last_success = self._parse_iso_timestamp(
            asset.get("lastSuccessfulBackupTimestamp")
        )
        last_online = self._parse_iso_timestamp(asset.get("lastOnlineTimestamp"))
        ticket_created = self._parse_iso_timestamp(ticket.get("createDate"))
        endpoint_online = endpoint.get("online") is True

        alert_data = self._read_data(
            "backup.backupiq.alert.search",
            {
                "company_id": work.company_id,
                "asset_name": work.hostname,
                "page_size": 100,
            },
        )
        alert_items = alert_data.get("items")
        if not isinstance(alert_items, list):
            self._block(work, "BackupIQ alert evidence is unavailable or malformed.")
            return

        recovered_after_ticket = (
            last_success is not None
            and ticket_created is not None
            and last_success >= ticket_created
        )
        if not backup_enabled:
            classification = "backup_configuration_issue"
        elif not endpoint_online and provider_status != "online":
            classification = "inactive_or_offline_device"
        elif endpoint_online and provider_status != "online":
            classification = "backup_agent_connectivity_failure"
        elif recovered_after_ticket:
            classification = "stale_or_recovered_alert"
        elif endpoint_online and provider_status == "online":
            classification = "backup_failure_or_stale_success"
        else:
            classification = "provider_endpoint_state_conflict"

        note = (
            "Jason autonomous BackupIQ diagnostic completed using governed DRMM and "
            "Backup.net/UniView read evidence. "
            f"Device={work.hostname}; DRMMOnline={'Yes' if endpoint_online else 'No'}; "
            f"ProviderAssetId={str(asset.get('id') or '')[:80] or 'unknown'}; "
            f"ProviderStatus={provider_status or 'unknown'}; "
            f"BackupEnabled={'Yes' if backup_enabled else 'No'}; "
            f"LastSuccessfulBackup={last_success.isoformat() if last_success else 'unknown'}; "
            f"LastProviderOnline={last_online.isoformat() if last_online else 'unknown'}; "
            f"CurrentBackupIQAlerts={len(alert_items)}; "
            f"Classification={classification}. "
            "No reinstall, clean install, token/encryption retrieval, policy change, "
            "backup deletion, retention change, restore, or other modifying backup "
            "action was attempted. "
        )
        if classification == "stale_or_recovered_alert":
            note += (
                "Provider evidence shows a successful backup at or after ticket creation. "
                "Automatic completion remains gated until the recovered-alert closure "
                "branch has completed live acceptance."
            )
            reason = (
                "BackupIQ diagnostic complete; recovered-alert closure branch not yet promoted."
            )
        elif classification == "inactive_or_offline_device":
            note += (
                "Both management/provider evidence indicate an offline/inactive condition; "
                "the playbook correctly did not reinstall while the endpoint is offline."
            )
            reason = (
                "BackupIQ diagnostic classified an inactive/offline endpoint; waiting/recheck "
                "automation remains separately gated."
            )
        else:
            note += (
                "Technician review or a separately accepted remediation branch is required "
                "before any modifying backup action."
            )
            reason = (
                f"BackupIQ diagnostic classified {classification}; remediation remains gated."
            )

        self._write_note(work, note, "Jason - Autonomous BackupIQ Diagnostic")
        self.store.put(
            self._replace(
                work,
                phase="escalated",
                last_reason=reason,
            )
        )

    @staticmethod
    def _unexpected_shutdown_alert(alert: Mapping[str, Any]) -> bool:
        context = alert.get("alertContext")
        if isinstance(context, Mapping):
            code = str(context.get("code") or "").strip()
            description = str(context.get("description") or "").casefold()
            if code == "6008" or (
                "previous system shutdown" in description
                and "unexpected" in description
            ):
                return True
        material = json.dumps(alert, sort_keys=True, default=str).casefold()
        return (
            "previous system shutdown" in material
            and "unexpected" in material
        )

    @staticmethod
    def _alert_timestamp_ms(alert: Mapping[str, Any]) -> int | None:
        value = alert.get("timestamp")
        if isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _physical_device(endpoint: Mapping[str, Any]) -> bool | None:
        device_type = endpoint.get("device_type")
        material = (
            json.dumps(device_type, sort_keys=True, default=str)
            if isinstance(device_type, (Mapping, list))
            else str(device_type or "")
        ).casefold()
        if any(token in material for token in ("virtual machine", "vmware", "virtualbox", "xen")):
            return False
        if any(
            token in material
            for token in (
                "main system chassis",
                "desktop",
                "laptop",
                "notebook",
                "workstation",
                "server",
            )
        ):
            return True
        return None

    def _investigate_unexpected_shutdown(self, work: OperationalWork) -> None:
        endpoint = self._read_record(
            "endpoint.device.read", {"resource_id": work.device_uid}
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
        if endpoint_uid != work.device_uid or endpoint_hostname.casefold() != work.hostname.casefold():
            self._block(work, "Unexpected-shutdown device identity changed during execution.")
            return
        if endpoint.get("online") is not True:
            self._block(work, "Unexpected-shutdown target went offline before evidence collection.")
            return

        history = self._read_data(
            "endpoint.alert.history.search",
            {"resource_id": work.device_uid},
        )
        alerts = history.get("alerts")
        if not isinstance(alerts, list):
            self._block(work, "Unexpected-shutdown alert history is unavailable or malformed.")
            return
        shutdown_alerts = [
            item for item in alerts
            if isinstance(item, Mapping) and self._unexpected_shutdown_alert(item)
        ]
        incident = next(
            (
                item for item in shutdown_alerts
                if str(item.get("ticketNumber") or "").strip() == work.ticket_number
            ),
            None,
        )
        if incident is None and shutdown_alerts:
            incident = max(
                shutdown_alerts,
                key=lambda item: self._alert_timestamp_ms(item) or 0,
            )
        incident_ms = self._alert_timestamp_ms(incident) if incident is not None else None
        if incident_ms is None:
            self._escalate(
                work,
                "Exact shutdown incident timestamp could not be recovered from governed alert history.",
            )
            return

        thirty_days_ms = 30 * 24 * 60 * 60 * 1000
        recurrence = [
            item for item in shutdown_alerts
            if (
                (ts := self._alert_timestamp_ms(item)) is not None
                and incident_ms - thirty_days_ms <= ts <= incident_ms + 5 * 60 * 1000
            )
        ]

        site = str(endpoint.get("site") or "").strip()
        physical_hits: set[str] = set()
        ambiguous_peers = 0
        checked_peers = 0
        if self._physical_device(endpoint) is True:
            physical_hits.add(work.device_uid)
        if site:
            site_data = self._read_data("endpoint.device.search", {"site": site})
            matches = site_data.get("resource_matches")
            if isinstance(matches, list):
                for match in matches[:50]:
                    if not isinstance(match, Mapping):
                        continue
                    uid = str(match.get("resource_id") or "").strip()
                    if not uid or uid == work.device_uid:
                        continue
                    peer = self._read_record("endpoint.device.read", {"resource_id": uid})
                    physical = self._physical_device(peer)
                    if physical is None:
                        ambiguous_peers += 1
                        continue
                    if physical is False:
                        continue
                    checked_peers += 1
                    peer_history = self._read_data(
                        "endpoint.alert.history.search", {"resource_id": uid}
                    )
                    peer_alerts = peer_history.get("alerts")
                    if not isinstance(peer_alerts, list):
                        continue
                    if any(
                        isinstance(item, Mapping)
                        and self._unexpected_shutdown_alert(item)
                        and (ts := self._alert_timestamp_ms(item)) is not None
                        and abs(ts - incident_ms) <= 15 * 60 * 1000
                        for item in peer_alerts
                    ):
                        physical_hits.add(uid)

        recurring = len(recurrence) >= 2
        site_wide = len(physical_hits) >= 2
        role = endpoint.get("device_type")
        role_text = (
            json.dumps(role, sort_keys=True, default=str)
            if isinstance(role, (Mapping, list))
            else str(role or "")
        )
        note = (
            "Jason autonomous unexpected-shutdown diagnostic completed using governed "
            "read-only endpoint and alert-history evidence. "
            f"Device={work.hostname}; Site={site or 'unknown'}; "
            f"IncidentTimestampMs={incident_ms}; "
            f"ShutdownEvents30d={len(recurrence)}; Recurring={'Yes' if recurring else 'No'}; "
            f"PhysicalDevicesInPlusMinus15Min={len(physical_hits)}; "
            f"PossibleSiteWideEvent={'Yes' if site_wide else 'No'}; "
            f"PhysicalPeersChecked={checked_peers}; AmbiguousPhysicalPeers={ambiguous_peers}; "
            f"DeviceType={role_text[:180] or 'unknown'}; "
            f"RebootRequired={'Yes' if bool(endpoint.get('reboot_required')) else 'No'}. "
            "VM/virtual devices are excluded from the physical-device threshold when "
            "provider classification identifies them as virtual. No reboot, shutdown, "
            "firmware, storage repair, service change, or PowerShell action was attempted. "
        )
        if recurring or site_wide or ambiguous_peers:
            note += (
                "Technician review is required because recurrence, site-wide correlation, "
                "or ambiguous physical-device classification remains material."
            )
            reason = (
                "Unexpected-shutdown diagnostic complete; recurrence/site-correlation "
                "requires technician review."
            )
        else:
            note += (
                "No recurrence or multi-physical-device site threshold was proven. "
                "Automatic closure remains gated until isolated-event live acceptance is complete."
            )
            reason = (
                "Unexpected-shutdown diagnostic complete; isolated closure branch not yet promoted."
            )
        self._write_note(work, note, "Jason - Autonomous Unexpected Shutdown Diagnostic")
        self.store.put(
            self._replace(
                work,
                phase="escalated",
                last_reason=reason,
            )
        )

    def _investigate_post_error(self, work: OperationalWork) -> None:
        endpoint = self._read_record(
            "endpoint.device.read", {"resource_id": work.device_uid}
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
        if endpoint_uid != work.device_uid or endpoint_hostname.casefold() != work.hostname.casefold():
            self._block(work, "POST investigation device identity changed during execution.")
            return
        if endpoint.get("online") is not True:
            self._block(work, "POST investigation target went offline before evidence collection.")
            return

        history = self._read_data(
            "endpoint.alert.history.search",
            {"resource_id": work.device_uid},
        )
        alerts = history.get("alerts")
        if alerts is None and isinstance(history.get("data"), Mapping):
            alerts = history["data"].get("alerts")
        if not isinstance(alerts, list):
            self._block(work, "POST alert history evidence is unavailable or malformed.")
            return

        post_alerts: list[Mapping[str, Any]] = []
        unique_tickets: set[str] = set()
        for alert in alerts:
            if not isinstance(alert, Mapping):
                continue
            material = json.dumps(alert, sort_keys=True, default=str).casefold()
            if "power-on-self-test" not in material and "post errors occurred" not in material:
                continue
            post_alerts.append(alert)
            ticket_number = str(alert.get("ticketNumber") or "").strip()
            if ticket_number:
                unique_tickets.add(ticket_number)

        operating_system = str(
            endpoint.get("operating_system")
            or endpoint.get("operatingSystem")
            or ""
        ).strip()
        device_type = endpoint.get("device_type")
        device_type_text = (
            json.dumps(device_type, sort_keys=True, default=str)
            if isinstance(device_type, (Mapping, list))
            else str(device_type or "")
        )
        role_material = f"{operating_system} {device_type_text} {work.title}".casefold()
        protected_role = any(
            token in role_material
            for token in ("server", "hyper-v", "hyperv", "domain controller", "physical host")
        )
        recurring = len(unique_tickets) >= 2 or len(post_alerts) >= 2
        reboot_required = bool(endpoint.get("reboot_required"))

        note = (
            "Jason autonomous POST diagnostic completed using read-only provider evidence. "
            f"Device={work.hostname}; Online=True; OS={operating_system or 'unknown'}; "
            f"ProtectedRole={'Yes' if protected_role else 'No'}; "
            f"HistoricalPOSTAlerts={len(post_alerts)}; "
            f"HistoricalPOSTTickets={len(unique_tickets)}; "
            f"Recurring={'Yes' if recurring else 'No'}; "
            f"RebootRequired={'Yes' if reboot_required else 'No'}. "
            "No reboot, firmware change, hardware mutation, service change, or generic "
            "PowerShell was attempted. "
        )
        if protected_role:
            note += (
                "Protected server/hypervisor evidence requires technician review; "
                "automatic remediation and closure are not authorized."
            )
        elif recurring:
            note += (
                "Recurring POST evidence requires technician review; automatic closure "
                "is not authorized."
            )
        else:
            note += (
                "The baseline autonomous branch is diagnostic-only; closure remains "
                "gated until isolated-workstation acceptance is separately proven."
            )

        self._write_note(work, note, "Jason - Autonomous POST Diagnostic")
        self.store.put(
            self._replace(
                work,
                phase="escalated",
                last_reason=(
                    "POST diagnostic complete; protected/recurring/closure branch "
                    "requires technician review."
                    if protected_role or recurring
                    else "POST diagnostic complete; isolated closure branch not yet promoted."
                ),
            )
        )

    def _poll_security_log(self, work: OperationalWork) -> None:
        if not work.job_uid or not work.component_uid:
            self._block(work, "Persisted Security Log job identity is incomplete.")
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
                "Security Log job state became stale or unknown; no redispatch allowed.",
            )
            return
        if status not in {"completed", "complete", "success", "succeeded", "finished"}:
            self._escalate(
                work,
                f"Security Log job ended with provider status {status or 'unknown'}.",
            )
            return

        if work.phase == "security_repair_wait":
            self.store.put(
                self._replace(
                    work,
                    phase="security_verify_dispatch",
                    job_uid=None,
                    component_uid=None,
                    last_reason=(
                        "Security Log Self-Heal completed; independent Quick Test "
                        "verification is required."
                    ),
                )
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
            self._block(work, "Security Log Quick Test produced no readable stdout.")
            return

        if self._status_healthy(text):
            summary = self._bounded_health_summary(text)
            body = (
                "Jason autonomous Security Log playbook verified the endpoint "
                f"Security Log healthy on {work.hostname}. "
                + (
                    "One standing-safe Security Log Self-Heal attempt was used. "
                    if work.repair_attempts
                    else "No repair was required. "
                )
                + f"Verification: {summary}. "
                "Alert/SOC side-effect correlation and cleanup remain a separately "
                "gated completion branch; no unrelated security alert or ticket was "
                "closed automatically."
            )
            self._write_note(work, body, "Jason - Autonomous Security Log Verification")
            self.store.put(
                self._replace(
                    work,
                    phase="escalated",
                    job_uid=None,
                    component_uid=None,
                    last_reason=(
                        "Security Log verified healthy; exact alert and process-generated "
                        "security-ticket cleanup remains separately gated."
                    ),
                )
            )
            return

        if work.phase == "security_quick_wait" and work.repair_attempts == 0:
            self.store.put(
                self._replace(
                    work,
                    phase="security_repair_dispatch",
                    job_uid=None,
                    component_uid=None,
                    last_reason=(
                        "Security Log Quick Test confirmed unhealthy; one standing-safe "
                        "Self-Heal attempt is permitted."
                    ),
                )
            )
            return

        self._escalate(
            work,
            "Security Log remains unhealthy after the single standing-safe Self-Heal attempt.",
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
        if work.playbook_id == IDLE_LOG_OFF_SCOPE.playbook_id:
            body = (
                "Jason autonomous Idle Log Off diagnostic stopped for technician review. "
                f"{reason} The setter was not run and no alert resolution, forced logoff, "
                "policy change, generic PowerShell, reboot, or other modifying action was attempted."
            )
            title = "Jason - Autonomous Idle Log Off Escalation"
        elif work.playbook_id == DISK_BAD_BLOCK_SCOPE.playbook_id:
            body = (
                "Jason autonomous Disk Event ID 7 diagnostic stopped for technician review. "
                f"{reason} No disk repair, CHKDSK repair, formatting, firmware/driver "
                "change, alert resolution, ticket completion, reboot, or other modifying "
                "action was attempted."
            )
            title = "Jason - Autonomous Disk Event ID 7 Escalation"
        elif work.playbook_id == VULSCAN_SCOPE.playbook_id:
            body = (
                "Jason autonomous VulScan diagnostic stopped for technician review. "
                f"{reason} No patch approval, forced install, Windows Update repair, "
                "WSUS-policy change, reboot scheduling, reboot, or other modifying action "
                "was attempted."
            )
            title = "Jason - Autonomous VulScan Escalation"
        elif work.playbook_id == LOW_DISK_SCOPE.playbook_id:
            body = (
                "Jason autonomous low-disk diagnostic stopped for technician review. "
                f"{reason} No file deletion, cleanup component, BitLocker change, reboot, "
                "service change, or other user-disruptive action was attempted."
            )
            title = "Jason - Autonomous Low Disk Escalation"
        elif work.playbook_id == BACKUPIQ_SCOPE.playbook_id:
            body = (
                "Jason autonomous BackupIQ diagnostic stopped for technician review. "
                f"{reason} No reinstall, clean install, backup deletion, retention/policy "
                "change, restore, credential disclosure, or other modifying backup action "
                "was attempted."
            )
            title = "Jason - Autonomous BackupIQ Escalation"
        elif work.playbook_id == UNEXPECTED_SHUTDOWN_SCOPE.playbook_id:
            body = (
                "Jason autonomous unexpected-shutdown diagnostic stopped for technician review. "
                f"{reason} No reboot, shutdown, firmware change, storage repair, service "
                "change, or PowerShell action was attempted."
            )
            title = "Jason - Autonomous Unexpected Shutdown Escalation"
        elif work.playbook_id == POST_SCOPE.playbook_id:
            body = (
                "Jason autonomous POST diagnostic stopped for technician review. "
                f"{reason} No reboot, firmware change, hardware mutation, service "
                "change, or generic PowerShell was attempted."
            )
            title = "Jason - Autonomous POST Diagnostic Escalation"
        elif work.playbook_id == SECURITY_LOG_SCOPE.playbook_id:
            body = (
                "Jason autonomous Security Log playbook stopped for technician review. "
                f"{reason} No reboot, generic PowerShell, or unrelated endpoint/security "
                "action was attempted."
            )
            title = "Jason - Autonomous Security Log Escalation"
        elif work.playbook_id == DNS_SCOPE.playbook_id:
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
