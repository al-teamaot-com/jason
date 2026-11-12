from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from session_gate import Denied, SessionGate, VerifiedTechnician
from synthetic_probe import SyntheticProbe, make_probe_request
from chatgpt_session_tool import ChatGPTSessionTool

class ChatGPTSessionToolTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.permissions={("tech-a","12345")}
        self.gate=SessionGate(
            identity=lambda ctx: VerifiedTechnician(*ctx),
            can_read_datto_device=lambda tech, device: (tech.subject,device) in self.permissions,
            clock=lambda: self.now,
        )
        receipt,token=self.gate.start(
            trusted_context=("tech-a","tenant-a"),device_uid="12345",consent=True
        )
        self.sid=receipt.session_id
        self.tokens={self.sid:token}
        result=SyntheticProbe(self.gate).exchange(
            trusted_context=("tech-a","tenant-a"),session_id=self.sid,
            token=token,device_uid="12345",request=make_probe_request("probe0001"),
        )
        self.results={self.sid:result}
        self.tool=ChatGPTSessionTool(
            gate=self.gate,credential_lookup=self.tokens.get,
            synthetic_receipt_lookup=self.results.get,
        )

    def fetch(self,**updates):
        kwargs=dict(authenticated_technician=("tech-a","tenant-a"),
                    session_id=self.sid,device_uid="12345")
        kwargs.update(updates)
        return self.tool.read_synthetic_status(**kwargs)

    def test_chatgpt_read_only_receipt_excludes_secret_and_image(self):
        output=self.fetch()
        self.assertFalse(output["screenshot_analyzed"])
        self.assertFalse(output["live_transport_connected"])
        self.assertEqual(output["inference_billing"],"none")
        self.assertEqual(output["provenance"],"synthetic-test-only")
        self.assertNotIn("token",output)
        self.assertNotIn("image",output)
        self.assertNotIn(self.tokens[self.sid],str(output))

    def test_foreign_technician_and_tenant_denied(self):
        for who in (("tech-b","tenant-a"),("tech-a","tenant-b")):
            with self.subTest(who=who),self.assertRaises(Denied):
                self.fetch(authenticated_technician=who)

    def test_wrong_device_denied(self):
        with self.assertRaises(Denied):
            self.fetch(device_uid="54321")

    def test_revocation_and_expiration_denied(self):
        self.permissions.clear()
        with self.assertRaises(Denied):
            self.fetch()
        self.permissions.add(("tech-a","12345"))
        self.now+=121
        with self.assertRaises(Denied):
            self.fetch()

    def test_missing_credential_and_evidence_denied(self):
        self.tokens.clear()
        with self.assertRaises(Denied):
            self.fetch()
        self.tokens[self.sid]="invalid"
        with self.assertRaises(Denied):
            self.fetch()

    def test_unverified_model_supplied_reference_denied(self):
        with self.assertRaises(Denied):
            self.fetch(session_id="nonexistent")
        with self.assertRaises(Denied):
            self.fetch(session_id="x"*129)

    def test_unsupported_observation_is_not_accepted_as_real_evidence(self):
        from dataclasses import replace
        self.results[self.sid]=replace(self.results[self.sid],observation="I saw a real screenshot")
        with self.assertRaises(Denied):
            self.fetch()

if __name__=="__main__":
    unittest.main()
