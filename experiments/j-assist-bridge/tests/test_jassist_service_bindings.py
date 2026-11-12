from __future__ import annotations
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from datto_administrator_authority import DattoSecurityLevelEvidence
from jassist_service_bindings import prepare_live_bindings
from session_gate import Denied, VerifiedTechnician


class ServiceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"jassist.json"
        self.policy={"schema_version":1,"revision":1,"enabled":True,
            "access_source":"datto_rmm_assigned_security_level",
            "aot_account_uid":"aot-account",
            "required_security_level":"Administrator",
            "scope":"screen_assistance",
            "approval_record":"APPROVED-TEST-ONLY"}
        self.save()
        self.person=VerifiedTechnician("trusted-oid","aot")
        self.calls=[]
        self.proof=DattoSecurityLevelEvidence(
            technician_subject="trusted-oid",technician_tenant="aot",
            account_uid="aot-account",datto_username="tech@example.test",
            assigned_security_levels=("Administrator",),
            assignment_verified=True,user_enabled=True,provider_verified=True,
            verified_at=time.time())
    def save(self):
        tmp=self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.policy))
        tmp.chmod(0o600)
        tmp.replace(self.path)
    def build(self, **changes):
        args={
            "settings_path":self.path,"datto_account_uid":"aot-account",
            "identity":lambda ctx:self.person,
            "datto_level_evidence":lambda person:self.proof,
            "datto_device_in_account":lambda acct,device:self.calls.append((acct,device)) or device=="12345",
        }
        args.update(changes)
        return prepare_live_bindings(**args)
    def test_live_services_gate_verified_consent_and_read(self):
        gate=self.build()
        receipt,token=gate.start(trusted_context=object(),device_uid="12345",consent=True)
        gate.authorize_read(trusted_context=object(),session_id=receipt.session_id,
                            token=token,device_uid="12345")
        self.assertEqual(self.calls,[("aot-account","12345"),("aot-account","12345")])
    def test_missing_real_services_denied(self):
        for key in ("settings_path","datto_account_uid","identity",
                    "datto_level_evidence","datto_device_in_account"):
            with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):
                self.build(**{key:None})
    def test_unapproved_policy_or_missing_proof_denied(self):
        self.policy["enabled"]=False
        self.save()
        gate=self.build()
        with self.assertRaises(Denied):
            gate.start(trusted_context=object(),device_uid="12345",consent=True)
        self.policy["enabled"]=True
        self.save()
        self.proof=None
        with self.assertRaises(Denied):
            gate.start(trusted_context=object(),device_uid="12345",consent=True)
    def test_revocation_mid_session_from_config_and_datto(self):
        gate=self.build()
        receipt,token=gate.start(trusted_context=object(),device_uid="12345",consent=True)
        self.policy.update(enabled=False,revision=2,approval_record="APPROVED-TEST-REVOCATION")
        self.save()
        with self.assertRaises(Denied):
            gate.authorize_read(trusted_context=object(),session_id=receipt.session_id,
                                token=token,device_uid="12345")
        self.policy.update(enabled=True,revision=3,approval_record="APPROVED-TEST-RESTORE")
        self.save()
        receipt,token=gate.start(trusted_context=object(),device_uid="12345",consent=True)
        self.proof=None
        with self.assertRaises(Denied):
            gate.authorize_read(trusted_context=object(),session_id=receipt.session_id,
                                token=token,device_uid="12345")
    def test_wrong_account_never_initializes(self):
        self.policy["aot_account_uid"]="other-account"
        self.save()
        with self.assertRaises(ValueError):
            self.build()


if __name__=="__main__":
    unittest.main()
