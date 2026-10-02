from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from jason_runtime.autonomous_repair_maintenance import (
    AutonomousRepairDeploymentMaintenance,
    GovernedSourceRepositoryReader,
    RepositoryRepairCandidateSource,
)


LIVE = "b" * 40
CANDIDATE = "a" * 40
REPO = "al-teamaot-com/jason"


class Reads:
    def __init__(self, parent=LIVE):
        self.parent = parent
        self.calls = []

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == "source.repository.pullrequest.search":
            return {
                "data": {
                    "items": [
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
                }
            }
        if capability == "source.repository.commit.read":
            return {
                "data": {
                    "item": {
                        "sha": CANDIDATE,
                        "parents": [self.parent, "c" * 40],
                    }
                }
            }
        raise AssertionError(capability)


def source(parent=LIVE):
    return RepositoryRepairCandidateSource(
        reads=Reads(parent=parent),
        repository=REPO,
    )


class FakeFactory:
    def __init__(self):
        self.calls = []
        self.observe_calls = []

    def build(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(capability_name=kwargs["capability_name"])

    def build_observe(self, **kwargs):
        self.observe_calls.append(kwargs)
        return SimpleNamespace(capability_name=kwargs["capability_name"])


class FakeOrchestrator:
    def __init__(self, output=None):
        self.requests = []
        self.output = output or {}

    def execute(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            status=SimpleNamespace(value="succeeded"),
            error_code=None,
            reason_codes=(),
            output=self.output,
        )


class AutonomousRepairMaintenanceTests(unittest.TestCase):
    def test_candidate_source_requires_live_first_parent(self):
        found = source().candidates(live_revision=LIVE)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["candidate_sha"], CANDIDATE)
        self.assertEqual(source(parent="d" * 40).candidates(live_revision=LIVE), [])

    def test_candidate_source_uses_canonical_repository_reads(self):
        reads = Reads()
        candidate_source = RepositoryRepairCandidateSource(
            reads=reads,
            repository=REPO,
        )
        candidate_source.candidates(live_revision=LIVE)
        self.assertEqual(
            [call[0] for call in reads.calls],
            [
                "source.repository.pullrequest.search",
                "source.repository.commit.read",
            ],
        )
        self.assertEqual(reads.calls[0][1]["repository"], REPO)

    def test_governed_reader_uses_observe_request_factory(self):
        factory = FakeFactory()
        orchestrator = FakeOrchestrator(output={"data": {"items": []}})
        reader = GovernedSourceRepositoryReader(
            request_factory=factory,
            orchestrator=orchestrator,
        )
        output = reader.execute(
            "source.repository.pullrequest.search",
            {"repository": REPO, "state": "closed", "base": "main", "limit": 30},
        )
        self.assertEqual(output["data"]["items"], [])
        self.assertEqual(len(factory.observe_calls), 1)
        self.assertEqual(
            factory.observe_calls[0]["policy_id"],
            "autonomous-repair-source-read-v1",
        )

    def test_maintenance_queues_exact_candidate_through_request_factory(self):
        factory = FakeFactory()
        orchestrator = FakeOrchestrator()
        maintenance = AutonomousRepairDeploymentMaintenance(
            request_factory=factory,
            orchestrator=orchestrator,
            source=source(),
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
            source=source(),
            interval_seconds=300,
            source_revision=LIVE,
            now=lambda: datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(maintenance.tick())
        self.assertFalse(maintenance.tick())


if __name__ == "__main__":
    unittest.main()
