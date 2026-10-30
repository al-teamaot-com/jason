"""Positive and deliberate-negative acceptance for engineering standards gate."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("engineering_standards_gate", ROOT / "tools" / "engineering_standards_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class EngineeringStandardsAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = (ROOT / gate.REGISTRY).read_text()
        cls.agents = (ROOT / gate.AGENTS).read_text()

    def test_approved_instructions_pass(self):
        self.assertEqual(gate.validate(self.registry, self.agents), [])

    def test_removed_standard_fails(self):
        broken = self.registry.replace("## JES-004", "## DELETED")
        self.assertIn("JES-004 must have exactly one heading", gate.validate(broken, self.agents))

    def test_missing_ai_bootstrap_fails(self):
        self.assertTrue(gate.validate(self.registry, "No instructions"))

    def test_missing_owner_action_fails(self):
        broken = self.registry.replace("What you need to do:", "Owner field removed")
        self.assertTrue(any("What you need to do" in v for v in gate.validate(broken, self.agents)))


if __name__ == "__main__":
    unittest.main()
