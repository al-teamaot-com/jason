from pathlib import Path
import json
import tempfile
import unittest

from pm_v2.failure_corpus import FailureCorpusError, validate_failure_corpus


ROOT = Path(__file__).resolve().parents[2]


class PMV2FailureCorpusTests(unittest.TestCase):
    def test_canonical_v1_failure_corpus_maps_every_failure_to_a_test(self):
        result = validate_failure_corpus(
            repo=ROOT,
            path=ROOT / "config" / "pm-v2-v1-failure-corpus.json",
        )
        self.assertEqual(result["status"], "pass")
        self.assertGreaterEqual(result["failure_count"], 13)

    def test_missing_regression_symbol_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            test = root / "test.py"
            test.write_text("def test_real(): pass\n", encoding="utf-8")
            corpus = root / "corpus.json"
            corpus.write_text(json.dumps({
                "schema_version": "1.0",
                "failures": [{
                    "id": "X",
                    "symptom": "x",
                    "correction": "y",
                    "test_file": "test.py",
                    "test_symbol": "test_missing"
                }]
            }), encoding="utf-8")
            with self.assertRaises(FailureCorpusError):
                validate_failure_corpus(repo=root, path=corpus)
