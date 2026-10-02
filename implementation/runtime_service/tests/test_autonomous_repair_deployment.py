from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from jason_runtime.autonomous_repair_deployment import (
    AUTONOMOUS_REPAIR_PROFILE,
    AUTONOMOUS_REPAIR_PROFILE_ENV,
    AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,
    DEPLOYMENT_REPAIR_APPLY,
    DEPLOYMENT_REPAIR_STATUS,
    AutonomousRepairDeploymentInvoker,
    register_autonomous_repair_deployment_foundation,
)


CANDIDATE = "a" * 40
ROLLBACK = "b" * 40


def request(*, principal="jason-autonomy-worker", permission="execute", execution="exec-1"):
    return SimpleNamespace(
        principal_id=principal,
        organization_id="aot",
        execution_id=execution,
        correlation_id="corr-1",
        capability_name=DEPLOYMENT_REPAIR_APPLY,
        permission_mode=permission,
        arguments={
            "candidate_sha": CANDIDATE,
            "rollback_sha": ROLLBACK,
            "support_item": "SUPPORT-OPS-023",
            "pr_number": 123,
            "post_deploy_verification": "Verify repaired orchestration write path.",
        },
    )


def resolution(capability=DEPLOYMENT_REPAIR_APPLY):
    return SimpleNamespace(
        selected_provider_id=AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,
        capability_name=capability,
    )


class AutonomousRepairDeploymentTests(unittest.TestCase):
    def test_profile_activation_is_fail_closed(self):
        capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
        providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(AUTONOMOUS_REPAIR_PROFILE_ENV, None)
            state = register_autonomous_repair_deployment_foundation(
                capabilities=capabilities,
                providers=providers,
                now=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )
        self.assertFalse(state.enabled)
        self.assertEqual(
            capabilities.get(capability_name=DEPLOYMENT_REPAIR_APPLY, version="1.0").lifecycle_status.value,
            "building",
        )

    def test_exact_profile_activates_status_but_keeps_production_apply_blocked(self):
        capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
        providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
        with patch.dict(os.environ, {AUTONOMOUS_REPAIR_PROFILE_ENV: AUTONOMOUS_REPAIR_PROFILE}):
            state = register_autonomous_repair_deployment_foundation(
                capabilities=capabilities,
                providers=providers,
                now=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )
        self.assertTrue(state.enabled)
        apply_capability = capabilities.get(capability_name=DEPLOYMENT_REPAIR_APPLY, version="1.0")
        self.assertEqual(apply_capability.lifecycle_status.value, "building")
        self.assertTrue(apply_capability.approval.required)
        self.assertEqual(
            capabilities.get_current(capability_name=DEPLOYMENT_REPAIR_STATUS).lifecycle_status.value,
            "active",
        )
        self.assertEqual(state.capability_names, (DEPLOYMENT_REPAIR_STATUS,))

    def test_only_autonomous_workload_can_queue(self):
        with tempfile.TemporaryDirectory() as td:
            invoker = AutonomousRepairDeploymentInvoker(Path(td))
            with self.assertRaises(PermissionError):
                invoker.invoke(
                    request=request(principal="person-al"),
                    resolution=resolution(),
                )

    def test_queue_is_durable_and_idempotent_across_execution_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            invoker = AutonomousRepairDeploymentInvoker(root)
            first = invoker.invoke(request=request(execution="exec-1"), resolution=resolution())
            second = invoker.invoke(request=request(execution="exec-2"), resolution=resolution())
            first_id = first.output["data"]["request_id"]
            second_id = second.output["data"]["request_id"]
            self.assertEqual(first_id, second_id)
            queued = list((root / "requests").glob("*.json"))
            self.assertEqual(len(queued), 1)
            payload = json.loads(queued[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["candidate_sha"], CANDIDATE)
            self.assertEqual(payload["rollback_sha"], ROLLBACK)
            self.assertFalse(first.output["data"]["host_mutation_performed"])

    def test_status_reads_bounded_result(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            invoker = AutonomousRepairDeploymentInvoker(root)
            queued = invoker.invoke(request=request(), resolution=resolution())
            request_id = queued.output["data"]["request_id"]
            result_dir = root / "results"
            result_dir.mkdir(parents=True)
            (result_dir / f"{request_id}.json").write_text(
                json.dumps(
                    {
                        "state": "succeeded",
                        "candidate_sha": CANDIDATE,
                        "rollback_sha": ROLLBACK,
                        "support_item": "SUPPORT-OPS-023",
                        "live_revision": CANDIDATE,
                        "verification_passed": True,
                        "rollback_performed": False,
                    }
                ),
                encoding="utf-8",
            )
            status_request = SimpleNamespace(
                permission_mode="observe",
                capability_name=DEPLOYMENT_REPAIR_STATUS,
                arguments={"request_id": request_id},
            )
            result = invoker.invoke(
                request=status_request,
                resolution=resolution(DEPLOYMENT_REPAIR_STATUS),
            )
            self.assertEqual(result.output["data"]["state"], "succeeded")
            self.assertEqual(result.output["data"]["live_revision"], CANDIDATE)

    def test_candidate_must_differ_from_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            invoker = AutonomousRepairDeploymentInvoker(Path(td))
            bad = request()
            bad.arguments["candidate_sha"] = ROLLBACK
            with self.assertRaises(ValueError):
                invoker.invoke(request=bad, resolution=resolution())


if __name__ == "__main__":
    unittest.main()
