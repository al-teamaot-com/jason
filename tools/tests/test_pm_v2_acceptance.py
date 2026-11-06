from pathlib import Path
import unittest

from pm_v2.acceptance import inspect_acceptance_matrix


ROOT = Path(__file__).resolve().parents[2]


class PMV2AcceptanceTests(unittest.TestCase):
    def test_every_canonical_requirement_has_source_and_external_evidence_definition(self):
        result = inspect_acceptance_matrix(
            repo=ROOT,
            matrix_path=ROOT / "config" / "pm-v2-acceptance-matrix.json",
        )
        self.assertEqual(result["requirement_count"], 20)
        self.assertEqual(result["source_implemented_count"], 20)
        self.assertEqual(result["source_implementation_percent"], 100.0)
        self.assertIn("not end-to-end acceptance", result["note"])
