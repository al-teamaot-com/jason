"""Deterministic DRMM diagnostic source/build safety and completeness checks."""
import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "source"
OUTPUT = ROOT / "components"
COMPONENTS = ["windows-snapshot", "disk-space-analysis", "network-dns"]
FORBIDDEN = (
    r"\bRestart-Computer\b", r"\bStop-Computer\b", r"\bRestart-Service\b",
    r"\bStop-Service\b", r"\bStart-Service\b", r"\bSet-Service\b",
    r"\bRemove-Item\b", r"\bSet-Item\b", r"\bNew-Item\b",
    r"\bClear-DnsClientCache\b", r"\bSet-DnsClientServerAddress\b",
    r"\bRepair-ComputerSecureChannel\b", r"\bReset-NetAdapter\b",
    r"\bDisable-NetAdapter\b", r"\bEnable-NetAdapter\b",
    r"\bInvoke-Expression\b", r"\bInvoke-WebRequest\b",
    r"\bInvoke-RestMethod\b", r"\bStart-Process\b",
    r"\bmsiexec(?:\.exe)?\b", r"\bSet-ExecutionPolicy\b",
)


class TestComponents(unittest.TestCase):
    def test_generated_artifacts_match_sources(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertTrue(manifest["read_only"])
        self.assertEqual(manifest["default_enrollment"], "not_enabled")
        self.assertEqual(len(manifest["components"]), 3)
        common = (SOURCES / "common.ps1").read_text()
        for i, key in enumerate(COMPONENTS):
            code = (OUTPUT / (key + ".ps1")).read_text()
            source = (SOURCES / (key + ".ps1")).read_text()
            self.assertIn(common, code)
            self.assertIn(source, code)
            self.assertEqual(manifest["components"][i]["sha256"],
                             hashlib.sha256(code.encode()).hexdigest())
            self.assertIsNone(manifest["components"][i]["datto_component_uid"])

    def test_sources_do_not_contain_disruptive_commands(self):
        # Ignore comments; deliberately conservative denylist, not a security proof.
        for path in SOURCES.glob("*.ps1"):
            source = "\n".join(line for line in path.read_text().splitlines()
                               if not line.lstrip().startswith("#"))
            for pattern in FORBIDDEN:
                self.assertIsNone(re.search(pattern, source, re.I),
                                  msg=f"{path.name} contains prohibited pattern {pattern}")

    def test_all_have_common_report_contract(self):
        common = (SOURCES / "common.ps1").read_text()
        for marker in ("schema_version", "overall_status", "collection_utc",
                       "AOT_DIAGNOSTIC_JSON_BEGIN", "AOT_DIAGNOSTIC_JSON_END",
                       "incomplete", "not_applicable", "unavailable", "duration_ms"):
            self.assertIn(marker, common)
        for key in COMPONENTS:
            source = (SOURCES / (key + ".ps1")).read_text()
            self.assertIn("New-AotReport", source)
            self.assertIn("Invoke-AotSection", source)
            self.assertIn("Write-AotReport $report", source)
            self.assertNotIn("exit 1", source)

    def test_bounded_collection(self):
        disk = (SOURCES / "disk-space-analysis.ps1").read_text()
        for needle in ("$maxFiles", "$maxTotalScanSeconds", "$maxFoldersPerVolume",
                       "skippedLinks", "GetAttributes", "file_budget", "time_budget"):
            self.assertIn(needle, disk)
        network = (SOURCES / "network-dns.ps1").read_text()
        for needle in ("QuickTimeout", "WaitOne($TimeoutMs)",
                       "Select-Object -First", "DiagTargetHost"):
            self.assertIn(needle, network)

    def test_build_is_repeatable(self):
        before = [(OUTPUT / (x + ".ps1")).read_bytes() for x in COMPONENTS]
        subprocess.run(["python3", str(ROOT / "build.py")], check=True, capture_output=True)
        after = [(OUTPUT / (x + ".ps1")).read_bytes() for x in COMPONENTS]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
