"""Runtime bridge for read-only autonomous queue shadow assessment."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from autonomous_remediation.autonomous_principal import AutonomousRequestFactory
from autonomous_remediation.shadow_assessment import ShadowQueueAssessor


class OrchestratorPort(Protocol):
    def execute(self, request: Any) -> Any: ...


class GovernedAutonomyReadPort:
    """Run autonomy reads only through JKD-001 + Central Orchestrator."""

    def __init__(
        self,
        *,
        request_factory: AutonomousRequestFactory,
        orchestrator: OrchestratorPort,
        client_id: str | None = None,
        policy_id: str = "autonomous-shadow-read-v1",
    ) -> None:
        self.request_factory = request_factory
        self.orchestrator = orchestrator
        self.client_id = client_id
        self.policy_id = policy_id

    def execute(
        self,
        capability: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        request = self.request_factory.build_observe(
            capability_name=capability,
            arguments=arguments,
            client_id=self.client_id,
            policy_id=self.policy_id,
        )
        result = self.orchestrator.execute(request)
        return {
            "status": result.status.value,
            "stage": result.stage.value,
            "capability": result.capability_name,
            "provider": result.provider_id,
            "reason_codes": list(result.reason_codes),
            "error_code": result.error_code,
            "correlation_id": result.correlation_id,
            "evidence": (
                dict(result.output)
                if isinstance(result.output, Mapping)
                else {}
            ),
        }


class SQLiteShadowAssessmentStore:
    """Persist bounded shadow-run summaries; never ticket bodies or secrets."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS autonomy_shadow_runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        ran_at TEXT NOT NULL,
        status TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(self.path),
            timeout=10.0,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(self._SCHEMA)
        os.chmod(self.path, 0o600)

    def record_success(self, assessment: Any, *, reasons: tuple[str, ...]) -> None:
        payload = {
            "candidate_count": int(assessment.candidate_count),
            "configured_active_limit": int(assessment.configured_active_limit),
            "selected_for_attention": [
                asdict(item)
                for item in assessment.selected_for_attention
            ],
            "reconcile_reasons": list(reasons),
        }
        self._insert("succeeded", payload)

    def record_failure(
        self,
        *,
        error_type: str,
        error_message: str,
        reasons: tuple[str, ...],
    ) -> None:
        self._insert(
            "failed",
            {
                "error_type": str(error_type)[:120],
                "error_message": str(error_message)[:500],
                "reconcile_reasons": list(reasons),
            },
        )

    def latest(self) -> Mapping[str, Any] | None:
        row = self._connection.execute(
            "SELECT ran_at,status,payload FROM autonomy_shadow_runs "
            "ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "ran_at": row["ran_at"],
            "status": row["status"],
            "payload": json.loads(row["payload"]),
        }

    def close(self) -> None:
        self._connection.close()

    def _insert(self, status: str, payload: Mapping[str, Any]) -> None:
        encoded = json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._connection:
            self._connection.execute(
                "INSERT INTO autonomy_shadow_runs(ran_at,status,payload) "
                "VALUES (?,?,?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    status,
                    encoded,
                ),
            )


class ShadowAutonomyMaintenance:
    """Bounded event/staleness shadow runner.

    service_actions() may call tick frequently; actual reconciliation occurs only
    when due or explicitly requested. Failures are persisted and never crash the
    runtime server.
    """

    def __init__(
        self,
        *,
        assessor: ShadowQueueAssessor,
        store: SQLiteShadowAssessmentStore,
        interval_seconds: int = 1800,
        failure_retry_seconds: int = 300,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if interval_seconds < 60:
            raise ValueError("interval_seconds must be at least 60")
        if not 60 <= failure_retry_seconds <= interval_seconds:
            raise ValueError(
                "failure_retry_seconds must be between 60 and interval_seconds"
            )
        self.assessor = assessor
        self.store = store
        self.interval_seconds = interval_seconds
        self.failure_retry_seconds = failure_retry_seconds
        self.monotonic = monotonic
        self._next_due = 0.0
        self._reasons: set[str] = {"startup"}

    def request_reconcile(self, reason: str) -> None:
        normalized = str(reason or "").strip()
        if not normalized:
            raise ValueError("reconcile reason must be non-empty")
        self._reasons.add(normalized)
        self._next_due = 0.0

    def tick(self) -> bool:
        now = self.monotonic()
        if now < self._next_due:
            return False

        reasons = tuple(sorted(self._reasons)) or ("staleness_budget",)
        self._reasons.clear()
        try:
            assessment = self.assessor.assess()
        except Exception as exc:  # fail closed; runtime remains healthy
            self.store.record_failure(
                error_type=type(exc).__name__,
                error_message=str(exc),
                reasons=reasons,
            )
            self._next_due = now + self.failure_retry_seconds
            return True

        self.store.record_success(assessment, reasons=reasons)
        self._next_due = now + self.interval_seconds
        return True
