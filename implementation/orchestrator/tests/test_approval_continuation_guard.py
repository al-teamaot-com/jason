from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.approval_continuation_guard import (
    ApprovalContinuationClaim,
    InMemoryApprovalContinuationGuard,
    SQLiteApprovalContinuationGuard,
)

NOW = datetime(2026, 8, 9, 18, 0, tzinfo=timezone.utc)


def claim(**overrides) -> ApprovalContinuationClaim:
    values = dict(
        approval_id="apr-1",
        organization_id="org-a",
        request_id="req-1",
        correlation_id="corr-1",
        capability="microsoft.resource.execute",
        authority_context_id="ctx-1",
        claimed_at=NOW,
    )
    values.update(overrides)
    return ApprovalContinuationClaim(**values)


class InMemoryGuardTests(unittest.TestCase):
    def test_first_claim_succeeds_and_replay_fails(self) -> None:
        guard = InMemoryApprovalContinuationGuard()
        guard.claim(claim())
        with self.assertRaises(PermissionError):
            guard.claim(claim())

    def test_cross_tenant_reuse_fails_closed(self) -> None:
        guard = InMemoryApprovalContinuationGuard()
        guard.claim(claim())
        with self.assertRaisesRegex(PermissionError, "tenant mismatch"):
            guard.claim(claim(organization_id="org-b"))

    def test_naive_timestamp_is_rejected(self) -> None:
        guard = InMemoryApprovalContinuationGuard()
        with self.assertRaises(ValueError):
            guard.claim(claim(claimed_at=datetime(2026, 8, 9, 18, 0)))


class SQLiteGuardTests(unittest.TestCase):
    def test_claim_survives_restart_and_blocks_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "continuations.sqlite3")
            first = SQLiteApprovalContinuationGuard(path)
            first.initialize()
            first.claim(claim())

            reopened = SQLiteApprovalContinuationGuard(path)
            reopened.initialize()
            with self.assertRaises(PermissionError):
                reopened.claim(claim())

    def test_cross_tenant_reuse_is_distinguished(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "continuations.sqlite3")
            guard = SQLiteApprovalContinuationGuard(path)
            guard.initialize()
            guard.claim(claim())
            with self.assertRaisesRegex(PermissionError, "tenant mismatch"):
                guard.claim(claim(organization_id="org-b"))


if __name__ == "__main__":
    unittest.main()
