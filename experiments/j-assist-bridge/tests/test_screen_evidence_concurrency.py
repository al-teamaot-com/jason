"""Bounded concurrency and memory acceptance for preproduction image intake."""
from __future__ import annotations

import hashlib
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screen_evidence_intake import (
    AcceptedScreen, ScreenEvidenceIntake, MAX_IN_MEMORY_IMAGES,
)
from session_gate import Denied, SessionGate, VerifiedTechnician

PNG = bytes.fromhex("89504e470d0a1a0a") + b"synthetic-no-client-data"
SHA = hashlib.sha256(PNG).hexdigest()


class EvidenceConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.person = VerifiedTechnician("aot-test-staff", "aot")
        self.gate = SessionGate(
            identity=lambda ctx: ctx,
            can_read_datto_device=lambda user, uid:
                user == self.person and uid == "1717088",
            clock=lambda: self.now,
        )
        self.session, self.token = self.gate.start(
            trusted_context=self.person, device_uid="1717088",
            consent=True, lifetime_seconds=300,
        )

    def send(self, intake, nonce):
        return intake.receive(
            trusted_technician=self.person,
            session_id=self.session.session_id,
            session_token=self.token,
            device_uid="1717088",
            request_nonce=nonce,
            image=PNG,
            declared_sha256=SHA,
        )

    def test_concurrent_same_nonce_only_one_review_and_receipt(self):
        entered = threading.Event()
        finish = threading.Event()
        reviews = []
        def reviewer(image):
            reviews.append(image)
            entered.set()
            if not finish.wait(3):
                raise AssertionError("synthetic test release timed out")
            return AcceptedScreen(image, "synthetic-review", "test-v1")
        intake = ScreenEvidenceIntake(
            gate=self.gate, review_content=reviewer, clock=lambda: self.now,
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(self.send, intake, "uniqueConcurrentNonce777")
            self.assertTrue(entered.wait(3))
            with self.assertRaisesRegex(Denied, "replayed"):
                self.send(intake, "uniqueConcurrentNonce777")
            finish.set()
            receipt = first.result(timeout=3)
        self.assertEqual(receipt.image_sha256, SHA)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(len(intake._images), 1)

    def test_failed_review_frees_pending_nonce_no_false_receipt(self):
        fail = [True]
        def reviewer(image):
            if fail[0]:
                raise RuntimeError("simulated DLP outage")
            return AcceptedScreen(image, "synthetic-review", "test-v1")
        intake = ScreenEvidenceIntake(
            gate=self.gate, review_content=reviewer, clock=lambda: self.now,
        )
        with self.assertRaises(Denied):
            self.send(intake, "uniqueFailedReviewNonce99")
        self.assertEqual(len(intake._pending_nonces), 0)
        self.assertEqual(len(intake._images), 0)
        fail[0] = False
        self.assertEqual(
            self.send(intake, "uniqueFailedReviewNonce99").image_sha256, SHA,
        )

    def test_memory_bounded_to_32_unexpired_receipts(self):
        intake = ScreenEvidenceIntake(
            gate=self.gate,
            review_content=lambda img:
                AcceptedScreen(img, "synthetic-review", "test-v1"),
            clock=lambda: self.now,
        )
        for i in range(MAX_IN_MEMORY_IMAGES):
            self.send(intake, "uniqueBoundedNonce%04d" % i)
        self.assertEqual(len(intake._images), MAX_IN_MEMORY_IMAGES)
        with self.assertRaisesRegex(Denied, "capacity"):
            self.send(intake, "uniqueBoundedNonceOverCapacity1")
        self.now += 121
        self.assertEqual(intake.purge_expired(), MAX_IN_MEMORY_IMAGES)
        self.assertEqual(len(intake._images), 0)
        self.send(intake, "uniqueBoundedNonceAfterExpiry")
        self.assertEqual(len(intake._images), 1)
        self.now += 301
        intake.purge_expired()
        self.assertEqual(len(intake._nonces), 0)

if __name__ == "__main__":
    unittest.main()
