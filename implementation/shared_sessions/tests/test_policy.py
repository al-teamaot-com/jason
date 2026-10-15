import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from implementation.shared_sessions.policy import SessionPolicy, SessionRequest

class SessionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "policy.json"
        self.settings = {
            "schema_version": 1, "configuration_version": "test-1", "enabled": False,
            "transports": {"ssh": False}, "modes": {"guided": False}
        }
        self.save()
        self.request = SessionRequest(
            "tenant1", "client1", "target1", "tech1", "ticket1",
            "ssh", "guided", "read_only",
            governed_grant_valid=True, identity_verified=True,
            target_binding_verified=True, execution_transport_approved=True
        )
    def save(self):
        self.path.write_text(json.dumps(self.settings), encoding="utf-8")
    def test_default_denied(self):
        self.assertEqual(SessionPolicy(self.path).decide(self.request).reason, "feature_disabled")
    def test_reload_without_restart(self):
        gate = SessionPolicy(self.path)
        self.settings["enabled"] = True
        self.settings["transports"]["ssh"] = True
        self.settings["modes"]["guided"] = True
        self.save()
        self.assertTrue(gate.decide(self.request).allowed)
        self.settings["enabled"] = False
        self.save()
        self.assertFalse(gate.decide(self.request).allowed)
    def test_missing_grant_denied(self):
        self.settings.update(enabled=True)
        self.settings["transports"]["ssh"] = True
        self.settings["modes"]["guided"] = True
        self.save()
        from dataclasses import replace
        self.assertFalse(SessionPolicy(self.path).decide(replace(self.request, governed_grant_valid=False)).allowed)
        self.assertFalse(SessionPolicy(self.path).decide(replace(self.request, execution_transport_approved=False)).allowed)
        self.assertFalse(SessionPolicy(self.path).decide(replace(self.request, classification="uncertain")).allowed)
        self.assertFalse(SessionPolicy(self.path).decide(replace(self.request, classification="mutating")).allowed)
        self.assertFalse(SessionPolicy(self.path).decide(replace(self.request, classification="sensitive")).allowed)
    def test_corrupt_config_denied(self):
        self.path.write_text("{", encoding="utf-8")
        self.assertFalse(SessionPolicy(self.path).decide(self.request).allowed)

if __name__ == "__main__":
    unittest.main()
