from __future__ import annotations
import base64
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chatgpt_image_tool import ChatGPTImageEvidenceTool
from screen_evidence_intake import AcceptedScreen, ScreenEvidenceIntake
from session_gate import Denied, SessionGate, VerifiedTechnician

FRAME=bytes.fromhex("89504e470d0a1a0a")+b"synthetic-reviewed-only"


class ChatGPTImageToolTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.
        self.user=VerifiedTechnician("staff-a","aot")
        self.allowed={("staff-a","1717088")}
        self.gate=SessionGate(
            identity=lambda x:x,
            can_read_datto_device=lambda p,d:(p.subject,d) in self.allowed,
            clock=lambda:self.now,
        )
        self.session,self.token=self.gate.start(
            trusted_context=self.user,device_uid="1717088",consent=True,
        )
        self.intake=ScreenEvidenceIntake(
            gate=self.gate,
            review_content=lambda image:AcceptedScreen(image,"offline-review","test-only"),
            clock=lambda:self.now,
        )
        self.accepted=self.intake.receive(
            trusted_technician=self.user,
            session_id=self.session.session_id,
            session_token=self.token,
            device_uid="1717088",
            request_nonce="UniqueImageRequest123",
            image=FRAME,
            declared_sha256=hashlib.sha256(FRAME).hexdigest(),
        )
        self.tool=ChatGPTImageEvidenceTool(
            intake=self.intake,
            credential_lookup=lambda sid:self.token if sid==self.session.session_id else None,
        )

    def read(self,**overrides):
        args={
            "authenticated_technician":self.user,
            "session_id":self.session.session_id,
            "device_uid":"1717088",
            "receipt_id":self.accepted.receipt_id,
        }
        args.update(overrides)
        return self.tool.read_reviewed_image(**args)

    def test_exact_reviewed_image_content_returned_to_model_client(self):
        result=self.read()
        self.assertEqual(base64.b64decode(result["image"]["data"]),FRAME)
        self.assertEqual(result["image"]["mimeType"],"image/png")
        self.assertFalse(result["analyzed_by_model"])
        self.assertFalse(result["production_connected"])
        self.assertNotIn(self.token,str(result))

    def test_cross_tenant_user_device_or_receipt_denied(self):
        for invalid in (
            {"authenticated_technician":VerifiedTechnician("staff-b","aot")},
            {"authenticated_technician":VerifiedTechnician("staff-a","other")},
            {"device_uid":"8"},
            {"receipt_id":"SomeOtherValidReceiptName"},
        ):
            with self.subTest(invalid=invalid),self.assertRaises(Denied):
                self.read(**invalid)

    def test_revoked_access_or_expired_image_denied(self):
        self.allowed.clear()
        with self.assertRaises(Denied):self.read()
        self.allowed.add(("staff-a","1717088"))
        self.now+=121
        with self.assertRaises(Denied):self.read()

    def test_missing_server_credential_or_unverified_identity_denied(self):
        no_auth=ChatGPTImageEvidenceTool(intake=self.intake,credential_lookup=lambda sid:None)
        with self.assertRaises(Denied):
            no_auth.read_reviewed_image(
                authenticated_technician=self.user,
                session_id=self.session.session_id,
                device_uid="1717088",receipt_id=self.accepted.receipt_id,
            )
        with self.assertRaises(Denied):
            self.read(authenticated_technician=("staff-a","aot"))


if __name__=="__main__":
    unittest.main()
