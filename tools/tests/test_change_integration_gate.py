import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "change_integration_gate.py"
SPEC = importlib.util.spec_from_file_location("change_integration_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gate)


class ChangeIntegrationGateTests(unittest.TestCase):
    def test_sensitive_paths(self):
        self.assertTrue(gate.sensitive("implementation/runtime_service/app.py"))
        self.assertTrue(gate.sensitive(".github/workflows/validate.yml"))
        self.assertTrue(gate.sensitive("CONTRIBUTING.md"))
        self.assertFalse(gate.sensitive("docs/sessions/proof.md"))

    def test_parse_acknowledged_bulleted_template_line(self):
        body = """
## Integration coordination

- Integration coordination: #123, #456
"""
        self.assertEqual(gate.parse_acknowledged(body), {123, 456})

    def test_parse_acknowledged_none(self):
        self.assertEqual(gate.parse_acknowledged("- Integration coordination: none"), set())


if __name__ == "__main__":
    unittest.main()
