from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from jason_runtime.autonomous_repair_maintenance import (
    AutonomousRepairDeploymentMaintenance,
    GitHubRepairCandidateSource,
)


LIVE = "b" * 40
CANDIDATE = "a" * 40


class Source(GitHubRepairCandidateSource):
    def __init__(self, parent=LIVE):
        super().__init__()
        self.parent = parent

    def _get(self, path):
        if path.startswith("/pulls?"):
            return [
                {
                    "number": 123,
                    "merged_at": "2026-09-28T14:00:00Z",
                    "merge_commit_sha": CANDIDATE,
                    "body": """
- Release class: autonomous-repair-candidate
- Support item: SUPPORT-OPS-023
- Post-deploy verification: Verify repaired behavior.
""",
                }
            ]
        if path == f"/commits/{CANDIDATE}":
            return {"parents": [{"sha": self.parent}, {"sha": "c" * 40}]}
        raise AssertionError(path)


class FakeFactory:
    def __init__(self):
        self.calls = []

    def build(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(capability_name=kwargs["capability_name"])


class FakeOrchestrator:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            status=SimpleNamespace(value="succeeded"),
            error_code=None,
            reason_codes=(),
        )


class AutonomousRepairMaintenanceTests(unittest.TestCase):
    def test_candidate_source_requires_live_first_parent(self):
        found = Source().candidates(live_revision=LIVE)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["candidate_sha"], CANDIDATE)
        self.assertEqual(Source(parent="d" * 40).candidates(live_revision=LIVE), [])

    def test_maintenance_queues_exact_candidate_through_request_factory(self):
        factory = FakeFactory()
        orchestrator = FakeOrchestrator()
        maintenance = AutonomousRepairDeploymentMaintenance(
            request_factory=factory,
            orchestrator=orchestrator,
            source=Source(),
            interval_seconds=300,
            source_revision=LIVE,
            now=lambda: datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(maintenance.tick())
        self.assertEqual(len(factory.calls), 1)
        call = factory.calls[0]
        self.assertEqual(call["capability_name"], "deployment.repair.apply")
        self.assertEqual(call["arguments"]["candidate_sha"], CANDIDATE)
        self.assertEqual(call["arguments"]["rollback_sha"], LIVE)
        self.assertEqual(call["arguments"]["support_item"], "SUPPORT-OPS-023")
        self.assertIsNone(call["standing_policy"])

    def test_maintenance_respects_interval(self):
        maintenance = AutonomousRepairDeploymentMaintenance(
            request_factory=FakeFactory(),
            orchestrator=FakeOrchestrator(),
            source=Source(),
            interval_seconds=300,
            source_revision=LIVE,
            now=lambda: datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(maintenance.tick())
        self.assertFalse(maintenance.tick())


if __name__ == "__main__":
    unittest.main()
