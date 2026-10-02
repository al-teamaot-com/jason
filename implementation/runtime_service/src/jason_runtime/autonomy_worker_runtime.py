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

import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

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
from autonomous_remediation.deb_availability import (
    DebAssetSelection,
    DebAvailabilityState,
    select_deb_asset,
)

from .low_disk_analysis import (
    LARGE_FILE_COMMAND,
    LOW_DISK_GRACE_SECONDS,
    PHYSICAL_DISK_COMMAND,
    RELIABILITY_COMMAND,
    SOFTWARE_DISTRIBUTION_COMMAND,
    SYSMON_COMMAND,
    SYSMON_DEPENDENCY_COMMAND,
    SYSTEM_FILE_COMMAND,
    TOP_FOLDER_COMMAND,
    VSS_COMMAND,
    artifact_bytes,
    choose_cleanup,
    numeric,
    parse_json_records,
    recommendation,
    relevant_findings,
    storage_health_summary,
)
from .unexpected_shutdown_analysis import (
    INCIDENT_WINDOW_MS,
    PHYSICAL_DISK_COMMAND as SHUTDOWN_PHYSICAL_DISK_COMMAND,
    RELIABILITY_COMMAND as SHUTDOWN_RELIABILITY_COMMAND,
    SHUTDOWN_EVENT_COMMAND,
    VOLUME_HEALTH_COMMAND,
    WHEA_EVENT_COMMAND,
    classify_site_scope,
    protected_role as shutdown_protected_role,
    shutdown_character,
    site_event_id,
    storage_health_risk as shutdown_storage_health_risk,
)
from .approved_client_messages import resolve_approved_client_message
from .technical_notes import TechnicalNote, canonical_title, legacy_technical_note, render_technical_note
from autonomous_remediation.offline_ticket_augmentation import (
    SiteContextEvidence,
    SiteWitness,
    classify_site_context,
    is_offline_ticket,
    render_site_context_note,
)
from .vulscan_client_policy import resolve_vulscan_policy


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
    playbook_version="1.1.0",
    policy_id="playbook-autonomy:unexpected_shutdown",
    required_action_capabilities=(
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
BACKUPIQ_SCOPE = PlaybookScope(
    playbook_id="backupiq_endpoint_backup",
    playbook_version="1.2.0",
    policy_id="playbook-autonomy:backupiq_endpoint_backup",
    required_action_capabilities=(
        "automation.component.execute",
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
LOW_DISK_SCOPE = PlaybookScope(
    playbook_id="low_disk_space",
    playbook_version="1.1.0",
    policy_id="playbook-autonomy:low_disk_space",
    required_action_capabilities=(
        "automation.component.execute",
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
# Preserve the exact previously owner-promoted diagnostic/classification scope.
# The v1.1 client-disposition branch is separately promotion-bound so adding
# client communication cannot disable safe core VulScan work.
VULSCAN_SCOPE = PlaybookScope(
    playbook_id="vulscan_missing_patch",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:vulscan_missing_patch",
    required_action_capabilities=(
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
VULSCAN_CLIENT_DISPOSITION_SCOPE = PlaybookScope(
    playbook_id="vulscan_missing_patch",
    playbook_version="1.1.0",
    policy_id="playbook-autonomy:vulscan_missing_patch",
    required_action_capabilities=(
        "service.ticket.note.create",
        "service.ticket.update",
        "service.ticket.client.notification.create",
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
    playbook_version="1.1.0",
    policy_id="playbook-autonomy:idle_log_off",
    required_action_capabilities=(
        "automation.component.execute",
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)
OFFLINE_AUGMENTATION_SCOPE = PlaybookScope(
    playbook_id="offline_ticket_context_augmentation",
    playbook_version="0.1.0",
    policy_id="playbook-autonomy:offline_ticket_context_augmentation",
    required_action_capabilities=(
        "service.ticket.note.create",
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
    OFFLINE_AUGMENTATION_SCOPE.playbook_id: OFFLINE_AUGMENTATION_SCOPE,
}

HEALTH_COMPONENT_NAME = "Check Datto EDR/AV Status AOT Ver 12122025-1"
REPAIR_COMPONENT_NAME = "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024"
DNS_DIAGNOSTIC_COMPONENT_NAME = "DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026"
DNS_DIAGNOSTIC_COMPONENT_UID = "c3340a58-48d5-457b-bc30-5fd79e5ad8b1"
IDLE_LOG_OFF_SETTER_NAME = "Set Idle Log Off AOT Ver 02042026-1"
IDLE_LOG_OFF_SETTER_UID = "acc6a240-881d-4655-9470-87f60c8e35e8"
SECURITY_LOG_QUICK_TEST_NAME = "Security Log Quick Test [WIN] AOT Ver 12012025-1"
SECURITY_LOG_QUICK_TEST_UID = "a50d486b-2cce-4658-9e11-64fb6bf9ab9d"
SECURITY_LOG_SELF_HEAL_NAME = "Security Log Self-Heal [WIN] AOT Ver 11262025-2"
SECURITY_LOG_SELF_HEAL_UID = "cdd297b4-378f-4ffc-b272-56833e926c81"
BACKUPIQ_INSTALLER_NAME = "Datto Endpoint Backup Agent v2 [WIN]"
BACKUPIQ_INSTALLER_UID = "f39412b2-bfdc-4ac6-b4be-f2fa8bc5f967"
BACKUPIQ_REINSTALL_VERIFY_SECONDS = 3 * 60 * 60
LOW_DISK_SYSMON_CLEANUP_NAME = "Sysmon - Clear C:\\Sysmon Folder - AOT"
LOW_DISK_SYSMON_CLEANUP_UID = "97ddcdd5-2b74-4a4b-9516-cc872af6a7b6"
TERMINAL_PHASES = frozenset({"complete", "escalated", "blocked", "approval_pending"})
RECOVERABLE_BLOCK_RETRY_SECONDS = 300
VULSCAN_APPROVAL_RECHECK_SECONDS = 24 * 60 * 60
VULSCAN_APPROVAL_ESCALATION_SECONDS = 10 * 24 * 60 * 60
VULSCAN_PATCH_WINDOW_RECHECK_SECONDS = 6 * 60 * 60
OFFLINE_AUGMENTATION_RECHECK_SECONDS = 10 * 60
OFFLINE_AUGMENTATION_WITNESS_COMMAND = "Get-NetIPConfiguration"


class OperationalAutonomyError(RuntimeError):
    pass


class DeviceAccessDeferred(OperationalAutonomyError):
    def __init__(self, *, work: "OperationalWork", reason: str) -> None:
        self.work = work
        super().__init__(reason)


class BackupIQManagedEndpointMissing(OperationalAutonomyError):
    def __init__(self, *, company_id: int, ci_id: int, hostname: str, provider_status: str) -> None:
        self.company_id = int(company_id)
        self.ci_id = int(ci_id)
        self.hostname = str(hostname)
        self.provider_status = str(provider_status)
        super().__init__(
            "BackupIQ provider asset is uniquely proven but the managed DRMM endpoint is absent; "
            f"company_id={self.company_id}; ci_id={self.ci_id}; hostname={self.hostname}; "
            f"provider_status={self.provider_status or 'unknown'}"
        )


@dataclass(frozen=True, slots=True)
class TicketScanSnapshot:
    cycle_id: str
    scanned_at: str
    pages_traversed: int
    provider_items: int
    duplicate_items: int
    evaluated: int
    eligible: int
    unsupported: int
    governance_blocked: int
    assigned_elsewhere: int
    active_slots: int
    selected: int
    waiting_device: int
    human_review: int


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
    source_version: str | None = None
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
        source_version TEXT,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS autonomy_ticket_scan_cycle (
        cycle_id TEXT PRIMARY KEY,
        scanned_at TEXT NOT NULL,
        pages_traversed INTEGER NOT NULL,
        provider_items INTEGER NOT NULL,
        duplicate_items INTEGER NOT NULL DEFAULT 0,
        evaluated INTEGER NOT NULL,
        eligible INTEGER NOT NULL,
        unsupported INTEGER NOT NULL,
        governance_blocked INTEGER NOT NULL,
        assigned_elsewhere INTEGER NOT NULL,
        active_slots INTEGER NOT NULL,
        selected INTEGER NOT NULL,
        waiting_device INTEGER NOT NULL,
        human_review INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS autonomy_ticket_classification (
        ticket_id INTEGER PRIMARY KEY,
        state TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        selected_count INTEGER NOT NULL DEFAULT 0,
        source_version TEXT
    );

    CREATE TABLE IF NOT EXISTS autonomy_ticket_note_state (
        ticket_id INTEGER NOT NULL,
        playbook_id TEXT NOT NULL,
        note_title TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        documented_at TEXT NOT NULL,
        PRIMARY KEY(ticket_id, playbook_id, note_title)
    );

    CREATE TABLE IF NOT EXISTS autonomy_ticket_augmentation_state (
        ticket_id INTEGER NOT NULL,
        augmentation_id TEXT NOT NULL,
        source_version TEXT,
        classification TEXT NOT NULL,
        evidence_fingerprint TEXT NOT NULL,
        checked_at TEXT NOT NULL,
        PRIMARY KEY(ticket_id, augmentation_id)
    );

    CREATE TABLE IF NOT EXISTS autonomy_ticket_activity (
        activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        ticket_number TEXT NOT NULL,
        title TEXT NOT NULL,
        playbook_id TEXT NOT NULL,
        source_queue TEXT NOT NULL,
        phase TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        occurred_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_autonomy_ticket_activity_occurred
        ON autonomy_ticket_activity(occurred_at, ticket_id);
    CREATE INDEX IF NOT EXISTS idx_autonomy_ticket_activity_ticket
        ON autonomy_ticket_activity(ticket_id, occurred_at);
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
        if "source_version" not in columns:
            self._connection.execute(
                "ALTER TABLE autonomy_operational_work ADD COLUMN source_version TEXT"
            )
        scan_columns = {
            str(row["name"])
            for row in self._connection.execute(
                "PRAGMA table_info(autonomy_ticket_scan_cycle)"
            ).fetchall()
        }
        if "duplicate_items" not in scan_columns:
            self._connection.execute(
                "ALTER TABLE autonomy_ticket_scan_cycle "
                "ADD COLUMN duplicate_items INTEGER NOT NULL DEFAULT 0"
            )
        # Preserve the latest known timestamp for pre-ledger work so historical
        # reporting has a bounded migration baseline without inventing events.
        self._connection.execute(
            """
            INSERT INTO autonomy_ticket_activity(
                ticket_id,ticket_number,title,playbook_id,source_queue,phase,reason,occurred_at
            )
            SELECT
                work.ticket_id,work.ticket_number,work.title,work.playbook_id,
                work.source_queue,work.phase,work.last_reason,work.updated_at
            FROM autonomy_operational_work AS work
            WHERE work.updated_at <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM autonomy_ticket_activity AS activity
                  WHERE activity.ticket_id = work.ticket_id
                    AND activity.occurred_at = work.updated_at
                    AND activity.phase = work.phase
              )
            """
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
            "WHERE phase NOT IN ("
            "'complete','escalated','blocked','approval_pending',"
            "'waiting_patch_approval','waiting_patch_window',"
            "'waiting_client_notification_authority'"
            ") "
            "AND phase NOT LIKE 'waiting_device_access:%' "
            "AND phase NOT LIKE 'waiting_recheck:%' "
            "ORDER BY updated_at,ticket_id"
        ).fetchall()
        return tuple(self._row(row) for row in rows)

    def list_waiting_device_access(self) -> tuple[OperationalWork, ...]:
        rows = self._connection.execute(
            "SELECT * FROM autonomy_operational_work "
            "WHERE phase LIKE 'waiting_device_access:%' "
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
                    component_uid,repair_attempts,last_reason,source_version,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    source_version=excluded.source_version,
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
                    work.source_version,
                    value,
                ),
            )
            self._connection.execute(
                """
                INSERT INTO autonomy_ticket_activity(
                    ticket_id,ticket_number,title,playbook_id,source_queue,phase,reason,occurred_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    work.ticket_id,
                    work.ticket_number,
                    work.title,
                    work.playbook_id,
                    work.source_queue,
                    work.phase,
                    work.last_reason,
                    value,
                ),
            )

    def delete(self, ticket_id: int) -> None:
        # Deliberately retain autonomy_ticket_note_state. A terminal work row may
        # be reconsidered after provider/ticket evidence changes, but unchanged
        # documentation must not be emitted again merely because the work row
        # was reopened.
        with self._connection:
            self._connection.execute(
                "DELETE FROM autonomy_operational_work WHERE ticket_id=?",
                (int(ticket_id),),
            )

    def record_scan(self, snapshot: TicketScanSnapshot) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO autonomy_ticket_scan_cycle(
                    cycle_id,scanned_at,pages_traversed,provider_items,duplicate_items,
                    evaluated,eligible,unsupported,governance_blocked,assigned_elsewhere,
                    active_slots,selected,waiting_device,human_review
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    snapshot.cycle_id, snapshot.scanned_at, snapshot.pages_traversed,
                    snapshot.provider_items, snapshot.duplicate_items, snapshot.evaluated,
                    snapshot.eligible, snapshot.unsupported, snapshot.governance_blocked,
                    snapshot.assigned_elsewhere, snapshot.active_slots,
                    snapshot.selected, snapshot.waiting_device, snapshot.human_review,
                ),
            )
            self._connection.execute(
                """
                DELETE FROM autonomy_ticket_scan_cycle
                WHERE cycle_id NOT IN (
                    SELECT cycle_id FROM autonomy_ticket_scan_cycle
                    ORDER BY scanned_at DESC LIMIT 500
                )
                """
            )

    def latest_scan(self) -> TicketScanSnapshot | None:
        row = self._connection.execute(
            "SELECT * FROM autonomy_ticket_scan_cycle ORDER BY scanned_at DESC LIMIT 1"
        ).fetchone()
        return None if row is None else TicketScanSnapshot(**dict(row))

    def record_classifications(
        self,
        rows: Sequence[tuple[int, str, str, str | None, bool]],
        *,
        observed_at: str,
    ) -> None:
        current_ids = [int(row[0]) for row in rows]
        with self._connection:
            if current_ids:
                placeholders = ",".join("?" for _ in current_ids)
                self._connection.execute(
                    f"DELETE FROM autonomy_ticket_classification "
                    f"WHERE ticket_id NOT IN ({placeholders})",
                    current_ids,
                )
            else:
                self._connection.execute("DELETE FROM autonomy_ticket_classification")
            for ticket_id, state, reason_code, source_version, selected in rows:
                self._connection.execute(
                    """
                    INSERT INTO autonomy_ticket_classification(
                        ticket_id,state,reason_code,first_seen,last_seen,
                        selected_count,source_version
                    ) VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(ticket_id) DO UPDATE SET
                        state=excluded.state,
                        reason_code=excluded.reason_code,
                        last_seen=excluded.last_seen,
                        selected_count=autonomy_ticket_classification.selected_count
                            + CASE WHEN excluded.selected_count > 0 THEN 1 ELSE 0 END,
                        source_version=excluded.source_version
                    """,
                    (
                        int(ticket_id), state, reason_code, observed_at, observed_at,
                        1 if selected else 0, source_version,
                    ),
                )

    def classification_state(self, ticket_id: int) -> str | None:
        row = self._connection.execute(
            "SELECT state FROM autonomy_ticket_classification WHERE ticket_id=?",
            (int(ticket_id),),
        ).fetchone()
        return None if row is None else str(row["state"])

    def last_note_fingerprint(
        self, ticket_id: int, playbook_id: str, note_title: str
    ) -> str | None:
        row = self._connection.execute(
            "SELECT fingerprint FROM autonomy_ticket_note_state "
            "WHERE ticket_id=? AND playbook_id=? AND note_title=?",
            (int(ticket_id), str(playbook_id), str(note_title)),
        ).fetchone()
        return None if row is None else str(row["fingerprint"])

    def remember_note_fingerprint(
        self,
        ticket_id: int,
        playbook_id: str,
        note_title: str,
        fingerprint: str,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO autonomy_ticket_note_state(
                    ticket_id,playbook_id,note_title,fingerprint,documented_at
                ) VALUES (?,?,?,?,?)
                ON CONFLICT(ticket_id,playbook_id,note_title) DO UPDATE SET
                    fingerprint=excluded.fingerprint,
                    documented_at=excluded.documented_at
                """,
                (
                    int(ticket_id),
                    str(playbook_id),
                    str(note_title),
                    str(fingerprint),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def augmentation_state(
        self,
        ticket_id: int,
        augmentation_id: str,
    ) -> Mapping[str, Any] | None:
        row = self._connection.execute(
            "SELECT source_version,classification,evidence_fingerprint,checked_at "
            "FROM autonomy_ticket_augmentation_state "
            "WHERE ticket_id=? AND augmentation_id=?",
            (int(ticket_id), str(augmentation_id)),
        ).fetchone()
        return None if row is None else dict(row)

    def remember_augmentation_state(
        self,
        *,
        ticket_id: int,
        augmentation_id: str,
        source_version: str | None,
        classification: str,
        evidence_fingerprint: str,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO autonomy_ticket_augmentation_state(
                    ticket_id,augmentation_id,source_version,classification,
                    evidence_fingerprint,checked_at
                ) VALUES (?,?,?,?,?,?)
                ON CONFLICT(ticket_id,augmentation_id) DO UPDATE SET
                    source_version=excluded.source_version,
                    classification=excluded.classification,
                    evidence_fingerprint=excluded.evidence_fingerprint,
                    checked_at=excluded.checked_at
                """,
                (
                    int(ticket_id),
                    str(augmentation_id),
                    str(source_version or "") or None,
                    str(classification),
                    str(evidence_fingerprint),
                    datetime.now(timezone.utc).isoformat(),
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
            source_version=row["source_version"],
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
        max_admission_attempts_per_scan: int = 4,
        max_candidate_evaluations_per_scan: int = 40,
        interval_seconds: int = 60,
        monotonic: Callable[[], float] = time.monotonic,
        audit=None,
        completion_notifier=None,
    ) -> None:
        if not 1 <= int(max_active_work_items) <= 20:
            raise ValueError("max_active_work_items must be between 1 and 20")
        if not 1 <= int(max_admission_attempts_per_scan) <= 20:
            raise ValueError("max_admission_attempts_per_scan must be between 1 and 20")
        if not 1 <= int(max_candidate_evaluations_per_scan) <= 200:
            raise ValueError("max_candidate_evaluations_per_scan must be between 1 and 200")
        if int(interval_seconds) < 30:
            raise ValueError("operational autonomy interval must be at least 30 seconds")
        self.queue_source = queue_source
        self.reads = reads
        self.actions = actions
        self.store = store
        self.promotion_store = promotion_store
        self.max_active_work_items = int(max_active_work_items)
        self.max_admission_attempts_per_scan = int(max_admission_attempts_per_scan)
        self.max_candidate_evaluations_per_scan = int(max_candidate_evaluations_per_scan)
        self.interval_seconds = int(interval_seconds)
        self.monotonic = monotonic
        self.audit = audit
        self.completion_notifier = completion_notifier
        self._next_due = 0.0
        self._resource_automation_cache: dict[int, bool] = {}
        self._ticket_status_cache: dict[int, str] = {}

    @staticmethod
    def _status_for_phase(phase: str) -> str | None:
        value = str(phase or "")
        if value == "waiting_patch_approval":
            return "Waiting Patch Approval"
        if value == "waiting_patch_window":
            return "On Hold"
        if value.startswith("waiting_device_access:"):
            return "Waiting Device Access"
        if value.startswith("waiting_recheck:"):
            return "On Hold"
        if value == "waiting_client_notification_authority":
            return "On Hold"
        if value == "approval_pending":
            return "Human Review"
        if value == "escalated":
            return "Human Review"
        if value == "complete":
            return "Complete"
        if value == "blocked":
            return "On Hold"
        return None

    def _update_ticket_status_verified(self, work: OperationalWork, status: str) -> None:
        normalized = str(status).strip()
        if self._ticket_status_cache.get(work.ticket_id, "").casefold() == normalized.casefold():
            return
        output = self.actions.execute(
            self._scope_for_work(work),
            "service.ticket.update",
            {"payload": {"id": work.ticket_id, "status": normalized}},
        )
        verification = self._action_data(output).get("jasonVerification")
        fields = verification.get("verifiedFields") if isinstance(verification, Mapping) else None
        if not (
            isinstance(verification, Mapping)
            and verification.get("readbackVerified") is True
            and isinstance(fields, Sequence)
            and not isinstance(fields, (str, bytes))
            and "status" in {str(value) for value in fields}
        ):
            raise OperationalAutonomyError(
                f"ticket status transition to {normalized!r} was not verified by provider readback"
            )
        self._ticket_status_cache[work.ticket_id] = normalized

    def _reconcile_ticket_status_for_phase(
        self,
        work: OperationalWork,
        observed_status: str | None = None,
    ) -> None:
        desired = self._status_for_phase(work.phase)
        if not desired:
            return
        observed = str(observed_status or "").strip()
        if observed.casefold() == desired.casefold():
            self._ticket_status_cache[work.ticket_id] = desired
            return
        self._update_ticket_status_verified(work, desired)

    def request_reconcile(self, reason: str) -> None:
        """Request a full queue reconciliation on the next maintenance tick."""
        del reason
        self._next_due = 0.0


    def _audit_diagnostic(self, event_type: str, payload: Mapping[str, Any]) -> None:
        """Emit one canonical worker diagnostic event without affecting ticket flow."""
        if self.audit is None:
            return
        event_id = f"autonomy-worker-{uuid4().hex}"
        self.audit.append(
            event_type,
            {
                "execution_id": event_id,
                "correlation_id": event_id,
                "organization_id": "aot",
                "principal_id": "jason-autonomy-worker",
                "capability_name": "autonomy.ticket.worker.scan",
                "stage": "completed",
                **dict(payload),
            },
        )

    def _reconcile_orphaned_waiting_device_rows(
        self,
        candidates_by_id: Mapping[int, Any],
    ) -> None:
        """Stop stale waiting rows without overriding authoritative PSA changes."""
        for work in self.store.list_waiting_device_access():
            if work.ticket_id in candidates_by_id:
                continue
            try:
                data = self._read_data(
                    "service.ticket.read",
                    {"resource_id": work.ticket_id},
                )
                items = data.get("items")
                if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], Mapping):
                    raise OperationalAutonomyError(
                        "waiting-device reconciliation requires exactly one ticket readback"
                    )
                ticket = dict(items[0])
                if int(ticket.get("id") or 0) != work.ticket_id:
                    raise OperationalAutonomyError(
                        "waiting-device reconciliation ticket identity mismatch"
                    )
                if ticket.get("completedDate"):
                    self.store.put(
                        self._replace(
                            work,
                            phase="complete",
                            last_reason=(
                                "Autotask ticket is complete; stale Waiting Device Access "
                                "worker state was retired without a PSA mutation."
                            ),
                        )
                    )
                    continue
                self.store.put(
                    self._replace(
                        work,
                        phase="escalated",
                        last_reason=(
                            "Autotask no longer presents this ticket in Jason's governed "
                            "Waiting Device Access candidate set. Autonomous waiting/resume "
                            "was stopped to preserve authoritative PSA/human state."
                        ),
                    )
                )
            except Exception as exc:
                if self.audit is not None:
                    self._audit_diagnostic(
                        "autonomy.waiting_device_reverse_reconcile.failed",
                        {
                            "ticket_id": work.ticket_id,
                            "error_type": type(exc).__name__,
                        },
                    )

    @staticmethod
    def _offline_augmentation_role(
        endpoint: Mapping[str, Any],
    ) -> tuple[str, bool, bool]:
        material = " ".join(
            (
                json.dumps(endpoint.get("device_type"), sort_keys=True, default=str),
                str(endpoint.get("operatingSystem") or endpoint.get("operating_system") or ""),
            )
        ).casefold()
        if any(token in material for token in ("laptop", "notebook", "portable")):
            return "laptop", False, True
        if "server" in material:
            return "server", True, False
        if any(token in material for token in ("desktop", "workstation", "main system chassis")):
            return "desktop", True, False
        return "unknown", False, False

    def _offline_augmentation_due(self, candidate) -> bool:
        ticket_id = int(candidate.resource_id)
        state = self.store.augmentation_state(
            ticket_id,
            OFFLINE_AUGMENTATION_SCOPE.playbook_id,
        )
        if state is None:
            return True
        observed_version = str(candidate.source_version or "").strip() or None
        recorded_version = str(state.get("source_version") or "").strip() or None
        if observed_version != recorded_version:
            return True
        checked = self._parse_iso_timestamp(state.get("checked_at"))
        if checked is None:
            return True
        return (
            datetime.now(timezone.utc) - checked
        ).total_seconds() >= OFFLINE_AUGMENTATION_RECHECK_SECONDS

    def _deb_asset_selection(
        self,
        *,
        company_id: int,
        hostname: str,
    ) -> DebAssetSelection:
        try:
            data = self._read_data(
                "backup.endpoint.asset.search",
                {
                    "company_id": company_id,
                    "name": hostname,
                    "page_size": 100,
                },
            )
        except Exception:
            return DebAssetSelection(
                state=DebAvailabilityState.UNAVAILABLE,
                hostname=hostname,
                exact_match_count=0,
                asset=None,
                selected_asset_id=None,
                selected_status=None,
                activity_at=None,
                reason="DEB availability read failed or is unavailable.",
            )
        items = data.get("items")
        if not isinstance(items, list):
            return DebAssetSelection(
                state=DebAvailabilityState.UNAVAILABLE,
                hostname=hostname,
                exact_match_count=0,
                asset=None,
                selected_asset_id=None,
                selected_status=None,
                activity_at=None,
                reason="DEB availability response did not contain an asset list.",
            )
        return select_deb_asset(
            items,
            hostname=hostname,
            observed_at=datetime.now(timezone.utc),
        )

    def _offline_augmentation_deb_online(
        self,
        *,
        company_id: int,
        hostname: str,
    ) -> bool | None:
        selection = self._deb_asset_selection(
            company_id=company_id,
            hostname=hostname,
        )
        if selection.state is DebAvailabilityState.ONLINE:
            return True
        if selection.state is DebAvailabilityState.OFFLINE:
            return False
        return None

    def _device_access_state(
        self,
        work: OperationalWork,
        *,
        endpoint: Mapping[str, Any] | None = None,
    ) -> tuple[str, DebAssetSelection]:
        current = (
            dict(endpoint)
            if endpoint is not None
            else self._read_record(
                "endpoint.device.read", {"resource_id": work.device_uid}
            )
        )
        endpoint_uid = str(
            current.get("resource_id")
            or current.get("uid")
            or current.get("deviceUid")
            or ""
        ).strip()
        endpoint_hostname = str(
            current.get("hostname")
            or current.get("hostName")
            or current.get("name")
            or ""
        ).strip()
        if endpoint_uid != work.device_uid:
            raise OperationalAutonomyError(
                "device availability DRMM identity changed during execution"
            )
        if endpoint_hostname and endpoint_hostname.casefold() != work.hostname.casefold():
            raise OperationalAutonomyError(
                "device availability DRMM hostname changed during execution"
            )

        if current.get("online") is True:
            return (
                "drmm_online",
                DebAssetSelection(
                    state=DebAvailabilityState.UNKNOWN,
                    hostname=work.hostname,
                    exact_match_count=0,
                    asset=None,
                    selected_asset_id=None,
                    selected_status=None,
                    activity_at=None,
                    reason="DEB read not required because DRMM is currently online.",
                ),
            )

        deb = self._deb_asset_selection(
            company_id=work.company_id,
            hostname=work.hostname,
        )
        if deb.state is DebAvailabilityState.ONLINE:
            return "deb_online_drmm_offline", deb
        if deb.state is DebAvailabilityState.OFFLINE:
            return "offline_corroborated", deb
        return "drmm_offline_unconfirmed", deb

    @staticmethod
    def _device_wait_reason(
        state: str,
        deb: DebAssetSelection,
    ) -> str:
        activity = (
            deb.activity_at.isoformat()
            if deb.activity_at is not None
            else "unknown"
        )
        if state == "deb_online_drmm_offline":
            return (
                "availability=deb_online_drmm_offline; DRMM reports the endpoint "
                "offline while DEB reports the current device online; waiting for "
                "DRMM management access rather than device power-on; "
                f"deb_asset={deb.selected_asset_id or 'unknown'}; "
                f"deb_activity={activity}."
            )
        if state == "offline_corroborated":
            return (
                "availability=offline_corroborated; DRMM and DEB independently "
                "report the endpoint offline; waiting for exact endpoint access; "
                f"deb_asset={deb.selected_asset_id or 'unknown'}; "
                f"deb_activity={activity}."
            )
        return (
            "availability=drmm_offline_unconfirmed; DRMM reports the endpoint "
            f"offline; DEB state={deb.state.value} and did not independently "
            "confirm whether the device is online; waiting for DRMM/device access."
        )

    def _document_deb_drmm_conflict(
        self,
        work: OperationalWork,
        deb: DebAssetSelection,
    ) -> None:
        activity = (
            deb.activity_at.isoformat()
            if deb.activity_at is not None
            else "unknown"
        )
        self._write_note(
            work,
            (
                "STATUS\n"
                f"{work.hostname} is not being treated as powered off. DEB reports "
                "the endpoint online while DRMM currently reports it offline.\n\n"
                "NEXT STEP\n"
                "Jason will preserve the ticket and wait for the DRMM management "
                "path when DRMM access is required. If an already-dispatched job "
                "can be polled safely, Jason may continue that read-only/status "
                "verification without waiting for DRMM's online flag to change.\n\n"
                "KEY EVIDENCE\n"
                "- DRMM online state=No\n"
                "- DEB online state=Yes\n"
                f"- DEB asset={deb.selected_asset_id or 'unknown'}\n"
                f"- DEB most recent activity={activity}\n"
                f"- Exact DEB hostname matches={deb.exact_match_count}\n\n"
                "CHANGES MADE\n"
                "None. Availability evidence only.\n\n"
                "JASON STATE\n"
                "waiting for DRMM management access; device itself is independently "
                "reported online by DEB"
            ),
            "Jason - Device Availability - DRMM Access",
        )

    def _offline_augmentation_live_server_witness(
        self,
        *,
        device_uid: str,
    ) -> bool:
        try:
            data = self._read_data(
                "endpoint.powershell.read",
                {
                    "device_uid": device_uid,
                    "command": OFFLINE_AUGMENTATION_WITNESS_COMMAND,
                    "timeout_seconds": 30,
                },
            )
        except Exception:
            return False
        stdout = str(data.get("stdout") or data.get("text") or "").strip()
        return bool(stdout)

    def _augment_offline_ticket_context(self, candidate) -> None:
        ticket = candidate.context
        ticket_id = int(candidate.resource_id)
        ci_raw = ticket.get("configurationItemID")
        try:
            ci_id = int(ci_raw)
        except (TypeError, ValueError):
            ci_id = 0

        if not is_offline_ticket(
            title=str(ticket.get("title") or ""),
            description=str(ticket.get("description") or ""),
            has_device_context=ci_id > 0,
        ):
            return
        if not self._offline_augmentation_due(candidate):
            return

        classification = "identity_unavailable"
        evidence_fingerprint = ""
        try:
            if ci_id <= 0:
                return

            company_id = self._company_id(ticket.get("companyID"))
            ci = self._read_data(
                "service.configuration.read",
                {"resource_id": ci_id},
            )
            if isinstance(ci.get("item"), Mapping):
                ci = dict(ci["item"])
            if (
                int(ci.get("id") or 0) != ci_id
                or self._company_id(ci.get("companyID")) != company_id
                or ci.get("isActive") is not True
            ):
                return

            device_uid = str(ci.get("referenceNumber") or "").strip()
            hostname = str(ci.get("referenceTitle") or "").strip()
            if not device_uid or not hostname:
                return

            endpoint = self._read_record(
                "endpoint.device.read",
                {"resource_id": device_uid},
            )
            observed_uid = str(
                endpoint.get("resource_id")
                or endpoint.get("uid")
                or endpoint.get("deviceUid")
                or ""
            ).strip()
            if observed_uid != device_uid:
                return
            target_drmm_online = (
                True if endpoint.get("online") is True
                else False if endpoint.get("online") is False
                else None
            )
            target_deb_online = self._offline_augmentation_deb_online(
                company_id=company_id,
                hostname=hostname,
            )
            site = str(endpoint.get("site") or "").strip() or None

            witnesses: list[SiteWitness] = []
            live_server_found = False
            if site:
                site_data = self._read_data(
                    "endpoint.device.search",
                    {"site": site},
                )
                matches = site_data.get("resource_matches")
                if isinstance(matches, list):
                    for raw_peer in matches[:20]:
                        if not isinstance(raw_peer, Mapping):
                            continue
                        peer_uid = str(
                            raw_peer.get("resource_id")
                            or raw_peer.get("uid")
                            or raw_peer.get("deviceUid")
                            or ""
                        ).strip()
                        if not peer_uid or peer_uid == device_uid:
                            continue

                        peer = dict(raw_peer)
                        role, fixed, mobile = self._offline_augmentation_role(peer)
                        peer_online = (
                            True if peer.get("online") is True
                            else False if peer.get("online") is False
                            else None
                        )
                        if role == "unknown" or peer_online is None:
                            try:
                                peer = self._read_record(
                                    "endpoint.device.read",
                                    {"resource_id": peer_uid},
                                )
                            except Exception:
                                continue
                            role, fixed, mobile = self._offline_augmentation_role(peer)
                            peer_online = (
                                True if peer.get("online") is True
                                else False if peer.get("online") is False
                                else None
                            )

                        peer_hostname = str(
                            peer.get("hostname")
                            or peer.get("hostName")
                            or peer.get("name")
                            or peer_uid
                        ).strip()
                        if not peer_hostname:
                            continue

                        live_read = False
                        site_confirmed = fixed and not mobile
                        if (
                            role == "server"
                            and peer_online is True
                            and not live_server_found
                        ):
                            live_read = self._offline_augmentation_live_server_witness(
                                device_uid=peer_uid,
                            )
                            if live_read:
                                live_server_found = True
                                site_confirmed = True

                        witnesses.append(
                            SiteWitness(
                                device_uid=peer_uid,
                                hostname=peer_hostname,
                                role=role,
                                online=peer_online,
                                fixed=fixed,
                                mobile=mobile,
                                site_presence_confirmed=site_confirmed,
                                live_read_succeeded=live_read,
                            )
                        )

            evidence = SiteContextEvidence(
                target_hostname=hostname,
                target_drmm_online=target_drmm_online,
                target_deb_online=target_deb_online,
                site_name=site,
                witnesses=tuple(witnesses),
            )
            assessment = classify_site_context(evidence)
            legacy_body = render_site_context_note(
                assessment,
                target_drmm_online=target_drmm_online,
                target_deb_online=target_deb_online,
                site_name=site,
            )
            classification = assessment.state.value
            note_title = canonical_title("technical_review")
            body = render_technical_note(
                TechnicalNote(
                    kind="technical_review",
                    status="Offline Context Assessed",
                    issue=str(candidate.context.get("title") or "Offline endpoint availability"),
                    scope=[
                        f"Ticket={candidate.context.get('ticketNumber') or ticket_id}",
                        f"CompanyID={candidate.context.get('companyID') or 0}",
                        f"Device={hostname or 'not resolved'}",
                        f"Site={site or 'not resolved'}",
                    ],
                    findings=[legacy_body],
                    evidence=[
                        f"Classification={classification}",
                        f"DRMMOnline={target_drmm_online}",
                        f"DEBOnline={target_deb_online}",
                        f"SiteWitnessCount={len(witnesses)}",
                    ],
                    actions_taken=["No endpoint remediation performed; this note records read-only availability correlation."],
                    verification=["Provider availability evidence was classified and fingerprinted."],
                    next_action="Continue according to the ticket playbook; this augmentation does not broaden execution authority.",
                    jason_state=[
                        f"Playbook={OFFLINE_AUGMENTATION_SCOPE.playbook_id}",
                        "Phase=offline_context_augmentation",
                        f"Classification={classification}",
                    ],
                )
            )
            evidence_fingerprint = assessment.fingerprint()

            prior = self.store.last_note_fingerprint(
                ticket_id,
                OFFLINE_AUGMENTATION_SCOPE.playbook_id,
                note_title,
            )
            if prior != evidence_fingerprint:
                self.actions.execute(
                    OFFLINE_AUGMENTATION_SCOPE,
                    "service.ticket.note.create",
                    {
                        "payload": {
                            "ticketID": ticket_id,
                            "title": note_title,
                            "description": body,
                            "noteType": 3,
                            "publish": 1,
                        }
                    },
                )
                self.store.remember_note_fingerprint(
                    ticket_id,
                    OFFLINE_AUGMENTATION_SCOPE.playbook_id,
                    note_title,
                    evidence_fingerprint,
                )
        finally:
            self.store.remember_augmentation_state(
                ticket_id=ticket_id,
                augmentation_id=OFFLINE_AUGMENTATION_SCOPE.playbook_id,
                source_version=(
                    str(candidate.source_version or "").strip() or None
                ),
                classification=classification,
                evidence_fingerprint=evidence_fingerprint,
            )

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
        self._reconcile_orphaned_waiting_device_rows(by_id)

        # Ticket augmentation is deliberately independent of queue ownership and
        # active-work capacity. It may add read-only context to a technician-owned
        # offline ticket, but it never claims, requeues, or changes ticket status.
        if self._scope_is_promoted(OFFLINE_AUGMENTATION_SCOPE):
            for item in candidates[: self.max_candidate_evaluations_per_scan]:
                try:
                    self._augment_offline_ticket_context(item)
                except Exception as exc:
                    if self.audit is not None:
                        self._audit_diagnostic(
                            "autonomy.offline_ticket_augmentation.failed",
                            {
                                "ticket_id": int(item.resource_id),
                                "error_type": type(exc).__name__,
                            },
                        )

        classifications: dict[
            int, tuple[str, str, str | None, bool]
        ] = {}
        backupiq_queue_blocked: set[int] = set()

        # BackupIQ ownership is a queue-routing invariant, not an active-work
        # scheduling decision. Normalize every open BackupIQ candidate before
        # evaluating active slots, endpoint availability, or remediation.
        for item in candidates:
            ticket_id = int(item.resource_id)
            existing_backupiq = self.store.get(ticket_id)
            backupiq_status = str(
                item.context.get("_jason_source_status_label") or ""
            ).strip().casefold()
            backupiq_human_handoff = (
                existing_backupiq is not None
                and existing_backupiq.playbook_id == BACKUPIQ_SCOPE.playbook_id
                and existing_backupiq.phase == "escalated"
            )
            if (
                self._is_backupiq_ticket(item.context)
                and str(item.source_queue).strip().casefold() != "jason"
                and backupiq_status != "human review"
                and not backupiq_human_handoff
            ):
                try:
                    self._normalize_backupiq_queue(item)
                except Exception:
                    ticket_id = int(item.resource_id)
                    backupiq_queue_blocked.add(ticket_id)
                    classifications[ticket_id] = (
                        "governance_blocked",
                        "backupiq_queue_normalization_failed",
                        item.source_version,
                        False,
                    )

        active = list(self.store.list_open())
        processed: set[int] = set()
        for work in active[: self.max_active_work_items]:
            candidate = by_id.get(work.ticket_id)
            if candidate is not None:
                classifications[work.ticket_id] = (
                    "eligible_now",
                    "active_work",
                    candidate.source_version,
                    True,
                )
            if candidate is None:
                self._block(
                    work,
                    "Ticket left the governed queue set while autonomous work was active.",
                )
                continue
            try:
                if self._pause_active_work_if_endpoint_offline(work, candidate):
                    state, reason_code = self._classify_persisted_work(work.ticket_id)
                    classifications[work.ticket_id] = (
                        state,
                        reason_code,
                        candidate.source_version,
                        False,
                    )
                    processed.add(work.ticket_id)
                    continue
                self._advance(work, candidate.context)
            except Exception as exc:
                self._block(
                    work,
                    f"Execution failed closed: {type(exc).__name__}: {str(exc)[:350]}",
                )
            state, reason_code = self._classify_persisted_work(work.ticket_id)
            classifications[work.ticket_id] = (
                state,
                reason_code,
                candidate.source_version,
                state == "eligible_now",
            )
            processed.add(work.ticket_id)

        eligible: list[tuple[Any, PlaybookScope]] = []
        unsupported = 0
        governance_blocked = 0
        assigned_elsewhere = 0
        human_review = 0

        for item in candidates:
            ticket_id = int(item.resource_id)
            if ticket_id in backupiq_queue_blocked:
                governance_blocked += 1
                continue
            existing = self.store.get(ticket_id)
            if (
                existing is not None
                and existing.playbook_id == BACKUPIQ_SCOPE.playbook_id
                and existing.phase == "escalated"
                and "inactive/offline endpoint"
                in str(existing.last_reason or "").casefold()
            ):
                endpoint_online = self._endpoint_is_online(existing.device_uid)
                desired_status = "In Progress" if endpoint_online else "Waiting Device Access"
                status_label = str(
                    item.context.get("_jason_source_status_label") or ""
                ).strip()
                if status_label.casefold() != desired_status.casefold():
                    self.actions.execute(
                        self._scope_for_work(existing),
                        "service.ticket.update",
                        {
                            "payload": {
                                "id": existing.ticket_id,
                                "status": desired_status,
                            }
                        },
                    )
                existing = self._replace(
                    existing,
                    phase=(
                        "backupiq_investigate"
                        if endpoint_online
                        else "waiting_device_access:backupiq_investigate"
                    ),
                    last_reason=(
                        "Migrated legacy BackupIQ offline escalation into the "
                        "resumable waiting-device lifecycle."
                        if not endpoint_online
                        else "Legacy BackupIQ offline escalation is online again; "
                        "resuming backupiq_investigate."
                    ),
                )
                self.store.put(existing)
            if existing is not None and existing.phase in TERMINAL_PHASES:
                if (
                    existing.phase == "blocked"
                    and self._recoverable_block_retry_due(existing)
                ):
                    self.store.delete(ticket_id)
                    existing = None
                elif existing.phase == "blocked":
                    try:
                        self._synchronize_blocked_ticket_lifecycle(existing, item)
                    except Exception as exc:
                        if self.audit is not None:
                            self._audit_diagnostic(
                                "autonomy.blocked_ticket_lifecycle_sync.failed",
                                {
                                    "ticket_id": ticket_id,
                                    "error_type": type(exc).__name__,
                                },
                            )
                    existing = self.store.get(ticket_id)
            if existing is not None and existing.phase in TERMINAL_PHASES:
                observed_version = str(item.source_version or "").strip() or None
                # A human-review handoff remains terminal while it stays outside
                # the Jason queue. The worker must not immediately reselect its
                # own Help Desk handoff merely because that governed update
                # changed the Autotask source-version marker.
                human_handoff = (
                    existing.phase == "escalated"
                    and (
                        existing.playbook_id == BACKUPIQ_SCOPE.playbook_id
                        or str(item.source_queue).strip().casefold() != "jason"
                    )
                )
                if (
                    not human_handoff
                    and observed_version
                    and observed_version != existing.source_version
                ):
                    self.store.delete(ticket_id)
                    existing = None
            if ticket_id in processed:
                continue
            if existing is not None:
                if existing.phase == "waiting_client_notification_authority":
                    if self._scope_is_promoted(VULSCAN_CLIENT_DISPOSITION_SCOPE):
                        if len(self.store.list_open()) < self.max_active_work_items:
                            existing = self._replace(
                                existing,
                                phase="vulscan_investigate",
                                last_reason=(
                                    "Exact VulScan client-disposition authority is active; "
                                    "resuming preserved work."
                                ),
                            )
                            self.store.put(existing)
                            try:
                                self._advance(existing, item.context)
                            except Exception as exc:
                                self._block(
                                    existing,
                                    "Execution failed closed after VulScan client-disposition "
                                    "authority resume: "
                                    f"{type(exc).__name__}: {str(exc)[:350]}",
                                )
                            state, reason_code = self._classify_persisted_work(ticket_id)
                            classifications[ticket_id] = (
                                state,
                                reason_code,
                                item.source_version,
                                state == "eligible_now",
                            )
                        else:
                            classifications[ticket_id] = (
                                "waiting_dependency",
                                "active_capacity_full",
                                item.source_version,
                                False,
                            )
                    else:
                        classifications[ticket_id] = (
                            "waiting_dependency",
                            "client_notification_authority_pending",
                            item.source_version,
                            False,
                        )
                    continue
                if existing.phase in {"waiting_patch_approval", "waiting_patch_window"}:
                    self._reconcile_ticket_status_for_phase(
                        existing,
                        item.context.get("_jason_source_status_label"),
                    )
                    interval = (
                        VULSCAN_APPROVAL_RECHECK_SECONDS
                        if existing.phase == "waiting_patch_approval"
                        else VULSCAN_PATCH_WINDOW_RECHECK_SECONDS
                    )
                    updated = self._parse_iso_timestamp(existing.updated_at)
                    due = (
                        updated is None
                        or (datetime.now(timezone.utc) - updated).total_seconds() >= interval
                    )
                    if due:
                        self._update_ticket_status_verified(existing, "In Progress")
                        existing = self._replace(
                            existing,
                            phase="vulscan_investigate",
                            last_reason=existing.last_reason,
                        )
                        self.store.put(existing)
                        try:
                            self._advance(existing, item.context)
                        except Exception as exc:
                            self._block(
                                existing,
                                "Execution failed closed during VulScan waiting-state recheck: "
                                f"{type(exc).__name__}: {str(exc)[:350]}",
                            )
                    state, reason_code = self._classify_persisted_work(ticket_id)
                    classifications[ticket_id] = (
                        state,
                        reason_code,
                        item.source_version,
                        False,
                    )
                    continue
                if existing.phase.startswith("waiting_device_access:"):
                    self._reconcile_ticket_status_for_phase(
                        existing,
                        item.context.get("_jason_source_status_label"),
                    )
                    waiting_phase = existing.phase
                    try:
                        access_state, deb = self._device_access_state(existing)
                    except Exception:
                        access_state = "drmm_offline_unconfirmed"
                        deb = DebAssetSelection(
                            state=DebAvailabilityState.UNAVAILABLE,
                            hostname=existing.hostname,
                            exact_match_count=0,
                            asset=None,
                            selected_asset_id=None,
                            selected_status=None,
                            activity_at=None,
                            reason="Availability recheck failed closed.",
                        )

                    resume_phase = waiting_phase.split(":", 1)[1]
                    safe_deb_resume = (
                        access_state == "deb_online_drmm_offline"
                        and bool(existing.job_uid)
                        and resume_phase.endswith("_wait")
                    )
                    may_resume = access_state == "drmm_online" or safe_deb_resume

                    if access_state == "deb_online_drmm_offline":
                        self._document_deb_drmm_conflict(existing, deb)

                    if may_resume:
                        if len(self.store.list_open()) < self.max_active_work_items:
                            scope = self._scope_for_work(existing)
                            self.actions.execute(
                                scope,
                                "service.ticket.update",
                                {
                                    "payload": {
                                        "id": existing.ticket_id,
                                        "status": "In Progress",
                                    }
                                },
                            )
                            resume_reason = (
                                existing.last_reason
                                if (
                                    existing.playbook_id == BACKUPIQ_SCOPE.playbook_id
                                    and resume_phase == "backupiq_verify_reinstall"
                                )
                                else (
                                    "DEB independently reports the endpoint online while "
                                    "DRMM is offline; resuming only the already-dispatched "
                                    "job polling phase."
                                    if safe_deb_resume
                                    else "Exact endpoint is online again; resuming preserved work."
                                )
                            )
                            existing = self._replace(
                                existing,
                                phase=resume_phase,
                                last_reason=resume_reason,
                            )
                            self.store.put(existing)
                            try:
                                self._advance(existing, item.context)
                            except Exception as exc:
                                self._block(
                                    existing,
                                    "Execution failed closed after device-access resume: "
                                    f"{type(exc).__name__}: {str(exc)[:350]}",
                                )
                            state, reason_code = self._classify_persisted_work(ticket_id)
                            classifications[ticket_id] = (
                                state,
                                reason_code,
                                item.source_version,
                                state == "eligible_now",
                            )
                        else:
                            classifications[ticket_id] = (
                                "waiting_device_access",
                                "active_capacity_full",
                                item.source_version,
                                False,
                            )
                    else:
                        reason = self._device_wait_reason(access_state, deb)
                        prior_reason = str(existing.last_reason or "").strip()
                        prior_prefix = (
                            prior_reason.split("availability=", 1)[0].strip(" ;")
                            if "availability=" in prior_reason
                            else prior_reason
                        )
                        combined_reason = (
                            f"{prior_prefix}; {reason}"
                            if prior_prefix
                            else reason
                        )
                        if combined_reason != existing.last_reason:
                            existing = self._replace(
                                existing,
                                last_reason=combined_reason,
                            )
                            self.store.put(existing)
                        reason_code = (
                            "drmm_access_unavailable_device_online_deb"
                            if access_state == "deb_online_drmm_offline"
                            else "endpoint_offline_corroborated_deb"
                            if access_state == "offline_corroborated"
                            else "endpoint_offline_deb_unconfirmed"
                        )
                        classifications[ticket_id] = (
                            "waiting_device_access",
                            reason_code,
                            item.source_version,
                            False,
                        )
                    continue
                if existing.phase.startswith("waiting_recheck:"):
                    self._reconcile_ticket_status_for_phase(
                        existing,
                        item.context.get("_jason_source_status_label"),
                    )
                    if len(self.store.list_open()) < self.max_active_work_items:
                        self._update_ticket_status_verified(existing, "In Progress")
                        waiting_phase = existing.phase
                        resume_phase = waiting_phase.split(":", 1)[1]
                        waiting_since = existing.updated_at
                        resume_reason = (
                            existing.last_reason
                            if (
                                (
                                    existing.playbook_id == BACKUPIQ_SCOPE.playbook_id
                                    and resume_phase == "backupiq_verify_reinstall"
                                )
                                or existing.playbook_id == LOW_DISK_SCOPE.playbook_id
                            )
                            else "Scheduled recheck due; resuming preserved work."
                        )
                        existing = self._replace(
                            existing,
                            phase=resume_phase,
                            last_reason=resume_reason,
                            updated_at=waiting_since,
                        )
                        self.store.put(existing)
                        try:
                            self._advance(existing, item.context)
                        except Exception as exc:
                            self._block(
                                existing,
                                "Execution failed closed after scheduled recheck resume: "
                                f"{type(exc).__name__}: {str(exc)[:350]}",
                            )
                        state, reason_code = self._classify_persisted_work(ticket_id)
                        classifications[ticket_id] = (
                            state,
                            reason_code,
                            item.source_version,
                            state == "eligible_now",
                        )
                    else:
                        classifications[ticket_id] = (
                            "waiting_recheck",
                            "active_capacity_full",
                            item.source_version,
                            False,
                        )
                    continue
                if existing.phase == "escalated":
                    human_review += 1
                    if existing.playbook_id == BACKUPIQ_SCOPE.playbook_id:
                        state, reason_code = (
                            "waiting_human_review",
                            "technician_review_required",
                        )
                    elif str(item.source_queue).strip().casefold() == "jason":
                        try:
                            self._handoff_to_helpdesk(existing)
                            state, reason_code = (
                                "waiting_human_review",
                                "technician_review_required",
                            )
                        except Exception:
                            governance_blocked += 1
                            state, reason_code = (
                                "governance_blocked",
                                "human_review_handoff_failed",
                            )
                    else:
                        state, reason_code = (
                            "waiting_human_review",
                            "technician_review_required",
                        )
                elif existing.phase == "approval_pending":
                    state, reason_code = "waiting_human_review", "approval_required"
                elif existing.phase == "blocked":
                    state, reason_code = "governance_blocked", "worker_blocked"
                elif existing.phase == "complete":
                    state, reason_code = "not_actionable", "already_complete"
                else:
                    state, reason_code = "eligible_now", "existing_active_work"
                classifications[ticket_id] = (
                    state, reason_code, item.source_version, state == "eligible_now"
                )
                continue
            scope = self._match_scope(item.context)
            if scope is None:
                unsupported += 1
                classifications[ticket_id] = (
                    "unsupported_capability", "no_applicable_promoted_playbook",
                    item.source_version, False,
                )
                continue
            if not self._scope_is_promoted(scope):
                governance_blocked += 1
                classifications[ticket_id] = (
                    "governance_blocked", "playbook_not_promoted",
                    item.source_version, False,
                )
                continue
            # Broad open-status discovery is useful for read-only assessment, but
            # autonomous admission outside Jason is limited to intake states.
            # This prevents a matching playbook from claiming work already being
            # handled by a technician simply because it appears in the open view.
            source_status = str(
                item.context.get("_jason_source_status_label") or ""
            ).strip().casefold()
            if (
                str(item.source_queue).strip().casefold() != "jason"
                and source_status not in {"new", "emergency"}
            ):
                classifications[ticket_id] = (
                    "not_actionable",
                    "discovery_status_not_admissible",
                    item.source_version,
                    False,
                )
                continue
            if item.context.get("_jason_assigned_elsewhere") is True:
                assigned_elsewhere += 1
                if not self._assigned_new_ticket_is_unworked(item):
                    classifications[ticket_id] = (
                        "not_actionable", "existing_technician_activity",
                        item.source_version, False,
                    )
                    continue
            eligible.append((item, scope))
            classifications[ticket_id] = (
                "eligible_now", "promoted_safe_branch_available",
                item.source_version, False,
            )

        # Keep prioritization deliberately simple and auditable: urgent first,
        # then PSA priority, then already-owned work, then oldest ticket ID.
        # Endpoints already proven offline in the previous scan are deprioritized
        # so unrelated work gets first use of the bounded candidate-evaluation budget.
        # Offline state is local to the affected ticket and never consumes an active
        # work slot or the non-offline admission-attempt budget.
        prior_states = {
            int(item.resource_id): self.store.classification_state(int(item.resource_id))
            for item, _ in eligible
        }
        eligible.sort(
            key=lambda pair: (
                int(prior_states.get(int(pair[0].resource_id)) == "waiting_device_access"),
                -int(pair[0].urgent),
                -pair[0].priority,
                -int(pair[0].owned_by_jason),
                int(pair[0].resource_id),
            )
        )
        started = 0
        waiting_device = 0
        admission_attempts = 0
        candidate_evaluations = 0
        for candidate, scope in eligible:
            # Recompute occupancy after every advancement. If a ticket completes,
            # blocks, or hands off immediately, refill the freed slot during this
            # same scan rather than idling until the next cadence.
            if len(self.store.list_open()) >= self.max_active_work_items:
                break
            if admission_attempts >= self.max_admission_attempts_per_scan:
                break
            if candidate_evaluations >= self.max_candidate_evaluations_per_scan:
                break
            candidate_evaluations += 1
            try:
                work = self._admit(candidate, scope)
            except Exception as exc:
                message = str(exc).casefold()
                if (
                    "endpoint is not currently online" in message
                    or "drmm access unavailable while deb reports endpoint online" in message
                ):
                    waiting_device += 1
                    reason_code = (
                        "drmm_access_unavailable_device_online_deb"
                        if "drmm access unavailable while deb reports endpoint online" in message
                        else "endpoint_offline_corroborated_deb"
                        if "deb corroborated" in message
                        else "endpoint_offline_deb_unconfirmed"
                    )
                    classifications[int(candidate.resource_id)] = (
                        "waiting_device_access", reason_code,
                        candidate.source_version, False,
                    )
                    self._record_admission_failure(candidate, scope, exc)
                    # Endpoint/management-path availability is local to this ticket.
                    # Defer it and keep searching for unrelated eligible work.
                    continue
                admission_attempts += 1
                classifications[int(candidate.resource_id)] = (
                    "governance_blocked", "admission_identity_or_governance_failure",
                    candidate.source_version, False,
                )
                # Non-offline admission failures consume the bounded admission
                # budget because they can involve expensive identity/governance work.
                self._record_admission_failure(candidate, scope, exc)
                continue
            admission_attempts += 1
            started += 1
            classifications[int(candidate.resource_id)] = (
                "eligible_now", "active_work", candidate.source_version, True
            )
            try:
                self._advance(work, candidate.context)
            except Exception as exc:
                self._block(
                    work,
                    f"Execution failed closed: {type(exc).__name__}: {str(exc)[:350]}",
                )
            state, reason_code = self._classify_persisted_work(work.ticket_id)
            classifications[work.ticket_id] = (
                state,
                reason_code,
                candidate.source_version,
                True,
            )

        # Derive coverage counts from the final current classifications so
        # telemetry includes existing active/waiting/handoff rows as well as new
        # admissions from this cycle.
        unsupported = sum(
            1 for state, _, _, _ in classifications.values()
            if state == "unsupported_capability"
        )
        governance_blocked = sum(
            1 for state, _, _, _ in classifications.values()
            if state == "governance_blocked"
        )
        human_review = sum(
            1 for state, _, _, _ in classifications.values()
            if state == "waiting_human_review"
        )
        waiting_device = sum(
            1 for state, _, _, _ in classifications.values()
            if state == "waiting_device_access"
        )
        assigned_elsewhere = sum(
            1 for state, reason, _, _ in classifications.values()
            if state == "not_actionable" and reason == "existing_technician_activity"
        )
        eligible_count = sum(
            1 for state, _, _, _ in classifications.values()
            if state == "eligible_now"
        )

        trace = getattr(self.queue_source, "last_trace", None)
        scanned_at = datetime.now(timezone.utc).isoformat()
        self.store.record_classifications(
            [
                (ticket_id, state, reason, source_version, selected)
                for ticket_id, (state, reason, source_version, selected)
                in classifications.items()
            ],
            observed_at=scanned_at,
        )
        cycle_id = f"scan-{uuid4().hex}"
        snapshot = TicketScanSnapshot(
            cycle_id=cycle_id,
            scanned_at=scanned_at,
            pages_traversed=int(getattr(trace, "pages_traversed", 0)),
            provider_items=int(getattr(trace, "provider_items", len(candidates))),
            duplicate_items=int(getattr(trace, "duplicate_items", 0)),
            evaluated=len(candidates),
            eligible=eligible_count,
            unsupported=unsupported,
            governance_blocked=governance_blocked,
            assigned_elsewhere=assigned_elsewhere,
            active_slots=len(self.store.list_open()),
            selected=started,
            waiting_device=waiting_device,
            human_review=human_review,
        )
        self.store.record_scan(snapshot)
        self._emit_scan_reflection(snapshot)

    def _emit_scan_reflection(self, snapshot: TicketScanSnapshot) -> None:
        if self.audit is None:
            return
        warnings: list[str] = []
        if snapshot.unsupported:
            warnings.append("worker_unsupported_capability_present")
        if snapshot.governance_blocked:
            warnings.append("worker_governance_blocked_present")
        self.audit.append(
            "orchestration.capability.completed",
            {
                "execution_id": snapshot.cycle_id,
                "correlation_id": snapshot.cycle_id,
                "organization_id": "aot",
                "principal_id": "jason-autonomy-worker",
                "capability_name": "autonomy.ticket.worker.scan",
                "stage": "completed",
                "provider_id": "autotask",
                "status": "completed",
                "reflection_normalized_intent": "scan_approved_open_ticket_scope",
                "reflection_selector_strategy": "open_status_queue_scoped_pagination",
                "reflection_requested_result_scope": "full",
                "reflection_result_count": snapshot.evaluated,
                "reflection_candidate_count": snapshot.eligible,
                "reflection_provider_call_count": snapshot.pages_traversed,
                "reflection_pagination_count": snapshot.pages_traversed,
                "reflection_evidence_item_count": snapshot.provider_items,
                "reflection_warning_codes": warnings,
            },
        )

    def _endpoint_is_online(self, device_uid: str) -> bool:
        try:
            endpoint = self._read_record(
                "endpoint.device.read", {"resource_id": device_uid}
            )
        except Exception:
            return False
        endpoint_uid = str(
            endpoint.get("resource_id")
            or endpoint.get("uid")
            or endpoint.get("deviceUid")
            or ""
        ).strip()
        if endpoint_uid != device_uid:
            return False
        return endpoint.get("online") is True

    def _pause_active_work_if_endpoint_offline(self, work: OperationalWork, candidate) -> bool:
        # BackupIQ owns its full dual-source branch separately.
        if work.playbook_id == BACKUPIQ_SCOPE.playbook_id:
            return False
        if not work.job_uid:
            return False
        if work.phase.startswith("waiting_device_access:"):
            return True

        try:
            access_state, deb = self._device_access_state(work)
        except Exception:
            return False

        if access_state == "drmm_online":
            return False
        if access_state == "deb_online_drmm_offline":
            # A job is already dispatched. DEB proves the machine is alive, so
            # polling the existing provider job is safe and does not redispatch.
            self._document_deb_drmm_conflict(work, deb)
            return False

        scope = self._scope_for_work(work)
        status_label = str(
            candidate.context.get("_jason_source_status_label") or ""
        ).strip()
        if status_label.casefold() != "waiting device access":
            self.actions.execute(
                scope,
                "service.ticket.update",
                {
                    "payload": {
                        "id": work.ticket_id,
                        "status": "Waiting Device Access",
                    }
                },
            )
        self.store.put(
            self._replace(
                work,
                phase=f"waiting_device_access:{work.phase}",
                last_reason=self._device_wait_reason(access_state, deb),
            )
        )
        return True

    @staticmethod
    def _block_is_retryable(work: OperationalWork) -> bool:
        reason = str(work.last_reason or "").casefold()
        return any(
            token in reason
            for token in (
                "governed read failed",
                "database is locked",
                "execution_plan_authorization_rejected",
                "datto_component_autonomy_requires_standing_safe",
                "provider_http_status_500",
                "provider_http_status_502",
                "provider_http_status_503",
                "provider_http_status_504",
            )
        )

    def _recoverable_block_retry_due(self, work: OperationalWork) -> bool:
        if not self._block_is_retryable(work):
            return False
        updated = self._parse_iso_timestamp(work.updated_at)
        if updated is None:
            return False
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        return age >= RECOVERABLE_BLOCK_RETRY_SECONDS

    def _synchronize_blocked_ticket_lifecycle(self, work: OperationalWork, candidate) -> None:
        if str(candidate.source_queue).strip().casefold() != "jason":
            return
        status_label = str(
            candidate.context.get("_jason_source_status_label") or ""
        ).strip()
        if self._block_is_retryable(work):
            if status_label.casefold() != "on hold":
                self._update_ticket_status_verified(work, "On Hold")
            return

        self._write_note(
            work,
            (
                "Jason cannot safely continue this ticket automatically. "
                f"Blocker: {work.last_reason}. "
                "The ticket is being returned to Help Desk I for technician review "
                "instead of remaining untriaged in the Jason queue."
            ),
            "Jason - Human Review Required",
        )
        self._handoff_to_helpdesk(work, status="Human Review")
        self.store.put(
            self._replace(
                work,
                phase="escalated",
                last_reason=work.last_reason,
            )
        )

    def _classify_persisted_work(self, ticket_id: int) -> tuple[str, str]:
        current = self.store.get(ticket_id)
        if current is None:
            return "eligible_now", "active_work"
        if current.phase == "escalated":
            return "waiting_human_review", "technician_review_required"
        if current.phase == "approval_pending":
            return "waiting_human_review", "approval_required"
        if current.phase == "waiting_patch_approval":
            return "waiting_dependency", "patch_approval_pending"
        if current.phase == "waiting_patch_window":
            return "waiting_dependency", "patch_window_pending"
        if current.phase == "waiting_client_notification_authority":
            return "waiting_dependency", "client_notification_authority_pending"
        if current.phase == "blocked":
            return "governance_blocked", "worker_blocked"
        if current.phase == "complete":
            return "not_actionable", "already_complete"
        if current.phase.startswith("waiting_device_access:"):
            reason = str(current.last_reason or "")
            if "availability=deb_online_drmm_offline" in reason:
                return (
                    "waiting_device_access",
                    "drmm_access_unavailable_device_online_deb",
                )
            if "availability=offline_corroborated" in reason:
                return "waiting_device_access", "endpoint_offline_corroborated_deb"
            return "waiting_device_access", "endpoint_offline_deb_unconfirmed"
        if current.phase.startswith("waiting_recheck:"):
            return "waiting_recheck", "scheduled_recheck"
        return "eligible_now", "active_work"

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

    def _normalize_backupiq_queue(self, candidate) -> None:
        output = self.actions.execute(
            BACKUPIQ_SCOPE,
            "service.ticket.update",
            {
                "payload": {
                    "id": int(candidate.resource_id),
                    "queueID": "Jason",
                }
            },
        )
        verification = self._action_data(output).get("jasonVerification")
        verified_fields = (
            verification.get("verifiedFields")
            if isinstance(verification, Mapping)
            else None
        )
        if not (
            isinstance(verification, Mapping)
            and verification.get("readbackVerified") is True
            and isinstance(verified_fields, Sequence)
            and not isinstance(verified_fields, (str, bytes))
            and "queueID" in {str(value) for value in verified_fields}
        ):
            raise OperationalAutonomyError(
                "BackupIQ queue normalization readback did not verify queueID"
            )

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

    @staticmethod
    def _structured_ticket_hostname(title: str) -> str | None:
        for pattern in (
            r"^Vulnerability Detected by VulScan\s*-\s*([A-Za-z0-9._-]+)\s*\(",
            r"\bfor\s+([A-Za-z0-9._-]+)\s*$",
        ):
            match = re.search(pattern, title, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", value):
                    continue
                return value
        return None

    @staticmethod
    def _normalized_mac(value: object) -> str:
        return re.sub(r"[^0-9A-Fa-f]", "", str(value or "")).casefold()

    @classmethod
    def _ticket_identity_evidence(cls, candidate) -> Mapping[str, set[str]]:
        material = " ".join(
            (
                str(candidate.context.get("title") or ""),
                str(candidate.context.get("description") or ""),
            )
        )
        ips = {
            value
            for value in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", material)
            if all(0 <= int(part) <= 255 for part in value.split("."))
        }
        macs = {
            cls._normalized_mac(value)
            for value in re.findall(
                r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b", material
            )
        }
        serials = {
            value.casefold()
            for value in re.findall(
                r"\bserial(?:\s+number)?\s*[:=#-]?\s*([A-Za-z0-9._-]{4,64})",
                material,
                flags=re.IGNORECASE,
            )
        }
        tokens = {
            value.casefold()
            for value in re.findall(r"\b[A-Za-z0-9][A-Za-z0-9._-]{2,127}\b", material)
        }
        return {
            "ips": ips,
            "macs": {value for value in macs if value},
            "serials": serials,
            "tokens": tokens,
        }

    @classmethod
    def _endpoint_identity_score(
        cls,
        endpoint: Mapping[str, Any],
        *,
        hints: Sequence[str],
        evidence: Mapping[str, set[str]],
    ) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
        matched: list[str] = []
        conflicts: list[str] = []
        hostname = str(
            endpoint.get("hostname") or endpoint.get("hostName") or endpoint.get("name") or ""
        ).strip()
        if hostname and hostname.casefold() in {hint.casefold() for hint in hints}:
            matched.append("hostname")

        endpoint_uid = str(
            endpoint.get("resource_id") or endpoint.get("uid") or endpoint.get("deviceUid") or ""
        ).strip()
        if endpoint_uid and endpoint_uid.casefold() in evidence.get("tokens", set()):
            matched.append("device_uid")

        endpoint_ips = {
            str(endpoint.get(key) or "").strip()
            for key in ("lan_ip", "wan_ip", "intIpAddress", "extIpAddress")
            if str(endpoint.get(key) or "").strip()
        }
        if endpoint_ips & evidence.get("ips", set()):
            matched.append("ip")

        endpoint_mac = cls._normalized_mac(
            endpoint.get("mac_address") or endpoint.get("macAddress") or endpoint.get("mac")
        )
        ticket_macs = evidence.get("macs", set())
        if endpoint_mac and ticket_macs:
            if endpoint_mac in ticket_macs:
                matched.append("mac")
            else:
                conflicts.append("mac")

        endpoint_serial = str(
            endpoint.get("serial_number")
            or endpoint.get("serialNumber")
            or endpoint.get("serial")
            or ""
        ).strip().casefold()
        ticket_serials = evidence.get("serials", set())
        if endpoint_serial and ticket_serials:
            if endpoint_serial in ticket_serials:
                matched.append("serial")
            else:
                conflicts.append("serial")

        return len(set(matched)), tuple(sorted(set(matched))), tuple(sorted(set(conflicts)))

    def _write_verified_ci_association(
        self, *, candidate, scope: PlaybookScope, ci_id: int
    ) -> int:
        output = self.actions.execute(
            scope,
            "service.ticket.update",
            {"payload": {"id": int(candidate.resource_id), "configurationItemID": ci_id}},
        )
        verification = self._action_data(output).get("jasonVerification")
        fields = verification.get("verifiedFields") if isinstance(verification, Mapping) else None
        if not (
            isinstance(verification, Mapping)
            and verification.get("readbackVerified") is True
            and isinstance(fields, Sequence)
            and not isinstance(fields, (str, bytes))
            and "configurationItemID" in {str(value) for value in fields}
        ):
            raise OperationalAutonomyError(
                "device association write was not verified by provider readback"
            )
        return ci_id

    def _associate_backupiq_unassigned_ticket_device(
        self, *, candidate, scope: PlaybookScope
    ) -> tuple[int, int] | None:
        """Recover a BackupIQ ticket that arrived without an authoritative company.

        BackupIQ email-created tickets can arrive as company 0 even when the exact
        managed endpoint and Autotask configuration belong to a client company.
        Recover only when one exact DRMM endpoint and one exact active Autotask CI
        prove the same identity. Never guess across multiple companies/devices.
        """
        material = " ".join(
            (
                str(candidate.context.get("title") or ""),
                str(candidate.context.get("description") or ""),
            )
        )
        hints: list[str] = []
        structured_hostname = self._structured_ticket_hostname(
            str(candidate.context.get("title") or "")
        )
        if structured_hostname:
            hints.append(structured_hostname)
        for token in re.findall(r"\b[A-Za-z0-9][A-Za-z0-9._-]{2,62}\b", material):
            if not any(ch.isalpha() for ch in token) or not any(ch.isdigit() for ch in token):
                continue
            if token.casefold() not in {item.casefold() for item in hints}:
                hints.append(token)
            if len(hints) >= 8:
                break
        if not hints:
            return None

        endpoints: dict[str, Mapping[str, Any]] = {}
        for hint in hints:
            data = self._read_data("endpoint.device.search", {"hostname": hint})
            raw = data.get("resource_matches") or data.get("records") or data.get("items") or ()
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
                continue
            for item in raw:
                if not isinstance(item, Mapping):
                    continue
                hostname = str(
                    item.get("hostname") or item.get("hostName") or item.get("name") or ""
                ).strip()
                uid = str(
                    item.get("resource_id") or item.get("uid") or item.get("deviceUid") or ""
                ).strip()
                if hostname.casefold() == hint.casefold() and uid:
                    endpoints[uid] = item
        if len(endpoints) == 0:
            ci_matches: list[Mapping[str, Any]] = []
            for hint in hints:
                data = self._read_data(
                    "service.configuration.search",
                    {"name": hint, "page_size": 25},
                )
                raw_items = data.get("items")
                if not isinstance(raw_items, list):
                    continue
                for item in raw_items:
                    if not isinstance(item, Mapping) or item.get("isActive") is not True:
                        continue
                    if str(item.get("referenceTitle") or "").strip().casefold() != hint.casefold():
                        continue
                    ci_matches.append(item)
            unique_ci = {int(item.get("id")): item for item in ci_matches if item.get("id")}
            if len(unique_ci) == 1:
                ci = next(iter(unique_ci.values()))
                company_id = self._company_id(ci.get("companyID"))
                ci_id = self._positive_int(ci.get("id"), "configuration item id")
                hostname = str(ci.get("referenceTitle") or "").strip()
                if company_id > 0 and hostname:
                    asset_data = self._read_data(
                        "backup.endpoint.asset.search",
                        {"company_id": company_id, "name": hostname, "page_size": 25},
                    )
                    asset_items = asset_data.get("items")
                    if isinstance(asset_items, list):
                        exact_assets = [
                            item for item in asset_items
                            if isinstance(item, Mapping)
                            and str(item.get("name") or "").strip().casefold() == hostname.casefold()
                        ]
                        if len(exact_assets) == 1:
                            raise BackupIQManagedEndpointMissing(
                                company_id=company_id,
                                ci_id=ci_id,
                                hostname=hostname,
                                provider_status=str(exact_assets[0].get("status") or ""),
                            )
            return None
        if len(endpoints) != 1:
            return None

        endpoint_uid, endpoint = next(iter(endpoints.items()))
        hostname = str(
            endpoint.get("hostname") or endpoint.get("hostName") or endpoint.get("name") or ""
        ).strip()
        if not hostname:
            return None

        data = self._read_data(
            "service.configuration.search",
            {"name": hostname, "page_size": 25},
        )
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            return None
        matches = [
            item
            for item in raw_items
            if isinstance(item, Mapping)
            and item.get("isActive") is True
            and str(item.get("referenceNumber") or "").strip() == endpoint_uid
            and str(item.get("referenceTitle") or "").strip().casefold() == hostname.casefold()
        ]
        if len(matches) != 1:
            return None
        company_id = self._company_id(matches[0].get("companyID"))
        if company_id <= 0:
            return None
        ci_id = self._positive_int(matches[0].get("id"), "configuration item id")
        # The inbound BackupIQ ticket may legitimately be company 0 even when
        # provider/CI evidence proves the client. Do not attempt a cross-company
        # CI mutation: Autotask rejects it and the ticket field is not authority.
        # Carry the independently proven company/CI inside governed work instead.
        return ci_id, company_id

    def _associate_exact_ticket_device(
        self, *, candidate, scope: PlaybookScope, company_id: int
    ) -> int:
        title = str(candidate.context.get("title") or "")
        structured_hostname = self._structured_ticket_hostname(title)
        if structured_hostname:
            data = self._read_data(
                "service.configuration.search",
                {
                    "company_id": company_id,
                    "name": structured_hostname,
                    "page_size": 25,
                },
            )
            raw_items = data.get("items")
            if not isinstance(raw_items, list):
                raise OperationalAutonomyError(
                    "configuration search returned invalid items"
                )
            matches = [
                item
                for item in raw_items
                if isinstance(item, Mapping)
                and item.get("isActive") is True
                and self._company_id(item.get("companyID")) == company_id
                and str(item.get("referenceTitle") or "").strip().casefold()
                == structured_hostname.casefold()
                and str(item.get("referenceNumber") or "").strip()
            ]
            if len(matches) == 1:
                ci = matches[0]
                ci_id = self._positive_int(ci.get("id"), "configuration item id")
                endpoint_uid = str(ci.get("referenceNumber") or "").strip()
                endpoint = self._read_record(
                    "endpoint.device.read", {"resource_id": endpoint_uid}
                )
                read_uid = str(
                    endpoint.get("resource_id")
                    or endpoint.get("uid")
                    or endpoint.get("deviceUid")
                    or ""
                ).strip()
                read_hostname = str(
                    endpoint.get("hostname")
                    or endpoint.get("hostName")
                    or endpoint.get("name")
                    or ""
                ).strip()
                if read_uid != endpoint_uid:
                    raise OperationalAutonomyError(
                        "same-company configuration Datto identity readback mismatch"
                    )
                if read_hostname.casefold() != structured_hostname.casefold():
                    raise OperationalAutonomyError(
                        "same-company configuration and Datto hostname do not match"
                    )
                return self._write_verified_ci_association(
                    candidate=candidate, scope=scope, ci_id=ci_id
                )
            # Zero or multiple same-company exact-title CIs are not guessed.
            # Continue into multi-signal endpoint correlation, which still must
            # produce one uniquely winning endpoint and one exact same-company CI.

        material = " ".join(
            (
                str(candidate.context.get("title") or ""),
                str(candidate.context.get("description") or ""),
            )
        )
        hints: list[str] = []
        if structured_hostname:
            hints.append(structured_hostname)
        for token in re.findall(r"\b[A-Za-z0-9][A-Za-z0-9._-]{2,62}\b", material):
            if not any(ch.isalpha() for ch in token) or not any(ch.isdigit() for ch in token):
                continue
            normalized = token.casefold()
            if normalized not in {item.casefold() for item in hints}:
                hints.append(token)
            if len(hints) >= 8:
                break
        if not hints:
            raise OperationalAutonomyError(
                "configuration item id is missing and ticket contains no bounded hostname hint"
            )

        endpoint_matches: dict[str, Mapping[str, Any]] = {}
        for hint in hints:
            data = self._read_data("endpoint.device.search", {"hostname": hint})
            raw = data.get("resource_matches") or data.get("records") or data.get("items") or ()
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
                continue
            exact = [
                item for item in raw
                if isinstance(item, Mapping)
                and str(item.get("hostname") or item.get("hostName") or item.get("name") or "").casefold()
                == hint.casefold()
                and str(item.get("resource_id") or item.get("uid") or item.get("deviceUid") or "").strip()
            ]
            for item in exact:
                endpoint_matches[
                    str(item.get("resource_id") or item.get("uid") or item.get("deviceUid"))
                ] = item
        if not endpoint_matches:
            raise OperationalAutonomyError(
                "configuration item id is missing and endpoint hostname correlation found no exact endpoint"
            )
        if len(endpoint_matches) == 1:
            endpoint_uid, endpoint = next(iter(endpoint_matches.items()))
        else:
            evidence = self._ticket_identity_evidence(candidate)
            scored: list[tuple[int, str, Mapping[str, Any], tuple[str, ...]]] = []
            for uid, item in endpoint_matches.items():
                score, matched, conflicts = self._endpoint_identity_score(
                    item, hints=hints, evidence=evidence
                )
                if conflicts:
                    continue
                scored.append((score, uid, item, matched))
            scored.sort(key=lambda value: (-value[0], value[1]))
            if not scored or scored[0][0] < 2:
                raise OperationalAutonomyError(
                    "configuration item id is missing and endpoint correlation lacks two independent matching identifiers"
                )
            if len(scored) > 1 and scored[1][0] == scored[0][0]:
                raise OperationalAutonomyError(
                    "configuration item id is missing and endpoint correlation remains ambiguous after multi-signal scoring"
                )
            _, endpoint_uid, endpoint, _ = scored[0]
        hostname = str(
            endpoint.get("hostname") or endpoint.get("hostName") or endpoint.get("name") or ""
        ).strip()

        data = self._read_data(
            "service.configuration.search",
            {"company_id": company_id, "name": hostname, "page_size": 25},
        )
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            raise OperationalAutonomyError("configuration search returned invalid items")
        matches = [
            item for item in raw_items
            if isinstance(item, Mapping)
            and item.get("isActive") is True
            and self._company_id(item.get("companyID")) == company_id
            and str(item.get("referenceNumber") or "").strip() == endpoint_uid
            and str(item.get("referenceTitle") or "").strip().casefold() == hostname.casefold()
        ]
        if len(matches) != 1:
            raise OperationalAutonomyError(
                "exact endpoint did not resolve to one active same-company configuration item"
            )
        ci_id = self._positive_int(matches[0].get("id"), "configuration item id")
        output = self.actions.execute(
            scope,
            "service.ticket.update",
            {"payload": {"id": int(candidate.resource_id), "configurationItemID": ci_id}},
        )
        verification = self._action_data(output).get("jasonVerification")
        fields = verification.get("verifiedFields") if isinstance(verification, Mapping) else None
        if not (
            isinstance(verification, Mapping)
            and verification.get("readbackVerified") is True
            and isinstance(fields, Sequence)
            and not isinstance(fields, (str, bytes))
            and "configurationItemID" in {str(value) for value in fields}
        ):
            raise OperationalAutonomyError(
                "device association write was not verified by provider readback"
            )
        return ci_id

    def _admit(self, candidate, scope: PlaybookScope) -> OperationalWork:
        ticket = candidate.context
        ticket_id = self._positive_int(ticket.get("id"), "ticket id")
        company_id = self._company_id(ticket.get("companyID"))
        ci_value = ticket.get("configurationItemID")
        recovered_backupiq_identity = None
        if (
            scope.playbook_id == BACKUPIQ_SCOPE.playbook_id
            and company_id == 0
            and ci_value in (None, "", 0, "0")
        ):
            recovered_backupiq_identity = self._associate_backupiq_unassigned_ticket_device(
                candidate=candidate, scope=scope
            )
        if recovered_backupiq_identity is not None:
            ci_id, company_id = recovered_backupiq_identity
        elif ci_value in (None, "", 0, "0"):
            ci_id = self._associate_exact_ticket_device(
                candidate=candidate,
                scope=scope,
                company_id=company_id,
            )
        else:
            ci_id = self._positive_int(ci_value, "configuration item id")

        ci = self._read_data(
            "service.configuration.read", {"resource_id": ci_id}
        )
        if "item" in ci and isinstance(ci["item"], Mapping):
            ci = dict(ci["item"])
        if int(ci.get("id") or 0) != ci_id:
            raise OperationalAutonomyError("configuration identity readback mismatch")
        if self._company_id(ci.get("companyID")) != company_id:
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

        work = OperationalWork(
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
            source_version=(str(candidate.source_version or "").strip() or None),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        offline_wait_scopes = {
            BACKUPIQ_SCOPE.playbook_id,
            IDLE_LOG_OFF_SCOPE.playbook_id,
        }
        if (
            endpoint.get("online") is not True
            and scope.playbook_id not in offline_wait_scopes
        ):
            deb = self._deb_asset_selection(
                company_id=company_id,
                hostname=hostname,
            )
            if deb.state is DebAvailabilityState.ONLINE:
                reason = "DRMM access unavailable while DEB reports endpoint online"
            elif deb.state is DebAvailabilityState.OFFLINE:
                reason = "endpoint is not currently online (DEB corroborated)"
            else:
                reason = "endpoint is not currently online (DEB unconfirmed)"
            raise DeviceAccessDeferred(work=work, reason=reason)

        return work

    def _advance(self, work: OperationalWork, ticket: Mapping[str, Any]) -> None:
        scope = self._scope_for_work(work)
        if not self._scope_is_promoted(scope):
            self._block(work, "Durable playbook promotion is no longer active.")
            return

        if work.phase == "claim":
            claim_output = self.actions.execute(
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
            claim_data = self._action_data(claim_output)
            verification = claim_data.get("jasonVerification")
            verified_fields = (
                verification.get("verifiedFields")
                if isinstance(verification, Mapping)
                else None
            )
            verified_field_set = (
                {str(value) for value in verified_fields}
                if isinstance(verified_fields, Sequence)
                and not isinstance(verified_fields, (str, bytes))
                else set()
            )
            if not (
                isinstance(verification, Mapping)
                and verification.get("readbackVerified") is True
                and {"queueID", "status"}.issubset(verified_field_set)
            ):
                raise OperationalAutonomyError(
                    "Jason queue claim readback did not verify queueID and status"
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
            if work.phase == "backupiq_reinstall_dispatch":
                self._dispatch_component(
                    work,
                    BACKUPIQ_INSTALLER_NAME,
                    "backupiq_reinstall_wait",
                )
                return
            if work.phase == "backupiq_reinstall_wait":
                self._poll_backupiq_reinstall(work)
                return
            if work.phase == "backupiq_verify_reinstall":
                self._verify_backupiq_reinstall(work)
                return

        if work.playbook_id == LOW_DISK_SCOPE.playbook_id:
            if work.phase == "low_disk_investigate":
                self._investigate_low_disk(work)
                return
            if work.phase == "low_disk_sysmon_cleanup_dispatch":
                self._dispatch_component(
                    work,
                    LOW_DISK_SYSMON_CLEANUP_NAME,
                    "low_disk_cleanup_wait",
                )
                return
            if work.phase == "low_disk_cleanup_wait":
                self._poll_low_disk_cleanup(work)
                return
            if work.phase == "low_disk_verify":
                self._verify_low_disk_cleanup(work)
                return

        if work.playbook_id == VULSCAN_SCOPE.playbook_id:
            if work.phase in {"vulscan_investigate", "vulscan_monitoring"}:
                self._investigate_vulscan(work, ticket)
                return
            if work.phase == "vulscan_client_notification_verify_complete":
                self._verify_vulscan_client_notification(work, continue_monitoring=False)
                return
            if work.phase == "vulscan_client_notification_verify_monitoring":
                self._verify_vulscan_client_notification(work, continue_monitoring=True)
                return

        if work.playbook_id == DISK_BAD_BLOCK_SCOPE.playbook_id:
            if work.phase == "disk_bad_block_investigate":
                self._investigate_disk_bad_block(work)
                return

        if work.playbook_id == IDLE_LOG_OFF_SCOPE.playbook_id:
            if work.phase == "idle_log_off_investigate":
                self._investigate_idle_log_off(work)
                return
            if work.phase == "idle_log_off_repair_dispatch":
                self._dispatch_component(
                    work,
                    IDLE_LOG_OFF_SETTER_NAME,
                    "idle_log_off_repair_wait",
                )
                return
            if work.phase == "idle_log_off_repair_wait":
                self._poll_idle_log_off_repair(work)
                return
            if work.phase == "idle_log_off_verify_monitor":
                self._verify_idle_log_off_monitor(work)
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
        elif component_name == IDLE_LOG_OFF_SETTER_NAME:
            component_uid = IDLE_LOG_OFF_SETTER_UID
            resolved_component_name = IDLE_LOG_OFF_SETTER_NAME
            step = "idle_log_off_repair"
        elif component_name == BACKUPIQ_INSTALLER_NAME:
            component_uid = BACKUPIQ_INSTALLER_UID
            resolved_component_name = BACKUPIQ_INSTALLER_NAME
            step = "backupiq_reinstall"
        elif component_name == LOW_DISK_SYSMON_CLEANUP_NAME:
            component_uid = LOW_DISK_SYSMON_CLEANUP_UID
            resolved_component_name = LOW_DISK_SYSMON_CLEANUP_NAME
            step = "low_disk_cleanup"
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
        if step == "backupiq_reinstall" and work.repair_attempts >= 1:
            raise OperationalAutonomyError(
                "BackupIQ autonomous reinstall limit is one per incident cycle"
            )
        if step == "low_disk_cleanup" and work.repair_attempts >= 1:
            raise OperationalAutonomyError(
                "Low Disk autonomous cleanup limit is one per incident cycle"
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
            1
            if step in {
                "repair",
                "security_repair",
                "idle_log_off_repair",
                "backupiq_reinstall",
                "low_disk_cleanup",
            }
            else 0
        )
        last_reason = f"Dispatched {resolved_component_name}."
        if step == "backupiq_reinstall":
            started_at = datetime.now(timezone.utc).isoformat()
            last_reason = (
                f"backupiq_reinstall_started_at={started_at}; "
                f"Dispatched {resolved_component_name}."
            )
        self.store.put(
            self._replace(
                work,
                phase=next_phase,
                job_uid=job_uid,
                component_uid=component_uid,
                repair_attempts=repair_attempts,
                last_reason=last_reason,
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
        if (
            endpoint_uid != work.device_uid
            or endpoint_hostname.casefold() != work.hostname.casefold()
        ):
            self._block(work, "Idle Log Off device identity changed during execution.")
            return

        role = endpoint.get("device_type")
        role_text = (
            json.dumps(role, sort_keys=True, default=str)
            if isinstance(role, (Mapping, list))
            else str(role or "")
        )
        role_material = (
            f"{role_text} "
            f"{endpoint.get('operating_system') or endpoint.get('operatingSystem') or ''}"
        ).casefold()
        protected = any(
            token in role_material
            for token in (
                "server",
                "domain controller",
                "rds",
                "terminal server",
                "kiosk",
            )
        )
        supported_workstation = (
            "windows" in role_material
            and any(
                token in role_material
                for token in ("desktop", "laptop", "notebook", "workstation")
            )
        )

        if endpoint.get("online") is False:
            access_state, deb = self._device_access_state(work, endpoint=endpoint)
            self.actions.execute(
                self._scope_for_work(work),
                "service.ticket.update",
                {
                    "payload": {
                        "id": work.ticket_id,
                        "status": "Waiting Device Access",
                    }
                },
            )
            if access_state == "deb_online_drmm_offline":
                self._document_deb_drmm_conflict(work, deb)
                status_text = (
                    f"{work.hostname} is independently online in DEB, but DRMM "
                    "management access is currently unavailable."
                )
            elif access_state == "offline_corroborated":
                status_text = (
                    f"{work.hostname} is reported offline by both DRMM and DEB."
                )
            else:
                status_text = (
                    f"{work.hostname} is offline in DRMM; DEB could not independently "
                    "confirm the endpoint state."
                )
            note = (
                "STATUS\n"
                + status_text
                + "\n\nNEXT STEP\n"
                "Keep the ticket in the Jason queue and resume "
                "idle_log_off_investigate automatically when the exact DRMM management "
                "path is available.\n\n"
                "KEY EVIDENCE\n"
                f"- Device={work.hostname}\n"
                f"- DRMM UID={work.device_uid}\n"
                "- DRMM online state=No\n"
                f"- DEB state={deb.state.value}\n"
                "- No setter, alert resolution, forced logoff, reboot, policy change, "
                "or generic PowerShell was attempted.\n\n"
                "JASON STATE\n"
                "waiting_device_access:idle_log_off_investigate"
            )
            self._write_note(
                work,
                note,
                "Jason - Idle Log Off - Waiting Device Access",
            )
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_device_access:idle_log_off_investigate",
                    last_reason=self._device_wait_reason(access_state, deb),
                )
            )
            return

        current_data = self._read_data(
            "endpoint.alert.search",
            {"resource_id": work.device_uid, "status": "open"},
        )
        current_items = current_data.get("items")
        if not isinstance(current_items, list):
            current_items = []
        current_idle_alerts = [
            item
            for item in current_items
            if isinstance(item, Mapping)
            and "idle log off"
            in json.dumps(item, sort_keys=True, default=str).casefold()
        ]

        history = self._read_data(
            "endpoint.alert.history.search", {"resource_id": work.device_uid}
        )
        history_items = history.get("alerts")
        if not isinstance(history_items, list):
            history_items = []
        idle_history = [
            item
            for item in history_items
            if isinstance(item, Mapping)
            and (
                "idle log off"
                in json.dumps(item, sort_keys=True, default=str).casefold()
                or (
                    str(item.get("ticketNumber") or "").strip()
                    == work.ticket_number
                    and "compliant: false"
                    in json.dumps(item, sort_keys=True, default=str).casefold()
                )
            )
        ]
        exact_history = next(
            (
                item
                for item in idle_history
                if str(item.get("ticketNumber") or "").strip()
                == work.ticket_number
            ),
            None,
        )
        if exact_history is None and idle_history:
            exact_history = max(
                idle_history,
                key=lambda item: int(item.get("timestamp") or 0),
            )

        diagnostic_material = " ".join(
            (
                json.dumps(
                    current_idle_alerts,
                    sort_keys=True,
                    default=str,
                ),
                (
                    json.dumps(
                        exact_history,
                        sort_keys=True,
                        default=str,
                    )
                    if exact_history is not None
                    else ""
                ),
            )
        ).casefold()
        plumbing_error = any(
            token in diagnostic_material
            for token in (
                "invalid myfiledestination",
                "powershell",
                "runtime mismatch",
                "missing variable",
                "script exception",
            )
        )

        if protected or not supported_workstation:
            classification = "protected_or_exception_role"
            reason = (
                "Idle Log Off diagnostic complete; endpoint role is not an "
                "autonomous workstation/laptop remediation target."
            )
        elif plumbing_error:
            classification = "monitor_execution_failure"
            reason = (
                "Idle Log Off diagnostic identified monitor/plumbing failure; "
                "endpoint noncompliance is not proven."
            )
        elif len(current_idle_alerts) != 1:
            classification = "current_alert_not_exact"
            reason = (
                "Idle Log Off autonomous remediation requires exactly one current "
                "Idle Log Off alert on the exact endpoint."
            )
        else:
            classification = "confirmed_current_noncompliance"
            reason = (
                "Exactly one current Idle Log Off alert is present on a supported "
                "Windows workstation/laptop; the exact playbook-scoped setter branch "
                "is eligible."
            )

        note = (
            "Jason Idle Log Off diagnostic completed using governed endpoint, "
            "current-alert, and alert-history evidence. "
            f"Device={work.hostname}; "
            f"Online={'Yes' if endpoint.get('online') is True else 'No'}; "
            f"DeviceType={role_text[:180] or 'unknown'}; "
            f"ProtectedOrExceptionRole={'Yes' if protected else 'No'}; "
            f"CurrentIdleAlerts={len(current_idle_alerts)}; "
            f"Classification={classification}. "
        )
        if classification == "confirmed_current_noncompliance":
            note += (
                "The exact approved remediation candidate is "
                f"{IDLE_LOG_OFF_SETTER_NAME} ({IDLE_LOG_OFF_SETTER_UID}) using "
                "built-in defaults only. The playbook-scoped branch does not "
                "authorize reboot, forced logoff, policy changes, generic PowerShell, "
                "or another component."
            )
        else:
            note += (
                "Jason did not run the setter, resolve an alert, force a logoff, "
                "change policy, run generic PowerShell, reboot, or perform another "
                "modifying action."
            )
        self._write_note(work, note, "Jason - Idle Log Off - Diagnostic")

        if classification == "confirmed_current_noncompliance":
            self.store.put(
                self._replace(
                    work,
                    phase="idle_log_off_repair_dispatch",
                    last_reason=reason,
                )
            )
            return

        self._persist_human_review_escalation(work, reason=reason)

    def _poll_idle_log_off_repair(self, work: OperationalWork) -> None:
        if not work.job_uid or work.component_uid != IDLE_LOG_OFF_SETTER_UID:
            self._block(
                work,
                "Persisted Idle Log Off remediation job identity is incomplete or changed.",
            )
            return

        job_data = self._read_data(
            "automation.job.read", {"resource_id": work.job_uid}
        )
        job = (
            job_data.get("job")
            if isinstance(job_data.get("job"), Mapping)
            else job_data
        )
        status = str(job.get("status") or "").strip().casefold()
        if status in {"active", "running", "queued", "pending", "scheduled"}:
            return
        if status in {"stale_or_unknown", "unknown"}:
            self._block(
                work,
                "Idle Log Off setter job state became stale or unknown; "
                "no duplicate dispatch is allowed.",
            )
            return
        if status not in {
            "completed",
            "complete",
            "success",
            "succeeded",
            "finished",
        }:
            self._escalate(
                work,
                "Idle Log Off setter job ended with provider status "
                f"{status or 'unknown'}; no automatic redispatch was attempted.",
            )
            return

        stdout_data = self._read_data(
            "automation.job.output.read",
            {
                "resource_id": work.job_uid,
                "device_uid": work.device_uid,
                "component_uid": work.component_uid,
                "stream": "stdout",
            },
        )
        stderr_data = self._read_data(
            "automation.job.output.read",
            {
                "resource_id": work.job_uid,
                "device_uid": work.device_uid,
                "component_uid": work.component_uid,
                "stream": "stderr",
            },
        )
        stdout_text = self._output_text(stdout_data)
        stderr_text = self._output_text(stderr_data)
        if stderr_text.strip():
            self._escalate(
                work,
                "Idle Log Off setter returned provider success but non-empty stderr; "
                "monitor verification was not treated as resolved.",
            )
            return

        summary = self._bounded_health_summary(stdout_text)
        self._write_note(
            work,
            (
                "Jason ran the exact playbook-scoped Idle Log Off setter using built-in "
                f"defaults on {work.hostname}. Job={work.job_uid}; "
                f"ProviderStatus={status}; Output={summary}. "
                "No reboot, immediate forced logoff, policy change, generic PowerShell, "
                "or unrelated component was used. Action success is not resolution; "
                "Jason is waiting for the normal Idle Log Off monitor to clear."
            ),
            "Jason - Idle Log Off - Remediation",
        )
        self.store.put(
            self._replace(
                work,
                phase="waiting_recheck:idle_log_off_verify_monitor",
                job_uid=None,
                component_uid=None,
                last_reason=(
                    "Idle Log Off setter completed; waiting for the authoritative "
                    "normal monitor cycle to clear the exact alert."
                ),
            )
        )

    def _verify_idle_log_off_monitor(self, work: OperationalWork) -> None:
        current_data = self._read_data(
            "endpoint.alert.search",
            {"resource_id": work.device_uid, "status": "open"},
        )
        current_items = current_data.get("items")
        if not isinstance(current_items, list):
            current_items = []
        current_idle_alerts = [
            item
            for item in current_items
            if isinstance(item, Mapping)
            and "idle log off"
            in json.dumps(item, sort_keys=True, default=str).casefold()
        ]

        if not current_idle_alerts:
            self._write_note(
                work,
                (
                    "Jason verified the normal DRMM Idle Log Off alert is no longer "
                    f"open for {work.hostname} after the playbook-scoped setter. "
                    "This authoritative monitor-clear evidence completes the remediation "
                    "verification. No reboot or forced logoff was used."
                ),
                "Jason - Idle Log Off - Verification",
            )
            self._complete_verified_ticket(
                work,
                reason=(
                    "Idle Log Off remediation completed and the authoritative current "
                    "DRMM alert cleared; ticket completion readback succeeded."
                ),
            )
            return

        waiting_since = self._parse_iso_timestamp(work.updated_at)
        age_seconds = (
            (datetime.now(timezone.utc) - waiting_since).total_seconds()
            if waiting_since is not None
            else 0
        )
        if age_seconds < 900:
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_recheck:idle_log_off_verify_monitor",
                    last_reason=(
                        "Idle Log Off alert remains open inside the bounded monitor "
                        "propagation window; waiting without redispatch."
                    ),
                    updated_at=work.updated_at,
                )
            )
            return

        self._write_note(
            work,
            (
                "Jason's exact Idle Log Off setter completed, but a current Idle Log Off "
                "alert remains after the 15-minute monitor propagation window. "
                "Jason did not rerun the setter, force a logoff, reboot, or change policy. "
                "Monitor/policy investigation is required."
            ),
            "Jason - Idle Log Off - Verification",
        )
        self._persist_human_review_escalation(
            work,
            reason=(
                "Current Idle Log Off alert remained after successful setter execution "
                "and bounded monitor propagation; monitor/policy review is required."
            ),
            clear_job=True,
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
        self._persist_human_review_escalation(
            work,
            reason=(
                "Disk Event ID 7 diagnostic complete; authoritative physical-disk "
                "mapping remains component/technician gated."
            ),
        )

    @staticmethod
    def _notification_history_items(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        items = data.get("items")
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            return []
        return [item for item in items if isinstance(item, Mapping)]

    def _notification_history_max_id(self, ticket_id: int) -> int:
        data = self._read_data(
            "service.notification.history.search",
            {"ticket_id": int(ticket_id), "page_size": 100},
        )
        ids: list[int] = []
        for item in self._notification_history_items(data):
            try:
                ids.append(int(item.get("id")))
            except (TypeError, ValueError):
                continue
        return max(ids, default=0)

    def _gromelski_notification_copy_observed(
        self,
        *,
        ticket_id: int,
        baseline_id: int,
    ) -> bool:
        data = self._read_data(
            "service.notification.history.search",
            {"ticket_id": int(ticket_id), "page_size": 100},
        )
        for item in self._notification_history_items(data):
            try:
                item_id = int(item.get("id"))
                item_ticket_id = int(item.get("ticketID"))
            except (TypeError, ValueError):
                continue
            if item_id <= int(baseline_id) or item_ticket_id != int(ticket_id):
                continue
            if (
                str(item.get("recipientEmailAddress") or "").strip().casefold()
                == "chris.benton@e-gai.com"
            ):
                return True
        return False

    @staticmethod
    def _notification_baseline_from_reason(reason: str) -> int:
        match = re.search(r"notification_baseline_id=(\\d+)", str(reason or ""))
        if match is None:
            raise OperationalAutonomyError(
                "client-notification verification has no durable baseline"
            )
        return int(match.group(1))

    def _verify_vulscan_client_notification(
        self,
        work: OperationalWork,
        *,
        continue_monitoring: bool,
    ) -> None:
        baseline_id = self._notification_baseline_from_reason(work.last_reason)
        if not self._gromelski_notification_copy_observed(
            ticket_id=work.ticket_id,
            baseline_id=baseline_id,
        ):
            return
        self.store.put(
            self._replace(
                work,
                phase="vulscan_monitoring" if continue_monitoring else "complete",
                last_reason=(
                    "Client-facing VulScan notification copy verified in "
                    "Autotask Notification History."
                ),
            )
        )

    def _apply_vulscan_client_disposition(
        self,
        work: OperationalWork,
        ticket: Mapping[str, Any],
        *,
        continue_monitoring: bool,
    ) -> bool:
        policy = resolve_vulscan_policy(
            client_id=work.company_id,
            site_id=ticket.get("companyLocationID"),
            device_id=work.device_uid,
            user_id=ticket.get("contactID"),
            ticket_id=work.ticket_id,
        )
        if not policy.client_notification_required:
            return False
        if policy.primary_contact_id is None:
            raise OperationalAutonomyError(
                "client-specific VulScan policy requires a primary contact"
            )

        if not self._scope_is_promoted(VULSCAN_CLIENT_DISPOSITION_SCOPE):
            self._write_note(
                work,
                (
                    "STATUS: WAITING - CLIENT NOTIFICATION AUTHORITY. "
                    "NEXT STEP: Jason will resume automatically when the exact "
                    "VulScan v1.1.0 client-disposition scope is durably promoted. "
                    "The patch classification is preserved. "
                    "CHANGES MADE: No client contact change, client notification, "
                    "or Close Pending transition was attempted."
                ),
                "Jason - VulScan - Waiting Client Notification Authority",
            )
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_client_notification_authority",
                    last_reason=(
                        "VulScan client disposition is waiting for exact v1.1.0 "
                        "durable promotion; no client communication or Close Pending "
                        "transition was attempted."
                    ),
                )
            )
            return True

        scope = VULSCAN_CLIENT_DISPOSITION_SCOPE
        desired_contact = int(policy.primary_contact_id)

        if int(ticket.get("contactID") or 0) != desired_contact:
            contact_update = self.actions.execute(
                scope,
                "service.ticket.update",
                {
                    "payload": {
                        "id": work.ticket_id,
                        "contactID": desired_contact,
                    }
                },
            )
            contact_data = self._action_data(contact_update)
            verification = contact_data.get("jasonVerification")
            verified_fields = (
                verification.get("verifiedFields")
                if isinstance(verification, Mapping)
                else None
            )
            if (
                not isinstance(verification, Mapping)
                or verification.get("readbackVerified") is not True
                or not isinstance(verified_fields, Sequence)
                or isinstance(verified_fields, (str, bytes))
                or "contactID" not in {str(value) for value in verified_fields}
            ):
                raise OperationalAutonomyError(
                    "VulScan primary-contact association failed readback"
                )

        template = resolve_approved_client_message(
            workflow_id=work.playbook_id,
            template_id=str(policy.client_notification_template_id or ""),
        )
        note_key = f"Client - Approved Communication - {template.template_id}"
        note_fingerprint = template.fingerprint
        prior = self.store.last_note_fingerprint(
            work.ticket_id,
            work.playbook_id,
            note_key,
        )

        baseline_id = self._notification_history_max_id(work.ticket_id)
        if prior != note_fingerprint:
            self.actions.execute(
                scope,
                "service.ticket.client.notification.create",
                {
                    "workflow_id": template.workflow_id,
                    "template_id": template.template_id,
                    "payload": {
                        "ticketID": int(work.ticket_id),
                    },
                },
            )
            self.store.remember_note_fingerprint(
                work.ticket_id,
                work.playbook_id,
                note_key,
                note_fingerprint,
            )

        status_update = self.actions.execute(
            scope,
            "service.ticket.update",
            {
                "payload": {
                    "id": work.ticket_id,
                    "contactID": desired_contact,
                    "status": policy.terminal_status,
                }
            },
        )
        status_data = self._action_data(status_update)
        verification = status_data.get("jasonVerification")
        verified_fields = (
            verification.get("verifiedFields")
            if isinstance(verification, Mapping)
            else None
        )
        if (
            not isinstance(verification, Mapping)
            or verification.get("readbackVerified") is not True
            or not isinstance(verified_fields, Sequence)
            or isinstance(verified_fields, (str, bytes))
            or not {"contactID", "status"}.issubset(
                {str(value) for value in verified_fields}
            )
        ):
            raise OperationalAutonomyError(
                "VulScan Close Pending/contact readback verification failed"
            )

        if prior == note_fingerprint:
            self.store.put(
                self._replace(
                    work,
                    phase="vulscan_monitoring" if continue_monitoring else "complete",
                    last_reason="Approved client VulScan communication already present.",
                )
            )
            return True

        if self._gromelski_notification_copy_observed(
            ticket_id=work.ticket_id,
            baseline_id=baseline_id,
        ):
            self.store.put(
                self._replace(
                    work,
                    phase="vulscan_monitoring" if continue_monitoring else "complete",
                    last_reason=(
                        "Close Pending, primary contact, canned note, and client "
                        "notification copy verified."
                    ),
                )
            )
            return True

        self.store.put(
            self._replace(
                work,
                phase=(
                    "vulscan_client_notification_verify_monitoring"
                    if continue_monitoring
                    else "vulscan_client_notification_verify_complete"
                ),
                last_reason=f"notification_baseline_id={baseline_id}",
            )
        )
        return True

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
            first_seen = self._vulscan_first_not_approved_at(work)
            now = datetime.now(timezone.utc)
            if first_seen is None:
                first_seen = now
            age_seconds = max(0.0, (now - first_seen).total_seconds())
            if age_seconds >= VULSCAN_APPROVAL_ESCALATION_SECONDS:
                note = (
                    "STATUS: HUMAN REVIEW REQUIRED. "
                    "ACTION REQUIRED: Approve or intentionally defer the listed patch(es). "
                    "WHY: One or more exact VulScan KBs have remained NOT_APPROVED for at least "
                    "10 calendar days. "
                    f"Device={work.hostname}; PatchStates={patch_summary}. "
                    "No patch approval, forced installation, Windows Update repair, WSUS-policy "
                    "change, reboot scheduling, reboot, or other modifying action was attempted."
                )
                self._write_note(
                    work,
                    note,
                    "Jason - VulScan - Human Review Required",
                )
                self._handoff_vulscan_approval_review(work)
                self.store.put(
                    self._replace(
                        work,
                        phase="escalated",
                        last_reason=(
                            "VulScan patch approval remained NOT_APPROVED for 10 days; "
                            "technician approve/defer decision required."
                        ),
                    )
                )
                return
            note += (
                "At least one reported KB is currently NOT_APPROVED. "
                "STATUS: WAITING - PATCH NOT APPROVED. "
                "NEXT STEP: No technician action is required yet; Jason will recheck the exact "
                "KB approval state daily and keep this ticket in the Jason queue. "
                "ESCALATION: If the same exact KB remains NOT_APPROVED for 10 calendar days, "
                "Jason will move the ticket to Help Desk I / Human Review for an approve-or-defer "
                "decision. The playbook will not approve patches autonomously."
            )
            reason = (
                "VulScan waiting for patch approval; "
                f"first_not_approved_at={first_seen.isoformat()}; "
                "one or more exact KBs remain NOT_APPROVED."
            )
        elif classification == "stale_or_recovered_finding":
            # Current endpoint reboot state is authoritative. Patch-level
            # rebootRequired is update metadata, not proof that the endpoint
            # still has a pending reboot after installation.
            reboot_gated = bool(endpoint.get("reboot_required"))
            if not reboot_gated:
                note += (
                    "All exact reported KBs are installed and no reboot is required. "
                    "This is a verified stale/recovered VulScan finding; Jason may close "
                    "the ticket without patching, rebooting, or other endpoint mutation."
                )
                self._write_note(work, note, "Jason - Autonomous VulScan Resolution")
                if self._apply_vulscan_client_disposition(
                    work,
                    ticket,
                    continue_monitoring=False,
                ):
                    self._notify_patch_completion(
                        work,
                        patch_summary=patch_summary,
                    )
                    return
                self._complete_verified_ticket(
                    work,
                    reason="All exact VulScan KBs verified installed with no reboot required.",
                )
                self._notify_patch_completion(
                    work,
                    patch_summary=patch_summary,
                )
                return
            note += (
                "All exact reported KBs are installed, but a reboot requirement is present. "
                "Ticket completion remains gated because Jason has no autonomous reboot authority."
            )
            reason = "VulScan diagnostic complete; reported KBs installed but reboot remains required."
        elif classification == "approved_pending":
            note += (
                "STATUS: WAITING - PATCH APPROVED/PENDING. "
                "NEXT STEP: Jason will keep the ticket in the Jason queue and recheck after the "
                "normal patch-processing window. No forced installation or reboot is authorized."
            )
            reason = (
                "VulScan waiting for normal patch processing; one or more exact KBs are "
                "APPROVED_PENDING."
            )
            if self._apply_vulscan_client_disposition(
                work,
                ticket,
                continue_monitoring=True,
            ):
                self._write_note(
                    work,
                    note,
                    "Jason - VulScan - Waiting Patch Window",
                )
                return
        else:
            note += (
                "Technician review or a separately accepted Windows Update remediation branch "
                "is required before modifying the endpoint."
            )
            reason = f"VulScan diagnostic classified {classification}; remediation remains gated."

        if classification == "approval_blocked":
            self._write_note(
                work,
                note,
                "Jason - VulScan - Waiting Patch Approval",
            )
            self._update_ticket_status_verified(work, "Waiting Patch Approval")
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_patch_approval",
                    last_reason=reason,
                )
            )
            return
        if classification == "approved_pending":
            self._write_note(
                work,
                note,
                "Jason - VulScan - Waiting Patch Window",
            )
            self._update_ticket_status_verified(work, "On Hold")
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_patch_window",
                    last_reason=reason,
                )
            )
            return

        self._write_note(work, note, "Jason - Autonomous VulScan Diagnostic")
        self._persist_human_review_escalation(work, reason=reason)

    def _low_disk_open_alerts(self, work: OperationalWork) -> list[Mapping[str, Any]]:
        current = self._read_data(
            "endpoint.alert.search",
            {"resource_id": work.device_uid, "status": "open"},
        )
        items = current.get("items")
        if not isinstance(items, list):
            items = current.get("alerts")
        if not isinstance(items, list):
            return []
        return [
            item
            for item in items
            if isinstance(item, Mapping)
            and "low disk"
            in json.dumps(item, sort_keys=True, default=str).casefold()
        ]

    def _low_disk_powershell_records(
        self,
        work: OperationalWork,
        command: str,
        *,
        timeout_seconds: int = 60,
    ) -> list[dict[str, Any]]:
        data = self._read_data(
            "endpoint.powershell.read",
            {
                "device_uid": work.device_uid,
                "command": command,
                "timeout_seconds": timeout_seconds,
            },
        )
        stdout = data.get("stdout") or data.get("text") or ""
        return parse_json_records(stdout)

    def _low_disk_collect_evidence(self, work: OperationalWork) -> dict[str, Any]:
        reads = (
            ("top_folders", TOP_FOLDER_COMMAND, 120),
            ("large_files", LARGE_FILE_COMMAND, 120),
            ("vss", VSS_COMMAND, 60),
            ("system_files", SYSTEM_FILE_COMMAND, 60),
            ("physical_disks", PHYSICAL_DISK_COMMAND, 60),
            ("reliability", RELIABILITY_COMMAND, 60),
            ("sysmon", SYSMON_COMMAND, 60),
            ("sysmon_dependencies", SYSMON_DEPENDENCY_COMMAND, 60),
            ("software_distribution", SOFTWARE_DISTRIBUTION_COMMAND, 90),
        )
        evidence: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for name, command, timeout_seconds in reads:
            try:
                evidence[name] = self._low_disk_powershell_records(
                    work,
                    command,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                evidence[name] = []
                errors[name] = f"{type(exc).__name__}: {str(exc)[:180]}"
        evidence["errors"] = errors
        return evidence

    def _low_disk_prior_ticket_count(self, work: OperationalWork) -> int:
        try:
            data = self._read_data(
                "service.ticket.search",
                {"company_id": work.company_id, "page_size": 100},
            )
        except Exception:
            return 0
        items = data.get("items")
        if not isinstance(items, list):
            items = data.get("tickets")
        if not isinstance(items, list):
            return 0
        hostname = work.hostname.casefold()
        return sum(
            1
            for item in items
            if isinstance(item, Mapping)
            and int(item.get("id") or 0) != work.ticket_id
            and "low disk" in str(item.get("title") or "").casefold()
            and hostname in str(item.get("title") or "").casefold()
        )

    def _low_disk_volume_baseline(
        self,
        work: OperationalWork,
    ) -> tuple[Mapping[str, Any], float, float, float, str]:
        audit = self._read_data(
            "endpoint.audit.read", {"resource_id": work.device_uid}
        )
        logical_disks = audit.get("logicalDisks")
        if logical_disks is None and isinstance(audit.get("audit"), Mapping):
            logical_disks = audit["audit"].get("logicalDisks")
        if not isinstance(logical_disks, list) or not logical_disks:
            raise OperationalAutonomyError(
                "Low-disk endpoint audit contained no logical-disk evidence."
            )
        fixed = [
            disk
            for disk in logical_disks
            if isinstance(disk, Mapping)
            and str(disk.get("description") or "").casefold() == "local fixed disk"
        ]
        candidates = fixed or [
            disk for disk in logical_disks if isinstance(disk, Mapping)
        ]
        disk = min(
            candidates,
            key=lambda item: (
                (numeric(item.get("freespace")) / numeric(item.get("size")))
                if numeric(item.get("size")) > 0
                else 1.0
            ),
        )
        size = numeric(disk.get("size"))
        free = numeric(disk.get("freespace"))
        free_pct = (free / size * 100.0) if size > 0 else 0.0
        drive = str(disk.get("diskIdentifier") or "unknown")
        return disk, size, free, free_pct, drive

    def _low_disk_note(
        self,
        work: OperationalWork,
        *,
        size: float,
        free: float,
        free_pct: float,
        drive: str,
        findings: Sequence[str],
        health_text: str,
        recommendation_text: str,
        prior_count: int,
        action: str,
        changes: str,
        state: str,
    ) -> str:
        lines = [
            "STATUS",
            (
                f"{drive} has {free / (1024**3):.1f} GB free of "
                f"{size / (1024**3):.1f} GB ({free_pct:.1f}% free)."
            ),
            "",
            "NEXT STEP" if changes == "None" else "RESULT / NEXT STEP",
            recommendation_text,
            "",
            "KEY EVIDENCE",
        ]
        lines.extend(f"- {item}" for item in findings[:5])
        if prior_count:
            lines.append(f"- Recurrence: {prior_count} prior low-disk ticket(s) found for this endpoint.")
        if health_text:
            lines.extend(["", "DISK HEALTH", health_text])
        lines.extend(
            [
                "",
                "WHAT JASON DID",
                action,
                "",
                "CHANGES MADE",
                changes,
                "",
                "JASON STATE",
                state,
            ]
        )
        return "\n".join(lines)

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
        if (
            endpoint_uid != work.device_uid
            or endpoint_hostname.casefold() != work.hostname.casefold()
        ):
            self._block(work, "Low-disk device identity changed during execution.")
            return
        if endpoint.get("online") is not True:
            access_state, deb = self._device_access_state(work, endpoint=endpoint)
            self.actions.execute(
                self._scope_for_work(work),
                "service.ticket.update",
                {"payload": {"id": work.ticket_id, "status": "Waiting Device Access"}},
            )
            if access_state == "deb_online_drmm_offline":
                self._document_deb_drmm_conflict(work, deb)
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_device_access:low_disk_investigate",
                    last_reason=self._device_wait_reason(access_state, deb),
                )
            )
            return

        _disk, size, free, free_pct, drive = self._low_disk_volume_baseline(work)
        current_alerts = self._low_disk_open_alerts(work)
        if not current_alerts:
            note = self._low_disk_note(
                work,
                size=size,
                free=free,
                free_pct=free_pct,
                drive=drive,
                findings=[],
                health_text="",
                recommendation_text=(
                    "The current DRMM low-disk monitor is healthy. The existing "
                    "Autotask-triggered cleanup appears to have resolved this incident."
                ),
                prior_count=0,
                action=(
                    "Verified current free space and confirmed the authoritative low-disk "
                    "alert is no longer open."
                ),
                changes="None",
                state="complete",
            )
            self._write_note(work, note, "Jason - Low Disk - Resolution")
            self._complete_verified_ticket(
                work,
                reason=(
                    "Current low-disk monitor cleared after the existing Autotask cleanup "
                    "opportunity; ticket completion readback succeeded."
                ),
            )
            return

        grace_match = re.search(
            r"low_disk_grace_started_at=([^;]+)",
            str(work.last_reason or ""),
        )
        grace_started = (
            self._parse_iso_timestamp(grace_match.group(1).strip())
            if grace_match
            else None
        )
        if grace_started is None:
            grace_started = datetime.now(timezone.utc)
        grace_age = (datetime.now(timezone.utc) - grace_started).total_seconds()
        if grace_age < LOW_DISK_GRACE_SECONDS:
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_recheck:low_disk_investigate",
                    last_reason=(
                        f"low_disk_grace_started_at={grace_started.isoformat()}; "
                        "Waiting for the existing Autotask-triggered Disk Cleanup and "
                        "normal monitor propagation before deeper diagnostics."
                    ),
                )
            )
            return

        role = endpoint.get("device_type")
        role_text = (
            json.dumps(role, sort_keys=True, default=str)
            if isinstance(role, (Mapping, list))
            else str(role or "")
        )
        role_material = (
            f"{role_text} "
            f"{endpoint.get('operating_system') or endpoint.get('operatingSystem') or ''}"
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
        storage_risk_hits = sum(
            1
            for alert in alerts
            if isinstance(alert, Mapping)
            and any(
                token in json.dumps(alert, sort_keys=True, default=str).casefold()
                for token in (
                    '"code":"7"',
                    '"code": "7"',
                    "bad block",
                    "ntfs",
                    "storport",
                    "storage controller",
                    "smart error",
                )
            )
        )

        evidence = self._low_disk_collect_evidence(work)
        health_risk, health_text = storage_health_summary(
            evidence["physical_disks"],
            evidence["reliability"],
            storage_risk_hits,
        )
        safe_sysmon = (
            evidence["sysmon"]
            if "sysmon" not in evidence["errors"]
            else []
        )
        safe_sysmon_dependencies = evidence["sysmon_dependencies"]
        if "sysmon_dependencies" in evidence["errors"]:
            safe_sysmon_dependencies = [{"Name": "dependency evidence unavailable"}]
        safe_software_distribution = (
            evidence["software_distribution"]
            if "software_distribution" not in evidence["errors"]
            else []
        )
        cleanup_kind, cleanup_bytes = choose_cleanup(
            sysmon=safe_sysmon,
            sysmon_dependencies=safe_sysmon_dependencies,
            software_distribution=safe_software_distribution,
            storage_health_risk=health_risk,
        )
        artifacts = artifact_bytes(evidence["large_files"])
        software_review_bytes = sum(
            numeric(item.get("Bytes"))
            for item in safe_software_distribution
            if isinstance(item, Mapping)
        )
        findings = relevant_findings(
            top_folders=evidence["top_folders"],
            large_files=evidence["large_files"],
            vss=evidence["vss"],
            system_files=evidence["system_files"],
            sysmon=evidence["sysmon"],
            software_distribution=evidence["software_distribution"],
        )
        prior_count = self._low_disk_prior_ticket_count(work)
        recommendation_text = recommendation(
            alert_still_open=True,
            storage_health_risk=health_risk,
            cleanup_kind=cleanup_kind if not protected else None,
            cleanup_bytes=cleanup_bytes,
            artifact_bytes=artifacts,
        )
        if (
            not health_risk
            and not protected
            and cleanup_kind is None
            and software_review_bytes >= 1024**3
        ):
            recommendation_text = (
                f"Old SoftwareDistribution backup folders account for about "
                f"{software_review_bytes / (1024**3):.1f} GB. The current cleanup "
                "component is destructive/review-bound, so Jason will not run it "
                "unattended; technician review can approve cleanup if appropriate."
            )
        if evidence["errors"] and not findings:
            recommendation_text = (
                "Root-cause evidence was incomplete and no useful large-consumer result "
                "was returned. Technician review is required rather than guessing."
            )

        if health_risk or protected or (evidence["errors"] and not findings):
            reason = (
                "Storage-health evidence requires technician review."
                if health_risk
                else "Protected/server role requires technician review."
                if protected
                else "Low-disk root-cause evidence was incomplete."
            )
            note = self._low_disk_note(
                work,
                size=size,
                free=free,
                free_pct=free_pct,
                drive=drive,
                findings=findings,
                health_text=health_text,
                recommendation_text=recommendation_text,
                prior_count=prior_count,
                action=(
                    "Allowed the existing Autotask cleanup grace period, then collected "
                    "read-only folder/file, VSS, system-file, SMART/physical-disk, "
                    "reliability, and storage-event evidence."
                ),
                changes="None",
                state="human_review",
            )
            self._write_note(work, note, "Jason - Low Disk - Human Review Required")
            self._persist_human_review_escalation(work, reason=reason)
            return

        if cleanup_kind and work.repair_attempts == 0:
            note = self._low_disk_note(
                work,
                size=size,
                free=free,
                free_pct=free_pct,
                drive=drive,
                findings=findings,
                health_text=health_text,
                recommendation_text=recommendation_text,
                prior_count=prior_count,
                action=(
                    "Allowed the existing Autotask cleanup grace period and performed "
                    "read-only root-cause analysis. One narrow approved cleanup target "
                    "was positively identified."
                ),
                changes="None yet",
                state="remediating",
            )
            self._write_note(work, note, "Jason - Low Disk - Diagnostic")
            phase = "low_disk_sysmon_cleanup_dispatch"
            self.store.put(
                self._replace(
                    work,
                    phase=phase,
                    last_reason=f"Selected approved cleanup target={cleanup_kind}.",
                )
            )
            return

        note = self._low_disk_note(
            work,
            size=size,
            free=free,
            free_pct=free_pct,
            drive=drive,
            findings=findings,
            health_text=health_text,
            recommendation_text=recommendation_text,
            prior_count=prior_count,
            action=(
                "Allowed the existing Autotask cleanup grace period and completed "
                "read-only root-cause analysis. No additional approved autonomous "
                "cleanup target was identified."
            ),
            changes="None",
            state="human_review",
        )
        self._write_note(work, note, "Jason - Low Disk - Human Review Required")
        self._persist_human_review_escalation(
            work,
            reason=(
                "Low-disk condition remains after the Autotask cleanup opportunity and "
                "no further approved autonomous cleanup target applies."
            ),
        )

    def _poll_low_disk_cleanup(self, work: OperationalWork) -> None:
        if not work.job_uid or work.component_uid != LOW_DISK_SYSMON_CLEANUP_UID:
            self._persist_human_review_escalation(
                work,
                reason="Low Disk cleanup job identity is incomplete or changed.",
                clear_job=True,
            )
            return
        job_data = self._read_data(
            "automation.job.read", {"resource_id": work.job_uid}
        )
        job = job_data.get("job") if isinstance(job_data.get("job"), Mapping) else job_data
        status = str(job.get("status") or "").strip().casefold()
        if status in {"active", "running", "queued", "pending", "scheduled"}:
            return
        if status not in {"completed", "complete", "success", "succeeded", "finished"}:
            self._persist_human_review_escalation(
                work,
                reason=(
                    f"Approved Low Disk cleanup ended with provider status "
                    f"{status or 'unknown'}; no second cleanup was attempted."
                ),
                clear_job=True,
            )
            return

        component_name = LOW_DISK_SYSMON_CLEANUP_NAME
        completed_at = datetime.now(timezone.utc)
        self._write_note(
            work,
            (
                "STATUS\nApproved narrow Low Disk cleanup completed.\n\n"
                "NEXT STEP\nJason will independently re-read free space and the current "
                "DRMM low-disk monitor before considering the incident resolved.\n\n"
                f"WHAT JASON DID\nRan {component_name}; Job={work.job_uid}; "
                f"ProviderStatus={status}.\n\n"
                "CHANGES MADE\nOnly the exact approved cleanup target was modified. "
                "No user documents, application data, VSS, hibernation, pagefile, "
                "Recycle Bin, reboot, or service change was performed.\n\n"
                "JASON STATE\nverifying"
            ),
            "Jason - Low Disk - Remediation",
        )
        self.store.put(
            self._replace(
                work,
                phase="waiting_recheck:low_disk_verify",
                job_uid=None,
                component_uid=None,
                last_reason=(
                    f"low_disk_cleanup_completed_at={completed_at.isoformat()}; "
                    f"low_disk_cleanup_component={component_name}; "
                    "Waiting for free-space and monitor verification."
                ),
            )
        )

    def _verify_low_disk_cleanup(self, work: OperationalWork) -> None:
        match = re.search(
            r"low_disk_cleanup_completed_at=([^;]+)",
            str(work.last_reason or ""),
        )
        completed_at = (
            self._parse_iso_timestamp(match.group(1).strip())
            if match
            else None
        )
        if completed_at is None:
            self._persist_human_review_escalation(
                work,
                reason="Low Disk cleanup verification timestamp is missing.",
            )
            return
        _disk, size, free, free_pct, drive = self._low_disk_volume_baseline(work)
        alerts = self._low_disk_open_alerts(work)
        if not alerts:
            note = self._low_disk_note(
                work,
                size=size,
                free=free,
                free_pct=free_pct,
                drive=drive,
                findings=[],
                health_text="",
                recommendation_text=(
                    "The authoritative DRMM low-disk monitor is healthy after the one "
                    "approved cleanup. No additional cleanup or capacity action is required "
                    "from this incident."
                ),
                prior_count=0,
                action=(
                    "Re-read free space and independently verified the current DRMM "
                    "low-disk alert is no longer open."
                ),
                changes="One approved narrow cleanup completed.",
                state="complete",
            )
            self._write_note(work, note, "Jason - Low Disk - Verification")
            self._complete_verified_ticket(
                work,
                reason=(
                    "One approved Low Disk cleanup completed and the authoritative "
                    "current monitor cleared; ticket completion readback succeeded."
                ),
            )
            return

        age = (datetime.now(timezone.utc) - completed_at).total_seconds()
        if age < LOW_DISK_GRACE_SECONDS:
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_recheck:low_disk_verify",
                    last_reason=work.last_reason,
                    updated_at=work.updated_at,
                )
            )
            return

        evidence = self._low_disk_collect_evidence(work)
        health_risk, health_text = storage_health_summary(
            evidence["physical_disks"],
            evidence["reliability"],
            0,
        )
        findings = relevant_findings(
            top_folders=evidence["top_folders"],
            large_files=evidence["large_files"],
            vss=evidence["vss"],
            system_files=evidence["system_files"],
            sysmon=evidence["sysmon"],
            software_distribution=evidence["software_distribution"],
        )
        recommendation_text = recommendation(
            alert_still_open=True,
            storage_health_risk=health_risk,
            cleanup_kind=None,
            cleanup_bytes=0,
            artifact_bytes=artifact_bytes(evidence["large_files"]),
        )
        note = self._low_disk_note(
            work,
            size=size,
            free=free,
            free_pct=free_pct,
            drive=drive,
            findings=findings,
            health_text=health_text,
            recommendation_text=recommendation_text,
            prior_count=self._low_disk_prior_ticket_count(work),
            action=(
                "Verified the one approved cleanup completed, re-read free space, and "
                "re-ran read-only root-cause evidence after the monitor propagation window."
            ),
            changes="One approved narrow cleanup completed; no second cleanup attempted.",
            state="human_review",
        )
        self._write_note(work, note, "Jason - Low Disk - Human Review Required")
        self._persist_human_review_escalation(
            work,
            reason=(
                "Low-disk monitor remained open after the one approved cleanup and "
                "bounded propagation window; technician review/capacity planning required."
            ),
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

    @staticmethod
    def _backupiq_timestamp_from_reason(
        work: OperationalWork,
        key: str,
    ) -> datetime | None:
        match = re.search(
            rf"(?:^|;)\s*{re.escape(key)}=([^;]+)",
            str(work.last_reason or ""),
        )
        if match is None:
            return None
        return OperationalAutonomyMaintenance._parse_iso_timestamp(
            match.group(1).strip()
        )

    def _backupiq_exact_asset(
        self,
        work: OperationalWork,
    ) -> Mapping[str, Any] | None:
        selection = self._deb_asset_selection(
            company_id=work.company_id,
            hostname=work.hostname,
        )
        return (
            dict(selection.asset)
            if isinstance(selection.asset, Mapping)
            and selection.state
            not in {
                DebAvailabilityState.AMBIGUOUS,
                DebAvailabilityState.NOT_FOUND,
                DebAvailabilityState.UNAVAILABLE,
            }
            else None
        )

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

        asset_selection = self._deb_asset_selection(
            company_id=work.company_id,
            hostname=work.hostname,
        )
        asset = asset_selection.asset
        if not isinstance(asset, Mapping):
            classification = (
                "asset_identity_or_lifecycle_issue"
                if asset_selection.state is DebAvailabilityState.NOT_FOUND
                else "duplicate_or_ambiguous_provider_asset"
                if asset_selection.state is DebAvailabilityState.AMBIGUOUS
                else "provider_asset_evidence_unavailable"
            )
            self._write_note(
                work,
                (
                    "Jason autonomous BackupIQ diagnostic stopped before remediation. "
                    f"Device={work.hostname}; ExactProviderAssetMatches="
                    f"{asset_selection.exact_match_count}; "
                    f"Classification={classification}; "
                    f"SelectionReason={asset_selection.reason}. Exact DRMM/provider asset "
                    "identity was not safely established. No reinstall, clean install, "
                    "policy change, backup deletion, retention change, or other modifying "
                    "backup action was attempted."
                ),
                "Jason - BackupIQ - Asset Validation",
            )
            self._persist_human_review_escalation(
                work,
                reason=(
                    "BackupIQ provider asset identity was not safely established; "
                    "technician review required."
                ),
            )
            return

        provider_status = str(asset.get("status") or "").strip().casefold()
        provider_online = provider_status == "online"
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
        elif not endpoint_online and not provider_online:
            classification = "true_offline_both_sources"
        elif not endpoint_online and provider_online:
            classification = "drmm_only_offline_conflict"
        elif endpoint_online and not provider_online:
            classification = "backup_agent_connectivity_failure"
        elif recovered_after_ticket and not alert_items:
            classification = "stale_or_recovered_alert"
        elif recovered_after_ticket:
            classification = "persistent_backupiq_condition_after_success"
        elif endpoint_online and provider_online:
            classification = "backup_failure_or_stale_success"
        else:
            classification = "provider_endpoint_state_conflict"

        note = (
            "Jason autonomous BackupIQ diagnostic completed using governed DRMM and "
            "Backup.net/UniView evidence. "
            f"Device={work.hostname}; DRMMOnline={'Yes' if endpoint_online else 'No'}; "
            f"ProviderAssetId={str(asset.get('id') or '')[:80] or 'unknown'}; "
            f"ProviderStatus={provider_status or 'unknown'}; "
            f"BackupEnabled={'Yes' if backup_enabled else 'No'}; "
            f"LastSuccessfulBackup={last_success.isoformat() if last_success else 'unknown'}; "
            f"LastProviderOnline={last_online.isoformat() if last_online else 'unknown'}; "
            f"CurrentBackupIQAlerts={len(alert_items)}; "
            f"Classification={classification}. "
        )

        if classification == "true_offline_both_sources":
            note += (
                "Both DRMM and Backup.net independently report the endpoint offline. "
                "This is the playbook's true-offline condition. No reinstall was attempted; "
                "Jason will retain ownership, release the active-work slot, and resume "
                "when the exact endpoint is available again."
            )
            self._write_note(work, note, "Jason - BackupIQ - Diagnostic")
            self.actions.execute(
                self._scope_for_work(work),
                "service.ticket.update",
                {
                    "payload": {
                        "id": work.ticket_id,
                        "status": "Waiting Device Access",
                    }
                },
            )
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_device_access:backupiq_investigate",
                    last_reason=(
                        "BackupIQ true-offline state verified by both DRMM and Backup.net; "
                        "waiting for exact endpoint access."
                    ),
                )
            )
            return

        if classification == "drmm_only_offline_conflict":
            note += (
                "DRMM alone reports the endpoint offline while Backup.net reports the "
                "provider asset online. This is contradictory availability evidence, not "
                "a true-offline condition. No reinstall was attempted."
            )
            self._write_note(work, note, "Jason - BackupIQ - Diagnostic")
            self._persist_human_review_escalation(
                work,
                reason=(
                    "DRMM-only offline conflict: Backup.net remains online. "
                    "Moved to Help Desk I / Human Review with evidence."
                ),
            )
            return

        if classification == "backup_configuration_issue":
            note += (
                "Backup is disabled or provider configuration is not in the expected state. "
                "Policy/configuration changes remain outside autonomous remediation."
            )
            self._write_note(work, note, "Jason - BackupIQ - Diagnostic")
            self._persist_human_review_escalation(
                work,
                reason=(
                    "BackupIQ configuration/policy condition requires technician review."
                ),
            )
            return

        if classification == "stale_or_recovered_alert":
            note += (
                "Both providers are online, Backup.net shows a successful backup at or "
                "after ticket creation, and no current BackupIQ alert remains. The alert "
                "is recovered/stale and can be completed automatically."
            )
            self._write_note(work, note, "Jason - BackupIQ - Diagnostic")
            self._complete_verified_ticket(
                work,
                reason=(
                    "BackupIQ recovered/healthy evidence verified and ticket completion "
                    "readback succeeded."
                ),
            )
            return

        if classification in {
            "backup_agent_connectivity_failure",
            "persistent_backupiq_condition_after_success",
            "backup_failure_or_stale_success",
        }:
            if work.repair_attempts >= 1:
                note += (
                    "The single approved autonomous Endpoint Backup reinstall has already "
                    "been used for this incident cycle. Additional remediation requires "
                    "technician review."
                )
                self._write_note(work, note, "Jason - BackupIQ - Diagnostic")
                self._persist_human_review_escalation(
                    work,
                    reason=(
                        "BackupIQ remains unhealthy after the one approved autonomous "
                        "reinstall attempt."
                    ),
                )
                return
            note += (
                "DRMM confirms the endpoint is online. The current evidence either shows "
                "Backup.net offline, an unresolved BackupIQ condition despite a recent "
                "successful backup, or a stale/failed backup while both providers are "
                "online. No lower-impact playbook repair fits this evidence, so the "
                "owner-approved standing-safe Endpoint Backup reinstall is the bounded "
                "fallback remediation."
            )
            self._write_note(work, note, "Jason - BackupIQ - Diagnostic")
            self.store.put(
                self._replace(
                    work,
                    phase="backupiq_reinstall_dispatch",
                    last_reason=f"BackupIQ classification={classification}; reinstall approved.",
                )
            )
            return

        note += (
            "Availability/provider evidence does not match an approved autonomous branch. "
            "Technician review is required."
        )
        self._write_note(work, note, "Jason - BackupIQ - Diagnostic")
        self._persist_human_review_escalation(
            work,
            reason=(
                f"BackupIQ diagnostic classified {classification}; technician review required."
            ),
        )

    def _poll_backupiq_reinstall(self, work: OperationalWork) -> None:
        if not work.job_uid or not work.component_uid:
            self._persist_human_review_escalation(
                work,
                reason="BackupIQ reinstall job identity is incomplete.",
                clear_job=True,
            )
            return

        job_data = self._read_data(
            "automation.job.read", {"resource_id": work.job_uid}
        )
        job = job_data.get("job") if isinstance(job_data.get("job"), Mapping) else job_data
        status = str(job.get("status") or "").strip().casefold()
        if status in {"active", "running", "queued", "pending", "scheduled"}:
            return
        if status not in {"completed", "complete", "success", "succeeded", "finished"}:
            self._write_note(
                work,
                (
                    "Jason's approved Endpoint Backup reinstall did not complete "
                    f"successfully. Job={work.job_uid}; ProviderStatus={status or 'unknown'}. "
                    "No second autonomous reinstall was attempted."
                ),
                "Jason - BackupIQ - Remediation",
            )
            self._persist_human_review_escalation(
                work,
                reason=(
                    "Endpoint Backup reinstall failed or ended in a non-success terminal "
                    "state; technician review required."
                ),
                clear_job=True,
            )
            return

        started_at = self._backupiq_timestamp_from_reason(
            work, "backupiq_reinstall_started_at"
        )
        if started_at is None:
            self._persist_human_review_escalation(
                work,
                reason="BackupIQ reinstall verification baseline timestamp is missing.",
                clear_job=True,
            )
            return

        summary = "provider job completed successfully"
        try:
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
            if text:
                summary = self._bounded_health_summary(text)
        except Exception:
            # Provider-side backup verification below is authoritative for incident
            # resolution, so unreadable installer stdout does not itself trigger a
            # second install or false failure.
            summary = "provider job succeeded; installer stdout unavailable"

        self._write_note(
            work,
            (
                "Jason ran the owner-approved standing-safe Endpoint Backup reinstall. "
                f"Component={BACKUPIQ_INSTALLER_NAME}; Job={work.job_uid}; "
                f"Result={summary}. Installer success is not incident resolution; "
                "Backup.net must report the exact asset online and a new successful "
                "backup after the reinstall baseline before completion."
            ),
            "Jason - BackupIQ - Remediation",
        )

        deadline = started_at.timestamp() + BACKUPIQ_REINSTALL_VERIFY_SECONDS
        deadline_at = datetime.fromtimestamp(deadline, tz=timezone.utc)
        self.store.put(
            self._replace(
                work,
                phase="waiting_recheck:backupiq_verify_reinstall",
                job_uid=None,
                component_uid=None,
                last_reason=(
                    f"backupiq_reinstall_started_at={started_at.isoformat()}; "
                    f"backupiq_verify_deadline_at={deadline_at.isoformat()}; "
                    "Reinstall completed; waiting for provider recovery and a new "
                    "successful backup."
                ),
            )
        )

    def _verify_backupiq_reinstall(self, work: OperationalWork) -> None:
        started_at = self._backupiq_timestamp_from_reason(
            work, "backupiq_reinstall_started_at"
        )
        deadline_at = self._backupiq_timestamp_from_reason(
            work, "backupiq_verify_deadline_at"
        )
        if started_at is None or deadline_at is None:
            self._persist_human_review_escalation(
                work,
                reason="BackupIQ post-reinstall verification timestamps are missing.",
            )
            return

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
            self._persist_human_review_escalation(
                work,
                reason="BackupIQ device identity changed during post-reinstall verification.",
            )
            return

        asset = self._backupiq_exact_asset(work)
        if asset is None:
            self._persist_human_review_escalation(
                work,
                reason=(
                    "Exact Backup.net asset could not be uniquely re-established after reinstall."
                ),
            )
            return

        provider_status = str(asset.get("status") or "").strip().casefold()
        provider_online = provider_status == "online"
        endpoint_online = endpoint.get("online") is True
        backup_enabled = asset.get("backupEnabled") is True
        last_success = self._parse_iso_timestamp(
            asset.get("lastSuccessfulBackupTimestamp")
        )

        if not backup_enabled:
            self._persist_human_review_escalation(
                work,
                reason="Backup became disabled during post-reinstall verification.",
            )
            return

        if not endpoint_online and not provider_online:
            self.actions.execute(
                self._scope_for_work(work),
                "service.ticket.update",
                {
                    "payload": {
                        "id": work.ticket_id,
                        "status": "Waiting Device Access",
                    }
                },
            )
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_device_access:backupiq_verify_reinstall",
                    last_reason=work.last_reason,
                )
            )
            return

        if not endpoint_online and provider_online:
            self._write_note(
                work,
                (
                    "Post-reinstall verification found DRMM offline while Backup.net "
                    "remains online. This is contradictory availability evidence and "
                    "requires technician review."
                ),
                "Jason - BackupIQ - Verification",
            )
            self._persist_human_review_escalation(
                work,
                reason=(
                    "DRMM-only offline conflict during BackupIQ post-reinstall verification."
                ),
            )
            return

        if (
            endpoint_online
            and provider_online
            and last_success is not None
            and last_success > started_at
        ):
            self._write_note(
                work,
                (
                    "BackupIQ post-remediation verification succeeded. "
                    f"Device={work.hostname}; DRMMOnline=Yes; BackupNetOnline=Yes; "
                    f"NewSuccessfulBackup={last_success.isoformat()}; "
                    f"ReinstallBaseline={started_at.isoformat()}. "
                    "The successful backup occurred after remediation."
                ),
                "Jason - BackupIQ - Verification",
            )
            self._complete_verified_ticket(
                work,
                reason=(
                    "Endpoint Backup reinstall independently verified by Backup.net "
                    "online state and a new successful backup."
                ),
            )
            return

        if datetime.now(timezone.utc) >= deadline_at:
            self._write_note(
                work,
                (
                    "BackupIQ post-reinstall verification window expired without proving "
                    "a new successful backup after remediation. "
                    f"DRMMOnline={'Yes' if endpoint_online else 'No'}; "
                    f"BackupNetStatus={provider_status or 'unknown'}; "
                    f"LastSuccessfulBackup={last_success.isoformat() if last_success else 'unknown'}; "
                    f"ReinstallBaseline={started_at.isoformat()}."
                ),
                "Jason - BackupIQ - Verification",
            )
            self._persist_human_review_escalation(
                work,
                reason=(
                    "BackupIQ did not produce a verified new successful backup within "
                    "the bounded post-reinstall verification window."
                ),
            )
            return

        self.store.put(
            self._replace(
                work,
                phase="waiting_recheck:backupiq_verify_reinstall",
                last_reason=work.last_reason,
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

    def _unexpected_shutdown_powershell_records(
        self,
        work: OperationalWork,
        command: str,
        *,
        timeout_seconds: int = 60,
    ) -> list[dict[str, Any]]:
        data = self._read_data(
            "endpoint.powershell.read",
            {
                "device_uid": work.device_uid,
                "command": command,
                "timeout_seconds": timeout_seconds,
            },
        )
        stdout = data.get("stdout") or data.get("text") or ""
        return parse_json_records(stdout)

    def _unexpected_shutdown_health_evidence(
        self,
        work: OperationalWork,
    ) -> dict[str, Any]:
        reads = (
            ("events", SHUTDOWN_EVENT_COMMAND, 90),
            ("whea", WHEA_EVENT_COMMAND, 90),
            ("physical_disks", SHUTDOWN_PHYSICAL_DISK_COMMAND, 60),
            ("reliability", SHUTDOWN_RELIABILITY_COMMAND, 60),
            ("volumes", VOLUME_HEALTH_COMMAND, 60),
        )
        evidence: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for name, command, timeout_seconds in reads:
            try:
                evidence[name] = self._unexpected_shutdown_powershell_records(
                    work,
                    command,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                evidence[name] = []
                errors[name] = f"{type(exc).__name__}: {str(exc)[:180]}"
        evidence["errors"] = errors
        return evidence

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
            access_state, deb = self._device_access_state(work, endpoint=endpoint)
            self.actions.execute(
                self._scope_for_work(work),
                "service.ticket.update",
                {"payload": {"id": work.ticket_id, "status": "Waiting Device Access"}},
            )
            if access_state == "deb_online_drmm_offline":
                self._document_deb_drmm_conflict(work, deb)
            self.store.put(
                self._replace(
                    work,
                    phase="waiting_device_access:shutdown_investigate",
                    last_reason=self._device_wait_reason(access_state, deb),
                )
            )
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
        correlated_event_times: list[int] = [incident_ms]
        active_physical_devices = 0
        ambiguous_peers = 0
        checked_peers = 0
        if self._physical_device(endpoint) is True:
            physical_hits.add(work.device_uid)
            active_physical_devices += 1
        if site:
            site_data = self._read_data("endpoint.device.search", {"site": site})
            matches = site_data.get("resource_matches")
            if isinstance(matches, list):
                for match in matches[:100]:
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
                    if peer.get("online") is True:
                        active_physical_devices += 1
                    peer_history = self._read_data(
                        "endpoint.alert.history.search", {"resource_id": uid}
                    )
                    peer_alerts = peer_history.get("alerts")
                    if not isinstance(peer_alerts, list):
                        ambiguous_peers += 1
                        continue
                    matching_times = [
                        ts
                        for item in peer_alerts
                        if isinstance(item, Mapping)
                        and self._unexpected_shutdown_alert(item)
                        and (ts := self._alert_timestamp_ms(item)) is not None
                        and abs(ts - incident_ms) <= INCIDENT_WINDOW_MS
                    ]
                    if matching_times:
                        physical_hits.add(uid)
                        correlated_event_times.append(min(matching_times))

        site_classification = classify_site_scope(
            affected_physical_devices=len(physical_hits),
            active_physical_devices=active_physical_devices,
            ambiguous_physical_devices=ambiguous_peers,
        )
        site_event = (
            site_event_id(site, min(correlated_event_times))
            if site_classification in {"SITE_ENVIRONMENTAL", "SITE_CORRELATED_SMALL_SITE"}
            else ""
        )

        health = self._unexpected_shutdown_health_evidence(work)
        if health["errors"]:
            self._write_note(
                work,
                (
                    "Jason unexpected-shutdown evidence collection was incomplete. "
                    f"Device={work.hostname}; SiteClassification={site_classification}; "
                    f"EvidenceErrors={json.dumps(health['errors'], sort_keys=True)[:700]}. "
                    "No repair, reboot, service change, firmware change, or disk mutation "
                    "was attempted."
                ),
                "Jason - Unexpected Shutdown - Diagnostic",
            )
            self._persist_human_review_escalation(
                work,
                reason="Unexpected-shutdown health evidence was incomplete.",
            )
            return

        storage_risk, storage_reasons = shutdown_storage_health_risk(
            events=health["events"],
            whea_events=health["whea"],
            physical_disks=health["physical_disks"],
            reliability=health["reliability"],
            volumes=health["volumes"],
        )
        shutdown_type = shutdown_character(health["events"])
        protected = shutdown_protected_role(endpoint)
        recurring = len(recurrence) >= 2 and site_classification not in {
            "SITE_ENVIRONMENTAL",
            "SITE_CORRELATED_SMALL_SITE",
        }
        independent_risk = storage_risk or protected or recurring

        note = (
            "STATUS\n"
            f"Unexpected shutdown classification for {work.hostname}: {site_classification}.\n\n"
            "KEY EVIDENCE\n"
            f"- IncidentTimestampMs={incident_ms}\n"
            f"- ShutdownCharacter={shutdown_type}\n"
            f"- ShutdownEvents30d={len(recurrence)}\n"
            f"- AffectedPhysicalDevicesPlusMinus15Min={len(physical_hits)}\n"
            f"- ActivePhysicalDevicesAtSite={active_physical_devices}\n"
            f"- PhysicalPeersChecked={checked_peers}\n"
            f"- AmbiguousPhysicalPeers={ambiguous_peers}\n"
            f"- SiteEventId={site_event or 'none'}\n"
            f"- StorageHealthRisk={'Yes' if storage_risk else 'No'}"
            + (
                f" ({'; '.join(storage_reasons)[:500]})"
                if storage_reasons
                else ""
            )
            + "\n"
            f"- ProtectedOrCriticalRole={'Yes' if protected else 'No'}\n"
            f"- IndependentDeviceRisk={'Yes' if independent_risk else 'No'}\n\n"
            "WHAT JASON DID\n"
            "Correlated same-site physical-device shutdown history and collected "
            "read-only Windows shutdown, WHEA, physical-disk, reliability, and volume-health evidence.\n\n"
            "CHANGES MADE\n"
            "None to the endpoint. No CHKDSK repair, storage repair, reboot, firmware/driver "
            "change, service interruption, or other disruptive action was attempted.\n\n"
            "JASON STATE\n"
        )

        if site_classification == "UNDETERMINED":
            note += "human_review"
            self._write_note(work, note, "Jason - Unexpected Shutdown - Correlation")
            self._persist_human_review_escalation(
                work,
                reason=(
                    "Site-vs-device classification could not be proven from complete "
                    "same-site physical-device evidence."
                ),
            )
            return

        if independent_risk:
            note += "human_review"
            self._write_note(work, note, "Jason - Unexpected Shutdown - Diagnostic")
            self._persist_human_review_escalation(
                work,
                reason=(
                    "Unexpected shutdown has independent device risk requiring technician "
                    "review despite site correlation."
                ),
            )
            return

        if site_classification == "DEVICE_SPECIFIC":
            note += "human_review"
            self._write_note(work, note, "Jason - Unexpected Shutdown - Device Specific")
            self._persist_human_review_escalation(
                work,
                reason=(
                    "Unexpected shutdown is isolated to one physical device. No hardware "
                    "or storage damage is proven, but device-specific root cause requires "
                    "technician review before autonomous closure."
                ),
            )
            return

        note += "complete"
        self._write_note(work, note, "Jason - Unexpected Shutdown - Resolution")
        self._complete_verified_ticket(
            work,
            reason=(
                f"{site_classification} shutdown event verified with no independent "
                "device/storage risk; ticket completion readback succeeded."
            ),
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
        self._persist_human_review_escalation(
            work,
            reason=(
                "POST diagnostic complete; protected/recurring/closure branch "
                "requires technician review."
                if protected_role or recurring
                else "POST diagnostic complete; isolated closure branch not yet promoted."
            ),
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
            self._persist_human_review_escalation(
                work,
                reason=(
                    "Security Log verified healthy; exact alert and process-generated "
                    "security-ticket cleanup remains separately gated."
                ),
                clear_job=True,
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
        self._persist_human_review_escalation(
            work,
            reason=(
                "Standing-safe DNS diagnostic completed; remediation branch "
                "requires separate accepted authority."
            ),
            clear_job=True,
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

    def _complete_verified_ticket(self, work: OperationalWork, *, reason: str) -> None:
        scope = self._scope_for_work(work)
        update_output = self.actions.execute(
            scope,
            "service.ticket.update",
            {"payload": {"id": work.ticket_id, "status": "Complete"}},
        )
        update_data = self._action_data(update_output)
        verification = update_data.get("jasonVerification")
        verified_fields = verification.get("verifiedFields") if isinstance(verification, Mapping) else None
        if (
            not isinstance(verification, Mapping)
            or verification.get("readbackVerified") is not True
            or not isinstance(verified_fields, Sequence)
            or isinstance(verified_fields, (str, bytes))
            or "status" not in {str(value) for value in verified_fields}
        ):
            raise OperationalAutonomyError(
                "ticket completion readback did not verify the requested status"
            )
        self.store.put(
            self._replace(
                work,
                phase="complete",
                job_uid=None,
                component_uid=None,
                last_reason=reason,
            )
        )

    def _notify_patch_completion(
        self,
        work: OperationalWork,
        *,
        patch_summary: str,
    ) -> None:
        if self.completion_notifier is None:
            return
        fingerprint = hashlib.sha256(
            (
                "patch_completed|"
                + work.ticket_number
                + "|"
                + work.hostname
                + "|"
                + patch_summary
            ).encode("utf-8")
        ).hexdigest()
        note_title = "Teams - Autonomous Patch Completion"
        if (
            self.store.last_note_fingerprint(
                work.ticket_id,
                work.playbook_id,
                note_title,
            )
            == fingerprint
        ):
            return
        self.completion_notifier.send(
            "patch_completed",
            ticket_number=work.ticket_number,
            hostname=work.hostname,
            patch_summary=patch_summary[:300],
        )
        self.store.remember_note_fingerprint(
            work.ticket_id,
            work.playbook_id,
            note_title,
            fingerprint,
        )

    def _complete(self, work: OperationalWork, stdout: str) -> None:
        summary = self._bounded_health_summary(stdout)
        note = (
            "Jason autonomous EDR/AV playbook completed. "
            f"Endpoint {work.hostname} returned authoritative Status=Healthy"
            + (" after one standing-safe repair attempt." if work.repair_attempts else ".")
            + f" Verification: {summary}. Autotask terminal status readback verified."
        )
        self._complete_verified_ticket(
            work,
            reason="Verified healthy and ticket completion readback succeeded.",
        )
        self._write_note(work, note, "Jason - Autonomous EDR/AV Resolution")

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
                "Jason autonomous BackupIQ work stopped for technician review. "
                f"{reason} "
                + (
                    "One owner-approved bounded Endpoint Backup reinstall was attempted. "
                    if work.repair_attempts
                    else "No Endpoint Backup reinstall was attempted. "
                )
                + "No clean install/new-asset lifecycle mutation, backup deletion, "
                "retention/policy change, restore, credential disclosure, reboot, or "
                "other unrelated modifying backup action was attempted."
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
        self._persist_human_review_escalation(
            work,
            reason=reason,
            clear_job=True,
        )

    def _persist_human_review_escalation(
        self,
        work: OperationalWork,
        *,
        reason: str,
        clear_job: bool = False,
    ) -> None:
        if work.playbook_id in {
            BACKUPIQ_SCOPE.playbook_id,
            LOW_DISK_SCOPE.playbook_id,
        }:
            self._handoff_to_helpdesk(work, status="Human Review")
        else:
            self._handoff_to_helpdesk(work)
        changes: dict[str, Any] = {
            "phase": "escalated",
            "last_reason": reason,
        }
        if clear_job:
            changes["job_uid"] = None
            changes["component_uid"] = None
        self.store.put(self._replace(work, **changes))

    @staticmethod
    def _vulscan_first_not_approved_at(work: OperationalWork) -> datetime | None:
        match = re.search(
            r"first_not_approved_at=([^;]+)",
            str(work.last_reason or ""),
        )
        if match is None:
            return None
        try:
            parsed = datetime.fromisoformat(match.group(1).strip())
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _handoff_vulscan_approval_review(self, work: OperationalWork) -> None:
        scope = self._scope_for_work(work)
        handoff = self.actions.execute(
            scope,
            "service.ticket.update",
            {
                "payload": {
                    "id": work.ticket_id,
                    "queueID": "Help Desk I",
                    "status": "Human Review",
                }
            },
        )
        handoff_data = self._action_data(handoff)
        verification = handoff_data.get("jasonVerification")
        verified_fields = (
            verification.get("verifiedFields")
            if isinstance(verification, Mapping)
            else None
        )
        verified = (
            verification.get("readbackVerified") is True
            and isinstance(verified_fields, Sequence)
            and not isinstance(verified_fields, (str, bytes))
            and {"queueID", "status"}.issubset(
                {str(value) for value in verified_fields}
            )
        ) if isinstance(verification, Mapping) else False
        if not verified:
            raise OperationalAutonomyError(
                "VulScan approval-review handoff readback did not verify queue and status"
            )

    def _handoff_to_helpdesk(
        self,
        work: OperationalWork,
        *,
        status: str = "New",
    ) -> None:
        # Human-review work must not be stranded in Jason's queue. Return it to
        # Help Desk I with an actionable status and require provider readback.
        scope = self._scope_for_work(work)
        handoff = self.actions.execute(
            scope,
            "service.ticket.update",
            {
                "payload": {
                    "id": work.ticket_id,
                    "queueID": "Help Desk I",
                    "status": status,
                }
            },
        )
        handoff_data = self._action_data(handoff)
        verification = handoff_data.get("jasonVerification")
        verified_fields = (
            verification.get("verifiedFields")
            if isinstance(verification, Mapping)
            else None
        )
        verified = (
            verification.get("readbackVerified") is True
            and isinstance(verified_fields, Sequence)
            and not isinstance(verified_fields, (str, bytes))
            and {"queueID", "status"}.issubset(
                {str(value) for value in verified_fields}
            )
        ) if isinstance(verification, Mapping) else False
        if not verified:
            raise OperationalAutonomyError(
                "human-review handoff readback did not verify queue and status"
            )

    def _assigned_new_ticket_is_unworked(self, candidate) -> bool:
        """Return True only for assigned New tickets with no technician-authored notes.

        Workflow/system notes, GPT Insights, customer/contact notes, and Jason's own
        notes do not establish human technician ownership. Read failure fails closed.
        """
        status_label = str(
            candidate.context.get("_jason_source_status_label") or ""
        ).strip()
        if status_label.casefold() != "new":
            return False
        try:
            result = self.reads.execute(
                "service.ticket.notes.search",
                {"ticket_id": int(candidate.resource_id)},
            )
        except Exception:
            return False
        evidence = result.get("evidence") if isinstance(result, Mapping) else None
        data = evidence.get("data") if isinstance(evidence, Mapping) else None
        items = data.get("items") if isinstance(data, Mapping) else None
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            return False

        owned_ids = set(
            getattr(
                getattr(self.queue_source, "config", None),
                "owned_resource_ids",
                (),
            )
            or ()
        )
        for note in items:
            if not isinstance(note, Mapping):
                continue
            title = str(note.get("title") or "").casefold()
            description = str(note.get("description") or "").casefold()
            if "gpt insight" in title or "gpt insight" in description:
                continue
            if note.get("createdByContactID") is not None:
                continue
            creator = note.get("creatorResourceID")
            try:
                creator_id = int(creator) if creator is not None else None
            except (TypeError, ValueError):
                creator_id = None
            if creator_id is None:
                continue
            if creator_id == 4 or creator_id in owned_ids:
                continue
            if self._resource_is_automation_identity(creator_id):
                continue
            return False
        return True

    def _resource_is_automation_identity(self, resource_id: int) -> bool:
        cached = self._resource_automation_cache.get(resource_id)
        if cached is not None:
            return cached
        try:
            result = self.reads.execute(
                "service.resource.read",
                {"resource_id": resource_id},
            )
        except Exception:
            self._resource_automation_cache[resource_id] = False
            return False
        evidence = result.get("evidence") if isinstance(result, Mapping) else None
        data = evidence.get("data") if isinstance(evidence, Mapping) else None
        item = data.get("item") if isinstance(data, Mapping) else None
        if not isinstance(item, Mapping):
            self._resource_automation_cache[resource_id] = False
            return False
        automation_identity = int(item.get("licenseType") or 0) == 7
        self._resource_automation_cache[resource_id] = automation_identity
        return automation_identity

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
        # Offline is transient and must not consume an active-work slot. For a
        # ticket already owned by Jason, reflect that state explicitly in
        # Autotask exactly once. The queue source continues to reconcile
        # Waiting Device Access tickets, so the normal claim path restores In
        # Progress automatically as soon as the exact DRMM endpoint is online.
        message = str(error).casefold()
        if isinstance(error, BackupIQManagedEndpointMissing):
            ticket_id = int(candidate.resource_id)
            context = candidate.context
            work = OperationalWork(
                ticket_id=ticket_id,
                ticket_number=str(context.get("ticketNumber") or ticket_id),
                title=str(context.get("title") or ""),
                playbook_id=scope.playbook_id,
                source_queue=str(candidate.source_queue),
                company_id=error.company_id,
                configuration_item_id=error.ci_id,
                device_uid="",
                hostname=error.hostname,
                phase="escalated",
                last_reason=str(error)[:500],
                source_version=(str(candidate.source_version or "").strip() or None),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            self._write_note(
                work,
                (
                    "Jason verified the BackupIQ provider asset and Autotask configuration, "
                    "but the corresponding managed Datto RMM endpoint is no longer present. "
                    f"Device={error.hostname}; AutotaskCompanyID={error.company_id}; "
                    f"ConfigurationItemID={error.ci_id}; BackupProviderStatus={error.provider_status or 'unknown'}. "
                    "No reinstall, backup deletion, retention change, or endpoint mutation was attempted. "
                    "Technician review is required to determine whether the device was retired, replaced, "
                    "or needs to be restored to managed RMM coverage."
                ),
                "Jason - BackupIQ - Managed Endpoint Missing",
            )
            self._persist_human_review_escalation(
                work,
                reason=(
                    "BackupIQ asset and Autotask CI are proven, but no managed Datto RMM endpoint exists."
                ),
            )
            return
        if (
            "endpoint is not currently online" in message
            or "drmm access unavailable while deb reports endpoint online" in message
        ):
            status_label = str(
                candidate.context.get("_jason_source_status_label") or ""
            ).strip()
            if (
                str(candidate.source_queue).strip().casefold() == "jason"
                and candidate.owned_by_jason
                and status_label.casefold() != "waiting device access"
            ):
                self.actions.execute(
                    scope,
                    "service.ticket.update",
                    {
                        "payload": {
                            "id": int(candidate.resource_id),
                            "status": "Waiting Device Access",
                        }
                    },
                )
            if isinstance(error, DeviceAccessDeferred):
                waiting_work = self._replace(
                    error.work,
                    phase="waiting_device_access:claim",
                    last_reason=str(error)[:500],
                )
                self.store.put(waiting_work)
            return
        # Missing/invalid ticket identity prerequisites outside Jason are not a
        # durable failure. They can be corrected by normal PSA triage; keeping a
        # terminal row would suppress reconsideration forever.
        if (
            str(candidate.source_queue).strip().casefold() != "jason"
            and (
                "company id must be a positive integer" in message
                or "company id must be a non-negative integer" in message
                or "configuration item id must be a positive integer" in message
                or "configuration belongs to another company" in message
            )
        ):
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
            source_version=(str(candidate.source_version or "").strip() or None),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.put(work)
        try:
            self._synchronize_blocked_ticket_lifecycle(work, candidate)
        except Exception as exc:
            if self.audit is not None:
                self._audit_diagnostic(
                    "autonomy.blocked_ticket_lifecycle_sync.failed",
                    {
                        "ticket_id": ticket_id,
                        "error_type": type(exc).__name__,
                    },
                )

    def _write_note(self, work: OperationalWork, body: str, title: str) -> bool:
        legacy_normalized_title = " ".join(str(title).split())
        legacy_normalized_body = " ".join(str(body).split())
        legacy_encoded = json.dumps(
            {
                "title": legacy_normalized_title,
                "body": legacy_normalized_body,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        legacy_fingerprint = hashlib.sha256(legacy_encoded).hexdigest()

        structured = legacy_technical_note(
            title=title,
            body=body,
            issue=work.title,
            scope=[
                f"Ticket={work.ticket_number}",
                f"CompanyID={work.company_id}",
                f"Device={work.hostname or 'not resolved'}",
                f"ConfigurationItemID={work.configuration_item_id or 'not associated'}",
                f"EndpointUID={work.device_uid or 'not resolved'}",
            ],
            playbook=work.playbook_id,
            phase=work.phase,
            reason=work.last_reason,
        )
        title = canonical_title(structured.kind)
        body = render_technical_note(structured)
        normalized_title = " ".join(str(title).split())
        normalized_body = " ".join(str(body).split())
        encoded = json.dumps(
            {"title": normalized_title, "body": normalized_body},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        fingerprint = hashlib.sha256(encoded).hexdigest()
        prior = self.store.last_note_fingerprint(
            work.ticket_id, work.playbook_id, normalized_title
        )
        if prior == fingerprint:
            return False

        legacy_prior = self.store.last_note_fingerprint(
            work.ticket_id,
            work.playbook_id,
            legacy_normalized_title,
        )
        if legacy_prior == legacy_fingerprint:
            self.store.remember_note_fingerprint(
                work.ticket_id,
                work.playbook_id,
                normalized_title,
                fingerprint,
            )
            return False

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
        self.store.remember_note_fingerprint(
            work.ticket_id, work.playbook_id, normalized_title, fingerprint
        )
        return True

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
    def _company_id(value: Any) -> int:
        if isinstance(value, bool):
            raise OperationalAutonomyError("company id must be a non-negative integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise OperationalAutonomyError(
                "company id must be a non-negative integer"
            ) from exc
        if parsed < 0:
            raise OperationalAutonomyError("company id must be a non-negative integer")
        return parsed

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
            "source_version": work.source_version,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        values.update(changes)
        return OperationalWork(**values)
