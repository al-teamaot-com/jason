from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from pm_v2.config import ConfigError, load_config


ROOT = Path(__file__).resolve().parents[2]
AGREEMENT = ROOT / "docs/operations/Production-Manager-V2-Goal-Scope-and-Success-Agreement.md"
EXPECTED = "4debf8d43ce200b2f61abad8bf281bbfd6ccf313f78b8534a0e96b77098a1f0c"


class PMV2CanonicalAgreementTests(unittest.TestCase):
    def test_canonical_agreement_matches_approved_hash_and_config(self):
        self.assertEqual(hashlib.sha256(AGREEMENT.read_bytes()).hexdigest(), EXPECTED)
        raw = json.loads((ROOT / "config/pm-v2.json").read_text())
        self.assertEqual(raw["scope"]["canonical_agreement_sha256"], EXPECTED)
        config = load_config(ROOT / "config/pm-v2.json", repo=ROOT)
        self.assertEqual(config.canonical_agreement_sha256, EXPECTED)

    def test_modified_agreement_fails_config_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            agreement = root / "agreement.md"
            agreement.write_text("changed", encoding="utf-8")
            # Exercise only the scope validator through a full minimal config.
            raw = json.loads((ROOT / "config/pm-v2.json").read_text())
            raw["scope"] = {
                "canonical_agreement_path": "agreement.md",
                "canonical_agreement_sha256": EXPECTED,
            }
            # Point other repo-relative sources to available temporary files.
            (root / "roadmap.md").write_text("", encoding="utf-8")
            (root / "SUPPORT.md").write_text("", encoding="utf-8")
            raw["sources"] = {
                "roadmap_path": "roadmap.md",
                "support_path": "SUPPORT.md",
            }
            path = root / "config.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path, repo=root)
