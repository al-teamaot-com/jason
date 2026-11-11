"""Deterministic source and optional offline-state checks for staged OC specialists."""
from __future__ import annotations

import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "config/openclaw-specialists"
REQUIRED = {"j-compliance", "j-docs", "j-observe", "j-qa", "j-integrations", "j-release"}


class SpecialistProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((SOURCE / "manifest.json").read_text())
        cls.profiles = cls.manifest["agents"]

    def test_scope_and_models(self):
        self.assertEqual(self.manifest["activation"], "disabled")
        self.assertEqual(self.manifest["coordinator"], "j-man")
        self.assertEqual(self.manifest["production_release_controller"], "existing-pmv3.2-release-manager")
        self.assertFalse(self.manifest["api_fallback_allowed"])
        self.assertEqual(self.manifest["existing_agents_unchanged"], ["main", "j-man", "j-dev"])
        self.assertEqual({p["id"] for p in self.profiles}, REQUIRED)
        self.assertEqual(len(self.profiles), len(REQUIRED))
        self.assertEqual(len({p["workspace"] for p in self.profiles}), len(REQUIRED))
        for p in self.profiles:
            self.assertEqual(p["model"], "openai/gpt-5.6-sol")
            self.assertEqual(p["mode"], "preproduction-only")
            self.assertEqual(p["channel_bindings"], [])
            self.assertIs(p["auto_dispatch"], False)
            self.assertIs(p["production_write_authority"], False)

    def test_role_profiles_and_reused_contract(self):
        shared = (SOURCE / "shared/AGENT-CONTRACT.md").read_text()
        self.assertIn("no new approval requirement", shared)
        self.assertIn("Core services", shared)
        self.assertIn("never a separately billed API key", shared)
        for p in self.profiles:
            agent_file = SOURCE / p["agent_instructions"]
            identity_file = SOURCE / p["identity"]
            self.assertTrue(agent_file.is_file(), p["id"])
            self.assertTrue(identity_file.is_file(), p["id"])
            instruction = agent_file.read_text()
            self.assertIn(p["id"], instruction)
            self.assertIn("../_shared/AGENT-CONTRACT.md", instruction)
            self.assertIn("no automatic routing", instruction)
            self.assertIn("no standing production rights", instruction)
            self.assertNotIn("@teamaot.com", instruction)
        self.assertTrue((ROOT/"docs/operations/OpenClaw-Specialist-Agent-Staging.md").is_file())

    def test_optional_isolated_state(self):
        loc = os.environ.get("JASON_OPENCLAW_OFFLINE_STATE")
        if not loc:
            self.skipTest("No isolated state provided in CI; source checks still run")
        state=Path(loc)
        cfg=json.loads((state/"openclaw.json").read_text())
        found={x["id"]: x for x in cfg.get("agents",{}).get("list",[])}
        self.assertEqual(set(found), REQUIRED | {"main"})
        self.assertFalse(cfg.get("bindings"))
        for p in self.profiles:
            aid=p["id"]
            self.assertEqual(found[aid].get("model"), p["model"])
            self.assertTrue((state/"workspaces"/aid/"AGENTS.md").is_file())
            self.assertTrue((state/"workspaces"/aid/"IDENTITY.md").is_file())
        self.assertTrue((state/"workspaces/_shared/AGENT-CONTRACT.md").is_file())
        # No subscription tokens, passwords, or API credentials in offline state.
        for forbidden in ("apiKey", "accessToken", "refreshToken", "api_key", "password"):
            self.assertNotIn(forbidden, (state/"openclaw.json").read_text())


if __name__ == "__main__":
    unittest.main()
