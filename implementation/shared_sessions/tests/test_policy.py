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

class SessionPolicyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'policy.json'
        self.config = {'schema_version': 1, 'configuration_version': 'boundary-1', 'enabled': True,
                       'transports': {'ssh': True}, 'modes': {'guided': True}}
        self.save()
        self.request = SessionRequest('tenant', 'client', 'target', 'tech', 'ticket', 'ssh', 'guided', 'read_only',
                    governed_grant_valid=True, identity_verified=True, target_binding_verified=True,
                    execution_transport_approved=True)

    def save(self):
        self.path.write_text(json.dumps(self.config), encoding='utf-8')

    def test_missing_context_denies_each_required_binding(self):
        from dataclasses import replace
        for field in ('tenant_id', 'client_id', 'target_id', 'technician_id', 'ticket_id'):
            with self.subTest(field=field):
                self.assertFalse(SessionPolicy(self.path).decide(replace(self.request, **{field: ''})).allowed)

    def test_missing_independent_evidence_denies(self):
        from dataclasses import replace
        for field in ('governed_grant_valid', 'identity_verified', 'target_binding_verified', 'execution_transport_approved'):
            with self.subTest(field=field):
                self.assertFalse(SessionPolicy(self.path).decide(replace(self.request, **{field: False})).allowed)

    def test_mutation_requires_specific_approval_and_uncertainty_always_denies(self):
        from dataclasses import replace
        gate = SessionPolicy(self.path)
        self.assertFalse(gate.decide(replace(self.request, classification='mutating')).allowed)
        self.assertTrue(gate.decide(replace(self.request, classification='mutating', specific_change_approval=True)).allowed)
        self.assertFalse(gate.decide(replace(self.request, classification='uncertain', specific_change_approval=True,
                                            separate_sensitive_grant=True)).allowed)

    def test_sensitive_requires_separate_grant(self):
        from dataclasses import replace
        gate = SessionPolicy(self.path)
        self.assertFalse(gate.decide(replace(self.request, classification='sensitive')).allowed)
        self.assertTrue(gate.decide(replace(self.request, classification='sensitive', separate_sensitive_grant=True)).allowed)

    def test_invalid_configuration_denies(self):
        for replacement in ({'enabled': 'true'}, {'transports': {'unknown': True}},
                            {'modes': {'guided': 1}}, {'schema_version': 999}):
            with self.subTest(replacement=replacement):
                config = self.config | replacement
                self.path.write_text(json.dumps(config), encoding='utf-8')
                self.assertFalse(SessionPolicy(self.path).decide(self.request).allowed)

    def test_disabled_mode_transport_and_unknown_command_denied(self):
        from dataclasses import replace
        gate = SessionPolicy(self.path)
        self.assertFalse(gate.decide(replace(self.request, mode='autonomous')).allowed)
        self.assertFalse(gate.decide(replace(self.request, transport='winrm')).allowed)
        self.assertFalse(gate.decide(replace(self.request, classification='other')).allowed)

    def test_truthy_non_boolean_attestations_fail_closed(self):
        from dataclasses import replace
        self.assertFalse(SessionPolicy(self.path).decide(
            replace(self.request, identity_verified='false')).allowed)
        self.assertFalse(SessionPolicy(self.path).decide(
            replace(self.request, governed_grant_valid=1)).allowed)
        self.assertFalse(SessionPolicy(self.path).decide(
            replace(self.request, tenant_id=123)).allowed)
