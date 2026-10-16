"""CCC scheduled-source readiness must not poison runtime drift or release controls."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import ccc_runner, run_ccc

SOURCE = "a" * 40
RUNTIME = "b" * 40
NOW = datetime(2026, 10, 16, 19, 20, tzinfo=timezone.utc)
MANDATORY = (
    "checker-currentness", "runtime-source-alignment",
    "material-change-owner-review", "j002-article-matrix", "system-registry",
    "j900-release-validation", "mcp-constitutional-production-equivalent",
    "systemd-failed-units", "prometheus-targets", "openclaw-authority-health",
    "immutable-runtime-release", "mcp-governance-boundary",
    "governed-provider-boundary-canaries",
)


def pending_report(*, override=None):
    statuses = {name: "PASS" for name in MANDATORY}
    statuses.update({
        "runtime-source-alignment": "NOT_PROVEN",
        "material-change-owner-review": "NOT_PROVEN",
    })
    statuses.update(override or {})
    return {
        "schema_version": "1.0", "status": "NOT_PROVEN",
        "trigger": "material_change", "source_revision": SOURCE,
        "runtime_revision": RUNTIME, "material_changes": ["implementation/runtime_service/"],
        "checks": [{"check_id": k, "status": v} for k, v in statuses.items()],
    }


class ScheduledSourcePendingTests(unittest.TestCase):
    def _evaluate(self, report, *, force=False, trigger="scheduled", git_rc=0):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.json"
            path.write_text(json.dumps(report))
            result = SimpleNamespace(
                status=report["status"],
                source_revision=report.get("source_revision"),
                runtime_revision=report.get("runtime_revision"),
                report_path=path,
            )
            config = SimpleNamespace(repository_root=Path(td))
            with patch.object(run_ccc.subprocess, "run",
                              return_value=subprocess.CompletedProcess([], git_rc)) as ancestry:
                accepted = run_ccc._scheduled_source_change_pending(
                    result, config, force=force, trigger=trigger,
                )
                if accepted:
                    ancestry.assert_called_once()
            return accepted

    def test_pending_new_source_is_successful_observation_not_certification(self):
        self.assertTrue(self._evaluate(pending_report()))

    def test_actual_control_failure_still_fails(self):
        self.assertFalse(self._evaluate(pending_report(override={"prometheus-targets": "FAIL"})))

    def test_missing_authority_or_unknown_exception_still_fails(self):
        self.assertFalse(self._evaluate(pending_report(override={"provider-boundary": "NOT_PROVEN"})))
        self.assertFalse(self._evaluate(pending_report(override={"j002-article-matrix": "NOT_PROVEN"})))

    def test_forced_release_candidate_never_gets_pending_exception(self):
        self.assertFalse(self._evaluate(pending_report(), force=True))
        self.assertFalse(self._evaluate(pending_report(), trigger="material_change"))

    def test_divergent_or_nonancestor_source_fails(self):
        self.assertFalse(self._evaluate(pending_report(), git_rc=1))
        report = pending_report()
        report["runtime_revision"] = SOURCE
        self.assertFalse(self._evaluate(report))

    def test_missing_mandatory_check_never_gets_exception(self):
        report = pending_report()
        report["checks"] = [
            item for item in report["checks"]
            if item["check_id"] != "governed-provider-boundary-canaries"
        ]
        self.assertFalse(self._evaluate(report))

    def test_overall_fail_never_gets_exception(self):
        report = pending_report()
        report["status"] = "FAIL"
        self.assertFalse(self._evaluate(report))


class ScheduledWatchdogFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.runner = ccc_runner.CCCRunner(
            SimpleNamespace(repository_root=Path("/test-repo")),
            checker_revision=RUNTIME, now=lambda: NOW,
        )
        self.failed = ccc_runner.CheckResult(
            "systemd-failed-units", "FAIL", "external_failed_units=1",
            {"failed_units": [
                "● jason-production-drift-watchdog.service loaded failed failed Jason Production Desired-State Drift Watchdog"
            ]},
        )

    def _reconcile(self, problems, *, age=30, status="drift_detected", checks=None):
        observed = (NOW - timedelta(seconds=age)).isoformat()
        report = {"status": status, "observed_at": observed, "problems": problems}
        with patch.object(Path, "read_text", return_value=json.dumps(report)):
            return self.runner._reconcile_scheduled_watchdog_feedback(checks or [self.failed])

    def test_known_feedback_is_explicitly_documented_but_does_not_certify(self):
        problems = [{"kind": "failed_system_unit", "unit": "jason-ccc.service", "state": "failed"}]
        result = self._reconcile(problems)
        self.assertEqual(result[0].status, "PASS")
        self.assertIn("historical_watchdog_feedback", result[0].evidence)

    def test_new_failure_or_stale_feedback_still_fails(self):
        expected = [{"kind": "failed_system_unit", "unit": "jason-ccc.service", "state": "failed"}]
        for problems, age in (
            (expected, 301),
            (expected + [{"kind": "unexpected_unit"}], 30),
            ([{"kind": "failed_system_unit", "unit": "jason-runtime.service", "state": "failed"}], 30),
        ):
            with self.subTest(problems=problems, age=age):
                self.assertEqual(self._reconcile(problems, age=age)[0].status, "FAIL")

    def test_unrelated_failed_watchdog_without_provenance_still_fails(self):
        with patch.object(Path, "read_text", side_effect=OSError("no evidence")):
            result = self.runner._reconcile_scheduled_watchdog_feedback([self.failed])
        self.assertEqual(result[0].status, "FAIL")
