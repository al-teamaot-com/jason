from __future__ import annotations
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jassist_access_policy import JAssistDattoAccessPolicy, FileBackedJAssistPolicyReader
from datto_administrator_authority import DattoAdministratorScreenAuthorizer, DattoAdministratorEvidence
from session_gate import VerifiedTechnician, SessionGate, Denied


def policy():
    return {
        "schema_version": 1,
        "revision": 1,
        "enabled": True,
        "access_source": "datto_rmm_assigned_security_level",
        "aot_account_uid": "aot-native-datto-account",
        "required_security_level": "Administrator",
        "scope": "screen_assistance",
        "approval_record": "AOT-JASSIST-20261111",
    }


class JAssistConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/"access-policy.json"
        self.write(policy())
        self.reader = FileBackedJAssistPolicyReader(self.path)

    def write(self, data):
        # Mimic an owner-controlled settings service's atomic publication.
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data))
        temp.chmod(0o600)
        temp.replace(self.path)

    def test_default_is_data_and_loaded_dynamically(self):
        first = self.reader()
        self.assertEqual(first.required_security_level, "Administrator")
        self.assertEqual(first.revision, 1)
        replacement = {**policy(), "required_security_level":"Tier 2",
                       "revision":2, "approval_record":"AOT-JASSIST-20261111-B"}
        self.write(replacement)
        current = self.reader()
        self.assertEqual(current.required_security_level, "Tier 2")
        self.assertEqual(current.revision, 2)

    def test_live_authorizer_hot_reload_without_restart(self):
        tech = VerifiedTechnician("tech-a", "aot")
        current = DattoAdministratorEvidence("tech-a", "aot", "aot-native-datto-account",
                    "tech@example.test", ("Administrator",), True, True, True, 1000.0)
        authorizer = DattoAdministratorScreenAuthorizer(
            aot_account_uid="aot-native-datto-account",
            access_policy_for=self.reader, evidence_for=lambda p: current,
            device_in_account=lambda a,d: a == "aot-native-datto-account" and d == "10001",
            clock=lambda:1010.0,
        )
        self.assertTrue(authorizer(tech,"10001"))
        self.write({**policy(), "required_security_level":"Tier 2", "revision":2,
                    "approval_record":"AOT-JASSIST-20261111-B"})
        self.assertFalse(authorizer(tech,"10001"))
        current = replace(current,assigned_security_levels=("Tier 2",))
        self.assertTrue(authorizer(tech,"10001"))
        self.write({**policy(),"enabled":False,"revision":3,
                    "approval_record":"AOT-JASSIST-20261111-C"})
        self.assertFalse(authorizer(tech,"10001"))

    def test_existing_session_is_revoked_when_policy_changes(self):
        tech=VerifiedTechnician("tech-a","aot")
        proof=DattoAdministratorEvidence("tech-a","aot","aot-native-datto-account",
              "tech@example.test",("Administrator",),True,True,True,1000.0)
        auth=DattoAdministratorScreenAuthorizer(
            aot_account_uid="aot-native-datto-account",
            access_policy_for=self.reader,
            evidence_for=lambda p:proof,
            device_in_account=lambda a,d:d=="10001",
            clock=lambda:1010.0,
        )
        gate=SessionGate(identity=lambda ctx:tech,can_read_datto_device=auth,clock=lambda:1010.0)
        receipt,secret=gate.start(trusted_context=object(),device_uid="10001",consent=True)
        gate.authorize_read(trusted_context=object(),session_id=receipt.session_id,
                            token=secret,device_uid="10001")
        self.write({**policy(),"revision":2,"enabled":False,
                    "approval_record":"AOT-JASSIST-20261111-B"})
        with self.assertRaises(Denied):
            gate.authorize_read(trusted_context=object(),session_id=receipt.session_id,
                                token=secret,device_uid="10001")

    def test_missing_corrupt_or_untrusted_file_deny(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError): self.reader()
        self.path.write_text("{broken JSON")
        self.path.chmod(0o600)
        with self.assertRaises(ValueError): self.reader()
        self.write(policy())
        self.path.chmod(0o666)
        with self.assertRaises(ValueError): self.reader()
        self.path.unlink()
        self.path.symlink_to(Path(self.folder.name)/"target")
        with self.assertRaises(ValueError): self.reader()

    def test_rejects_ambiguous_duplicate_or_oversized_json(self):
        self.path.write_text('{"revision":1,"revision":2}')
        self.path.chmod(0o600)
        with self.assertRaises(ValueError): self.reader()
        self.path.write_text(" " * 4097)
        self.path.chmod(0o600)
        with self.assertRaises(ValueError): self.reader()

    def test_rejects_incomplete_unsafe_and_unapproved_shapes(self):
        base = policy()
        for changed in [
            {"required_security_level":"*"},
            {"required_security_level":"all"},
            {"required_security_level":"Administrator "},
            {"required_security_level":""},
            {"revision":0},
            {"revision":True},
            {"enabled":1},
            {"scope":"powershell"},
            {"access_source":"entra_group_claim"},
            {"schema_version":2},
            {"approval_record":""},
            {"aot_account_uid":""},
            {"unexpected":True},
        ]:
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                JAssistDattoAccessPolicy.from_mapping({**base,**changed})
        with self.assertRaises(ValueError):
            JAssistDattoAccessPolicy.from_mapping({k:v for k,v in base.items()
                                                   if k != "required_security_level"})

    def test_requires_trusted_absolute_settings_path(self):
        with self.assertRaises(ValueError):
            FileBackedJAssistPolicyReader("relative-policy.json")


if __name__ == "__main__":
    unittest.main()
