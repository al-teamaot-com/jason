import importlib.util
import json
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "canonical_capability_boundary_gate.py"
SPEC = importlib.util.spec_from_file_location("canonical_capability_boundary_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "canonical-capability-boundary.json"


class CanonicalCapabilityBoundaryGateTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def test_workflow_caller_direct_connector_import_fails(self):
        source = "from connectors.autotask.connector import AutotaskConnector\n"
        violations = gate.inspect_python(
            "implementation/runtime_service/src/jason_runtime/example_workflow.py",
            source,
            self.policy,
        )
        self.assertTrue(any(v.rule == "direct_provider_import" for v in violations))

    def test_workflow_caller_direct_http_fails(self):
        source = (
            "from urllib.request import urlopen\n"
            "def run():\n"
            "    return urlopen('https://provider.invalid')\n"
        )
        violations = gate.inspect_python(
            "implementation/runtime_service/src/jason_runtime/example_flow.py",
            source,
            self.policy,
        )
        self.assertTrue(any(v.rule == "direct_provider_import" for v in violations))
        self.assertTrue(any(v.rule == "direct_provider_call" for v in violations))

    def test_workflow_canonical_action_is_allowed(self):
        source = (
            "def run(actions, scope):\n"
            "    return actions.execute(scope, 'service.ticket.update', {'payload': {}})\n"
        )
        violations = gate.inspect_python(
            "implementation/runtime_service/src/jason_runtime/example_workflow.py",
            source,
            self.policy,
        )
        self.assertEqual(violations, [])

    def test_provider_boundary_may_import_connector(self):
        source = "from connectors.autotask.connector import AutotaskConnector\n"
        violations = gate.inspect_python(
            "implementation/runtime_service/src/jason_runtime/autotask_example.py",
            source,
            self.policy,
        )
        self.assertEqual(violations, [])

    def test_noncaller_helper_is_not_reclassified_by_filename_agnostic_guess(self):
        source = "from urllib.request import urlopen\n"
        violations = gate.inspect_python(
            "implementation/runtime_service/src/jason_runtime/provider_reads.py",
            source,
            self.policy,
        )
        self.assertEqual(violations, [])

    def test_analysis_module_is_a_caller_boundary(self):
        self.assertTrue(
            gate.is_caller(
                "implementation/runtime_service/src/jason_runtime/low_disk_analysis.py",
                self.policy,
            )
        )

    def test_provider_specific_runtime_module_is_boundary(self):
        self.assertTrue(
            gate.is_provider_boundary(
                "implementation/runtime_service/src/jason_runtime/datto_component_execution.py",
                self.policy,
            )
        )


if __name__ == "__main__":
    unittest.main()
