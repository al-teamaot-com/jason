"""Shadow-mode classification for recurring Windows time-source alerts.

This maintenance path is intentionally read-only. It detects the exact DRMM
component alert signature, proves endpoint identity, extracts the observed and
approved time sources, measures recurrence from authoritative alert history, and
persists/audits the resulting classification. It never dispatches remediation,
resolves alerts, or mutates Autotask.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


TIME_SOURCE_MISMATCH = "Time source mismatch."
APPROVED_LIST_MARKER = "not in approved list:"
RECURRENCE_WINDOW = timedelta(days=30)
RECURRENCE_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class TimeSourceDecision:
    alert_uid: str
    device_uid: str
    hostname: str
    site: str
    observed_source: str
    approved_sources: tuple[str, ...]
    recurrence_count: int
    classification: str
    reason: str
    fingerprint: str


class SQLiteWindowsTimeSourceShadowState:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS windows_time_source_shadow_state (
        alert_uid TEXT PRIMARY KEY,
        device_uid TEXT NOT NULL,
        hostname TEXT NOT NULL,
        site TEXT NOT NULL,
        observed_source TEXT NOT NULL,
        approved_sources_json TEXT NOT NULL,
        recurrence_count INTEGER NOT NULL,
        classification TEXT NOT NULL,
        reason TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS windows_time_source_shadow_meta (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        last_run_at TEXT
    );
    INSERT OR IGNORE INTO windows_time_source_shadow_meta(singleton) VALUES (1);
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

    def last_run_at(self) -> datetime | None:
        row = self._connection.execute(
            "SELECT last_run_at FROM windows_time_source_shadow_meta WHERE singleton=1"
        ).fetchone()
        value = None if row is None else row["last_run_at"]
        return datetime.fromisoformat(value) if value else None

    def mark_run(self, when: datetime) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE windows_time_source_shadow_meta SET last_run_at=? WHERE singleton=1",
                (when.isoformat(),),
            )

    def put(self, decision: TimeSourceDecision, *, when: datetime) -> bool:
        row = self._connection.execute(
            "SELECT fingerprint FROM windows_time_source_shadow_state WHERE alert_uid=?",
            (decision.alert_uid,),
        ).fetchone()
        changed = row is None or str(row["fingerprint"]) != decision.fingerprint
        first_seen = when.isoformat()
        existing = self._connection.execute(
            "SELECT first_seen_at FROM windows_time_source_shadow_state WHERE alert_uid=?",
            (decision.alert_uid,),
        ).fetchone()
        if existing is not None:
            first_seen = str(existing["first_seen_at"])
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO windows_time_source_shadow_state(
                    alert_uid,device_uid,hostname,site,observed_source,
                    approved_sources_json,recurrence_count,classification,reason,
                    fingerprint,first_seen_at,last_seen_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(alert_uid) DO UPDATE SET
                    device_uid=excluded.device_uid,
                    hostname=excluded.hostname,
                    site=excluded.site,
                    observed_source=excluded.observed_source,
                    approved_sources_json=excluded.approved_sources_json,
                    recurrence_count=excluded.recurrence_count,
                    classification=excluded.classification,
                    reason=excluded.reason,
                    fingerprint=excluded.fingerprint,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    decision.alert_uid,
                    decision.device_uid,
                    decision.hostname,
                    decision.site,
                    decision.observed_source,
                    json.dumps(decision.approved_sources),
                    decision.recurrence_count,
                    decision.classification,
                    decision.reason,
                    decision.fingerprint,
                    first_seen,
                    when.isoformat(),
                ),
            )
        return changed

    def close(self) -> None:
        self._connection.close()


def _successful(result: Mapping[str, Any]) -> bool:
    return str(result.get("status") or "") == "succeeded"


def _evidence(result: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = result.get("evidence")
    return evidence if isinstance(evidence, Mapping) else {}


def _alert_items(result: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    evidence = _evidence(result)
    data = evidence.get("data")
    if isinstance(data, Mapping):
        provider_data = data.get("provider_data")
        if isinstance(provider_data, Mapping) and isinstance(provider_data.get("alerts"), list):
            return tuple(x for x in provider_data["alerts"] if isinstance(x, Mapping))
        for key in ("alerts", "items"):
            values = data.get(key)
            if isinstance(values, list):
                return tuple(x for x in values if isinstance(x, Mapping))
    for key in ("alerts", "items"):
        values = evidence.get(key)
        if isinstance(values, list):
            return tuple(x for x in values if isinstance(x, Mapping))
    return ()


def is_time_source_alert(alert: Mapping[str, Any]) -> bool:
    context = alert.get("alertContext")
    if not isinstance(context, Mapping) or str(context.get("@class") or "") != "comp_script_ctx":
        return False
    diagnostics = str(alert.get("diagnostics") or "")
    return TIME_SOURCE_MISMATCH in diagnostics and APPROVED_LIST_MARKER in diagnostics


def parse_sources(alert: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    diagnostics = str(alert.get("diagnostics") or "")
    match = re.search(
        r"Current source '([^']*)' is not in approved list:\s*([^\r\n]+)",
        diagnostics,
        flags=re.IGNORECASE,
    )
    if not match:
        return "", ()
    observed = match.group(1).strip()
    approved = tuple(
        part.strip()
        for part in re.split(r"[,;]", match.group(2))
        if part.strip()
    )
    return observed, approved


def _provider_time(alert: Mapping[str, Any]) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(alert.get("timestamp")) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


class WindowsTimeSourceShadowMaintenance:
    def __init__(
        self,
        *,
        reads,
        state: SQLiteWindowsTimeSourceShadowState,
        cadence: timedelta = timedelta(minutes=15),
        now=lambda: datetime.now(timezone.utc),
        audit=None,
    ) -> None:
        if cadence < timedelta(minutes=1):
            raise ValueError("cadence must be at least one minute")
        self.reads = reads
        self.state = state
        self.cadence = cadence
        self.now = now
        self.audit = audit

    def tick(self) -> bool:
        now = self.now()
        last = self.state.last_run_at()
        if last is not None and now - last < self.cadence:
            return False
        self.run_once(now=now)
        return True

    def run_once(self, *, now: datetime | None = None) -> Mapping[str, int]:
        now = now or self.now()
        summary = {
            "open_seen": 0,
            "matched": 0,
            "identified": 0,
            "recurring": 0,
            "inconclusive": 0,
            "changed": 0,
            "mutations": 0,
        }
        result = self.reads.execute("management.alert.search", {"status": "open"})
        if not _successful(result):
            summary["inconclusive"] += 1
            self.state.mark_run(now)
            return summary
        alerts = _alert_items(result)
        summary["open_seen"] = len(alerts)
        for alert in alerts:
            if not is_time_source_alert(alert):
                continue
            summary["matched"] += 1
            decision = self._classify(alert, now=now)
            if decision is None:
                summary["inconclusive"] += 1
                continue
            summary["identified"] += 1
            if decision.classification == "RECURRING_FAILURE":
                summary["recurring"] += 1
            changed = self.state.put(decision, when=now)
            if changed:
                summary["changed"] += 1
            if self.audit is not None:
                self.audit.record(
                    "autonomy.windows_time_source_shadow",
                    {
                        "alert_uid": decision.alert_uid,
                        "device_uid": decision.device_uid,
                        "hostname": decision.hostname,
                        "site": decision.site,
                        "observed_source": decision.observed_source,
                        "approved_sources": list(decision.approved_sources),
                        "recurrence_count": decision.recurrence_count,
                        "classification": decision.classification,
                        "reason": decision.reason,
                        "changed": changed,
                        "mutated": False,
                    },
                )
        self.state.mark_run(now)
        return summary

    def _classify(
        self,
        alert: Mapping[str, Any],
        *,
        now: datetime,
    ) -> TimeSourceDecision | None:
        source = alert.get("alertSourceInfo")
        source = source if isinstance(source, Mapping) else {}
        alert_uid = str(alert.get("alertUid") or "").strip()
        device_uid = str(source.get("deviceUid") or "").strip()
        hostname = str(source.get("deviceName") or "").strip()
        site = str(source.get("siteName") or "").strip()
        observed, approved = parse_sources(alert)
        if not all((alert_uid, device_uid, hostname, observed)) or not approved:
            return None

        device = self.reads.execute("endpoint.device.read", {"resource_id": device_uid})
        if not _successful(device):
            return None
        record = _evidence(device).get("record")
        if not isinstance(record, Mapping):
            record = _evidence(device)
        resolved_uid = str(
            record.get("resource_id")
            or record.get("uid")
            or record.get("deviceUid")
            or device_uid
        ).strip()
        resolved_host = str(
            record.get("hostname")
            or record.get("hostName")
            or record.get("name")
            or hostname
        ).strip()
        if resolved_uid != device_uid or resolved_host.casefold() != hostname.casefold():
            return None

        history = self.reads.execute(
            "endpoint.alert.history.search",
            {"resource_id": device_uid},
        )
        if not _successful(history):
            return None
        cutoff = now - RECURRENCE_WINDOW
        prior = 0
        for item in _alert_items(history):
            if not is_time_source_alert(item):
                continue
            created = _provider_time(item)
            if created is not None and cutoff <= created <= now:
                prior += 1
        recurrence = prior + 1
        classification = (
            "RECURRING_FAILURE"
            if recurrence >= RECURRENCE_THRESHOLD
            else "CURRENT_TIME_SOURCE_MISMATCH"
        )
        reason = (
            f"{recurrence} matching time-source mismatch episodes in the 30-day window"
            if classification == "RECURRING_FAILURE"
            else f"current source {observed} is outside the approved source set"
        )
        material = {
            "alert_uid": alert_uid,
            "device_uid": device_uid,
            "hostname": hostname,
            "site": site,
            "observed_source": observed,
            "approved_sources": approved,
            "recurrence_count": recurrence,
            "classification": classification,
            "reason": reason,
        }
        fingerprint = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return TimeSourceDecision(
            alert_uid=alert_uid,
            device_uid=device_uid,
            hostname=hostname,
            site=site,
            observed_source=observed,
            approved_sources=approved,
            recurrence_count=recurrence,
            classification=classification,
            reason=reason,
            fingerprint=fingerprint,
        )
