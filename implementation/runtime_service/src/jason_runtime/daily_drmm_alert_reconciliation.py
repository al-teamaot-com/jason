"""Daily bounded reconciliation of recent Datto RMM alerts.

The sweep is intentionally fail-closed.  It only considers currently-open DRMM
alerts whose provider timestamp falls inside a rolling lookback window and only
mutates alert/ticket state when a registered verifier proves the triggering
condition is no longer present on the exact managed endpoint.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .autonomy_worker_runtime import GovernedAutonomyActionPort, PlaybookScope


RECONCILIATION_SCOPE = PlaybookScope(
    playbook_id="drmm_recent_alert_reconciliation",
    playbook_version="1.0.0",
    policy_id="playbook-autonomy:drmm_recent_alert_reconciliation",
    required_action_capabilities=(
        "endpoint.alert.resolve",
        "service.ticket.note.create",
        "service.ticket.update",
    ),
)


@dataclass(frozen=True, slots=True)
class AlertDecision:
    outcome: str
    reason: str
    evidence: Mapping[str, Any]


class SQLiteDailyAlertReconciliationState:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS drmm_daily_alert_reconciliation_state (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        last_started_at TEXT,
        last_completed_at TEXT,
        last_summary_json TEXT
    );
    INSERT OR IGNORE INTO drmm_daily_alert_reconciliation_state(singleton)
    VALUES (1);
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(self._SCHEMA)
        os.chmod(self.path, 0o600)

    def last_completed_at(self) -> datetime | None:
        row = self._connection.execute(
            "SELECT last_completed_at FROM drmm_daily_alert_reconciliation_state WHERE singleton=1"
        ).fetchone()
        value = None if row is None else row["last_completed_at"]
        return datetime.fromisoformat(value) if value else None

    def mark_started(self, when: datetime) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE drmm_daily_alert_reconciliation_state SET last_started_at=? WHERE singleton=1",
                (when.isoformat(),),
            )

    def mark_completed(self, when: datetime, summary: Mapping[str, Any]) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE drmm_daily_alert_reconciliation_state SET last_completed_at=?, last_summary_json=? WHERE singleton=1",
                (when.isoformat(), json.dumps(dict(summary), sort_keys=True, separators=(",", ":"))),
            )

    def close(self) -> None:
        self._connection.close()


def _evidence(result: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = result.get("evidence")
    return evidence if isinstance(evidence, Mapping) else {}


def _successful(result: Mapping[str, Any]) -> bool:
    return str(result.get("status") or "") == "succeeded"


def _provider_timestamp(alert: Mapping[str, Any]) -> datetime | None:
    raw = alert.get("timestamp")
    try:
        millis = int(raw)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)


def _alerts(result: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    data = _evidence(result).get("data")
    provider_data = data.get("provider_data") if isinstance(data, Mapping) else None
    if isinstance(provider_data, Mapping):
        values = provider_data.get("alerts")
    elif isinstance(data, Mapping):
        values = data.get("alerts")
    else:
        values = None
    return tuple(item for item in (values or ()) if isinstance(item, Mapping))


class RecentAlertVerifierRegistry:
    """Explicit verifier registry. Unsupported alert classes are never guessed."""

    def __init__(self, reads) -> None:
        self.reads = reads

    def verify(self, alert: Mapping[str, Any]) -> AlertDecision:
        context = alert.get("alertContext")
        context = context if isinstance(context, Mapping) else {}
        alert_class = str(context.get("@class") or "")
        if alert_class == "endpoint_security_threat_ctx":
            return self._verify_endpoint_security(alert)
        return AlertDecision(
            "unsupported",
            f"no authoritative verifier registered for {alert_class or 'unknown alert class'}",
            {"alert_class": alert_class or None},
        )

    def _verify_endpoint_security(self, alert: Mapping[str, Any]) -> AlertDecision:
        source = alert.get("alertSourceInfo")
        source = source if isinstance(source, Mapping) else {}
        device_uid = str(source.get("deviceUid") or "").strip()
        if not device_uid:
            return AlertDecision("inconclusive", "missing exact DRMM device UID", {})

        device = self.reads.execute("endpoint.device.read", {"resource_id": device_uid})
        if not _successful(device):
            return AlertDecision("inconclusive", "endpoint current-state read failed", {})
        record = _evidence(device).get("record")
        record = record if isinstance(record, Mapping) else {}
        if not bool(record.get("online")):
            return AlertDecision("waiting", "endpoint is offline; current health cannot be proven", {})

        status = self.reads.execute("endpoint.security.status.read", {"resource_id": device_uid})
        if not _successful(status):
            return AlertDecision("inconclusive", "endpoint security status read failed", {})
        status_data = _evidence(status).get("data")
        matches = status_data.get("resource_matches") if isinstance(status_data, Mapping) else None
        security = next((x for x in (matches or ()) if isinstance(x, Mapping)), None)
        if not isinstance(security, Mapping):
            return AlertDecision("inconclusive", "endpoint security identity could not be resolved", {})

        av = security.get("datto_av")
        av = av if isinstance(av, Mapping) else {}
        healthy_engine = bool(av.get("enabled")) and bool(av.get("connected")) and bool(av.get("engine_ready"))
        agent_id = str(security.get("agent_id") or "").strip()
        if not healthy_engine or not agent_id:
            return AlertDecision(
                "unhealthy",
                "Datto AV/EDR is not currently healthy enough to prove recovery",
                {"agent_id_present": bool(agent_id), "engine_ready": healthy_engine},
            )

        detections = self.reads.execute(
            "endpoint.security.detection.search",
            {"agent_id": agent_id, "archived": False, "limit": 50},
        )
        if not _successful(detections):
            return AlertDecision("inconclusive", "active detection read failed", {})
        det_data = _evidence(detections).get("data")
        active = det_data.get("alerts") if isinstance(det_data, Mapping) else None
        active = [item for item in (active or ()) if isinstance(item, Mapping)]
        if active:
            return AlertDecision(
                "unhealthy",
                "one or more active EDR detections remain",
                {"active_detection_count": len(active)},
            )

        return AlertDecision(
            "healthy",
            "endpoint online, Datto AV/EDR healthy, and no active detections remain",
            {
                "device_uid": device_uid,
                "agent_id": agent_id,
                "engine_version": av.get("engine_version"),
                "definition_version": av.get("vdf_version"),
                "active_detection_count": 0,
            },
        )


class DailyDrmmAlertReconciliationMaintenance:
    """Run one recent-alert sweep per configured cadence, durably."""

    def __init__(
        self,
        *,
        reads,
        actions: GovernedAutonomyActionPort,
        state: SQLiteDailyAlertReconciliationState,
        lookback: timedelta = timedelta(hours=24),
        cadence: timedelta = timedelta(hours=24),
        now=lambda: datetime.now(timezone.utc),
        audit=None,
    ) -> None:
        if lookback <= timedelta(0) or lookback > timedelta(days=7):
            raise ValueError("lookback must be greater than zero and no more than 7 days")
        if cadence < timedelta(hours=1):
            raise ValueError("cadence must be at least one hour")
        self.reads = reads
        self.actions = actions
        self.state = state
        self.lookback = lookback
        self.cadence = cadence
        self.now = now
        self.audit = audit
        self.verifiers = RecentAlertVerifierRegistry(reads)

    def tick(self) -> bool:
        now = self.now()
        last = self.state.last_completed_at()
        if last is not None and now - last < self.cadence:
            return False
        self.run_once(now=now)
        return True

    def run_once(self, *, now: datetime | None = None) -> Mapping[str, Any]:
        now = now or self.now()
        cutoff = now - self.lookback
        self.state.mark_started(now)
        summary = {
            "window_start": cutoff.isoformat(),
            "window_end": now.isoformat(),
            "open_seen": 0,
            "in_window": 0,
            "resolved": 0,
            "unhealthy": 0,
            "waiting": 0,
            "unsupported": 0,
            "inconclusive": 0,
            "ticket_reconciled": 0,
        }

        result = self.reads.execute("management.alert.search", {"status": "open"})
        if not _successful(result):
            summary["inconclusive"] += 1
            self.state.mark_completed(now, summary)
            return summary

        current = _alerts(result)
        summary["open_seen"] = len(current)
        for alert in current:
            created = _provider_timestamp(alert)
            if created is None or created < cutoff or created > now:
                continue
            summary["in_window"] += 1
            decision = self.verifiers.verify(alert)
            if decision.outcome != "healthy":
                summary[decision.outcome if decision.outcome in summary else "inconclusive"] += 1
                self._audit(alert, decision, mutated=False)
                continue

            if self._resolve_and_verify(alert, decision):
                summary["resolved"] += 1
                if self._reconcile_ticket(alert, decision):
                    summary["ticket_reconciled"] += 1
                self._audit(alert, decision, mutated=True)
            else:
                summary["inconclusive"] += 1
                self._audit(
                    alert,
                    AlertDecision("inconclusive", "exact alert resolution did not verify", decision.evidence),
                    mutated=False,
                )

        self.state.mark_completed(now, summary)
        return summary

    def _resolve_and_verify(self, alert: Mapping[str, Any], decision: AlertDecision) -> bool:
        source = alert.get("alertSourceInfo")
        source = source if isinstance(source, Mapping) else {}
        alert_uid = str(alert.get("alertUid") or "").strip()
        device_uid = str(source.get("deviceUid") or "").strip()
        if not alert_uid or not device_uid:
            return False
        self.actions.execute(
            RECONCILIATION_SCOPE,
            "endpoint.alert.resolve",
            {"alert_uid": alert_uid, "device_uid": device_uid},
        )
        history = self.reads.execute("endpoint.alert.history.search", {"resource_id": device_uid})
        if not _successful(history):
            return False
        return any(
            str(item.get("alertUid") or "") == alert_uid and bool(item.get("resolved"))
            for item in _alerts(history)
        )

    def _reconcile_ticket(self, alert: Mapping[str, Any], decision: AlertDecision) -> bool:
        ticket_number = str(alert.get("ticketNumber") or "").strip()
        if not ticket_number:
            return False
        found = self.reads.execute(
            "service.ticket.search",
            {"ticket_number": ticket_number, "page_size": 5},
        )
        if not _successful(found):
            return False
        data = _evidence(found).get("data")
        items = data.get("items") if isinstance(data, Mapping) else None
        ticket = next((x for x in (items or ()) if isinstance(x, Mapping)), None)
        if not isinstance(ticket, Mapping):
            return False
        ticket_id = ticket.get("id")
        if ticket_id is None:
            return False
        if int(ticket.get("status") or 0) == 5:
            return False
        alert_uid = str(alert.get("alertUid") or "")
        host = str((alert.get("alertSourceInfo") or {}).get("deviceName") or "")
        note = (
            "STATUS: Resolved by scheduled 24-hour DRMM alert reconciliation.\n"
            "NEXT STEP: No technician action required.\n"
            f"KEY EVIDENCE: Exact alert {alert_uid}; endpoint {host}; {decision.reason}.\n"
            "WHAT JASON DID: Verified current endpoint security state, resolved the exact DRMM alert, "
            "and verified provider resolution by readback.\n"
            "CHANGES MADE: DRMM alert resolved; no endpoint remediation or disruptive action performed."
        )
        self.actions.execute(
            RECONCILIATION_SCOPE,
            "service.ticket.note.create",
            {"payload": {"ticketID": int(ticket_id), "title": "Jason - Scheduled DRMM Reconciliation - Resolution", "description": note, "noteType": 3, "publish": 1}},
        )
        self.actions.execute(
            RECONCILIATION_SCOPE,
            "service.ticket.update",
            {"payload": {"id": int(ticket_id), "status": "Complete"}},
        )
        verify = self.reads.execute("service.ticket.read", {"ticket_id": int(ticket_id)})
        if not _successful(verify):
            return False
        vdata = _evidence(verify).get("data")
        vitems = vdata.get("items") if isinstance(vdata, Mapping) else None
        current = next((x for x in (vitems or ()) if isinstance(x, Mapping)), None)
        return isinstance(current, Mapping) and int(current.get("status") or 0) == 5

    def _audit(self, alert: Mapping[str, Any], decision: AlertDecision, *, mutated: bool) -> None:
        if self.audit is None:
            return
        self.audit.record(
            "autonomy.drmm_recent_alert_reconciliation",
            {
                "alert_uid": alert.get("alertUid"),
                "device_uid": (alert.get("alertSourceInfo") or {}).get("deviceUid"),
                "ticket_number": alert.get("ticketNumber"),
                "decision": decision.outcome,
                "reason": decision.reason,
                "mutated": mutated,
                "evidence": dict(decision.evidence),
            },
        )
