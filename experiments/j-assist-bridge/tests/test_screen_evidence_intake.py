from __future__ import annotations
from dataclasses import replace
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from screen_evidence_intake import (
    AcceptedScreen, ScreenEvidenceIntake, MAX_IMAGE_BYTES,
)
from session_gate import Denied, SessionGate, VerifiedTechnician

FRAME = bytes.fromhex("89504e470d0a1a0a") + b"synthetic-test-image-only"
def digest(raw):
    return hashlib.sha256(raw).hexdigest()

class ScreenEvidenceIntakeTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.allowed = {("staff-a", "1717088")}
        self.person = VerifiedTechnician("staff-a", "aot")
        self.gate = SessionGate(
            identity=lambda ctx: ctx,
            can_read_datto_device=lambda person,device:
                (person.subject,device) in self.allowed,
            clock=lambda: self.now,
        )
        self.receipt, self.token = self.gate.start(
            trusted_context=self.person, device_uid="1717088", consent=True,
        )
        self.reviews=[]
        def review(raw):
            self.reviews.append(raw)
            return AcceptedScreen(raw, "test-reviewer", "offline-test-v1")
        self.intake = ScreenEvidenceIntake(gate=self.gate,
            review_content=review, clock=lambda: self.now)

    def send(self, **overrides):
        args={
            "trusted_technician":self.person,
            "session_id":self.receipt.session_id,
            "session_token":self.token,
            "device_uid":"1717088",
            "request_nonce":"uniqueFrameRequest01",
            "image":FRAME,
            "declared_sha256":digest(FRAME),
        }
        args.update(overrides)
        return self.intake.receive(**args)

    def test_receipt_and_readback_are_bound_to_session(self):
        receipt=self.send()
        self.assertEqual(receipt.image_sha256,digest(FRAME))
        self.assertEqual(receipt.bytes_accepted,len(FRAME))
        self.assertFalse(receipt.analyzed_by_model)
        record,original=self.intake.retrieve(
            trusted_technician=self.person,session_id=self.receipt.session_id,
            session_token=self.token,device_uid="1717088",
            receipt_id=receipt.receipt_id,
        )
        self.assertEqual(record,receipt)
        self.assertEqual(original,FRAME)

    def test_missing_review_or_rejection_denies_receipt(self):
        for reviewer in (lambda raw:None,
                         lambda raw: (_ for _ in ()).throw(RuntimeError("DLP offline"))):
            with self.subTest(reviewer=reviewer):
                service=ScreenEvidenceIntake(gate=self.gate,review_content=reviewer)
                with self.assertRaises(Denied):
                    service.receive(
                        trusted_technician=self.person,
                        session_id=self.receipt.session_id,
                        session_token=self.token,device_uid="1717088",
                        request_nonce="uniqueFrameRequest01",
                        image=FRAME,declared_sha256=digest(FRAME),
                    )

    def test_wrong_hash_oversize_or_invalid_image_denied(self):
        for change in (
            {"declared_sha256":"a"*64},
            {"image":b"x"*(MAX_IMAGE_BYTES+1)},
            {"image":b"not-an-image","declared_sha256":digest(b"not-an-image")},
            {"request_nonce":"short"},
        ):
            with self.subTest(change=list(change)):
                with self.assertRaises(Denied):
                    self.send(**change)

    def test_replay_denied(self):
        self.send()
        with self.assertRaises(Denied):
            self.send()

    def test_wrong_person_device_revoked_permission_denied(self):
        self.send()
        for change in (
            {"trusted_technician":VerifiedTechnician("staff-b","aot")},
            {"trusted_technician":VerifiedTechnician("staff-a","other")},
            {"device_uid":"123"},
        ):
            with self.subTest(change=change),self.assertRaises(Denied):
                self.send(request_nonce="AnotherUniqueNonce20",**change)
        self.allowed.clear()
        with self.assertRaises(Denied):
            self.send(request_nonce="AnotherUniqueNonce30")

    def test_review_not_invoked_if_not_authorized(self):
        self.allowed.clear()
        with self.assertRaises(Denied):
            self.send()
        self.assertEqual(self.reviews,[])

    def test_expiry_and_purge(self):
        accepted=self.send()
        self.now += 121
        self.assertEqual(self.intake.purge_expired(),1)
        with self.assertRaises(Denied):
            self.intake.retrieve(
                trusted_technician=self.person,
                session_id=self.receipt.session_id,
                session_token=self.token,device_uid="1717088",
                receipt_id=accepted.receipt_id,
            )

    def test_permission_revoked_during_review_denies(self):
        def revoke(raw):
            self.allowed.clear()
            return AcceptedScreen(raw,"test-reviewer","offline-test-v1")
        intake=ScreenEvidenceIntake(gate=self.gate,review_content=revoke)
        with self.assertRaises(Denied):
            intake.receive(
                trusted_technician=self.person,session_id=self.receipt.session_id,
                session_token=self.token,device_uid="1717088",
                request_nonce="uniqueFrameRequest01",image=FRAME,
                declared_sha256=digest(FRAME),
            )

if __name__=="__main__":
    unittest.main()
