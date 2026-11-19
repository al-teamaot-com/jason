"""Isolated source-only Windows Time JSON classifier on the legacy cadence.

Reuses existing legacy SQLiteWindowsTimeSourceShadowState and its deterministic
alert filtering, and the new JSON reader/projection. This is NOT installed as a
new production scheduler or dispatch path. Its role is per-playbook synthetic
legacy-vs-JSON sweep acceptance prior to an approved cutover.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from autonomous_remediation.json_shadow_integration import JsonShadowBoundaryError
from .windows_time_source_shadow import (
    SQLiteWindowsTimeSourceShadowState, _alert_items, is_time_source_alert,
)
from .json_windows_time_preprod import build_windows_time_json_readonly_preprod
from .json_windows_time_projection import project_windows_time_json_decision


class WindowsTimeJsonIsolatedSweep:
    def __init__(
        self, *,
        isolated_root: Path,
        client_id: str,
        verified_site: str,
        request_factory: Any,
        orchestrator: Any,
        state: SQLiteWindowsTimeSourceShadowState,
        clock,
        cadence: timedelta = timedelta(minutes=15),
        max_alerts_per_sweep: int = 40,
        audit=None,
    ) -> None:
        if cadence < timedelta(minutes=1):
            raise ValueError("TIME_SOURCE_CADENCE_TOO_SHORT")
        if not 1 <= max_alerts_per_sweep <= 100:
            raise ValueError("TIME_SOURCE_ALERT_LIMIT_INVALID")
        if not client_id.strip() or not verified_site.strip():
            raise JsonShadowBoundaryError("TIME_SOURCE_TRUSTED_SITE_SCOPE_MISSING")
        self.root = Path(isolated_root)
        self.client_id = client_id
        self.verified_site = verified_site
        self.request_factory = request_factory
        self.orchestrator = orchestrator
        self.state = state
        self.clock = clock
        self.cadence = cadence
        self.max_alerts = max_alerts_per_sweep
        self.audit = audit

    def tick(self) -> bool:
        now = self.clock()
        last = self.state.last_run_at()
        if last is not None and now - last < self.cadence:
            return False
        self.run_once(now=now)
        return True

    def run_once(self, *, now: datetime) -> Mapping[str, int]:
        """One bounded synthetic shadow sweep, never a production dispatcher."""
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise JsonShadowBoundaryError("TIME_SOURCE_SWEEP_CLOCK_REQUIRED")
        from .autonomy_shadow_runtime import GovernedAutonomyReadPort
        reads = GovernedAutonomyReadPort(
            request_factory=self.request_factory,
            orchestrator=self.orchestrator,
            client_id=self.client_id,
            policy_id="json-migration-readonly-preprod-v1",
        )
        response = reads.execute("management.alert.search", {"status": "open"})
        summary = {
            "open_seen": 0, "matched": 0, "identified": 0,
            "recurring": 0, "waiting_device_access": 0,
            "inconclusive": 0, "changed": 0, "mutations": 0,
        }
        if response.get("status") != "succeeded":
            summary["inconclusive"] = 1
            self.state.mark_run(now)
            return summary
        alerts = _alert_items(response)
        summary["open_seen"] = len(alerts)
        matches = [alert for alert in alerts if is_time_source_alert(alert)]
        # A larger provider page must not be truncated silently: require an
        # explicit bounded recovery strategy and do not mutate or claim
        # successful completion when the batch exceeds the approved limit.
        if len(matches) > self.max_alerts:
            raise JsonShadowBoundaryError("TIME_SOURCE_ALERT_BATCH_LIMIT")
        seen: set[str] = set()
        for alert in matches:
            summary["matched"] += 1
            alert_uid = str(alert.get("alertUid") or "").strip()
            if not alert_uid or alert_uid in seen:
                summary["inconclusive"] += 1
                continue
            seen.add(alert_uid)
            source = alert.get("alertSourceInfo")
            if not isinstance(source, Mapping) or (
                str(source.get("siteName") or "").strip().casefold()
                != self.verified_site.casefold()
            ):
                summary["inconclusive"] += 1
                continue
            runner = build_windows_time_json_readonly_preprod(
                enabled=True,
                isolated_root=self.root,
                client_id=self.client_id,
                client_site_binding=self.verified_site,
                request_factory=self.request_factory,
                orchestrator=self.orchestrator,
                clock=lambda: now,
            )
            try:
                result = runner.run(
                    run_id=f"time-source-json:{alert_uid}:{now.isoformat()}",
                    client_id=self.client_id,
                    target_id=alert_uid,
                    trusted_seed={
                        "client_id": self.client_id, "target_id": alert_uid,
                    },
                )
                changed = project_windows_time_json_decision(
                    result=result, state=self.state, at=now,
                    audit=self.audit,
                )
                if changed is None:
                    summary["inconclusive"] += 1
                    continue
                summary["identified"] += 1
                if result.facts["classification"] == "RECURRING_FAILURE":
                    summary["recurring"] += 1
                if result.facts["classification"] == "WAITING_DEVICE_ACCESS":
                    summary["waiting_device_access"] += 1
                if changed:
                    summary["changed"] += 1
            finally:
                runner.state.close()
        self.state.mark_run(now)
        return summary
