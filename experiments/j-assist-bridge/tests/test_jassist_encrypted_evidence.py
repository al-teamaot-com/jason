from __future__ import annotations
from dataclasses import replace
import hashlib
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jassist_durable_sessions import DurableJAssistSessionGate
from jassist_encrypted_evidence import EncryptedJAssistEvidenceIntake
from screen_evidence_intake import AcceptedScreen
from session_gate import Denied,VerifiedTechnician

JPEG=bytes.fromhex("ffd8ffe000104a46494600")+b"non-sensitive synthetic frame"+bytes.fromhex("ffd9")


class EncryptedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.session_db=root/"sessions.db"
        self.image_db=root/"evidence.db"
        self.now=1000.0
        self.authorized=True
        self.person=VerifiedTechnician("staff-a","aot")
        self.gate=DurableJAssistSessionGate(
            db_path=self.session_db,encryption_key=b"k"*32,
            identity=lambda x:x,clock=lambda:self.now,
            can_read_datto_device=lambda p,d:self.authorized
            and p==self.person and d=="1717088")
        self.session,self.token=self.gate.start(
            trusted_context=self.person,device_uid="1717088",consent=True)
        self.reviewer=lambda raw:AcceptedScreen(raw,"approved-reviewer-fixture","fixture-v1")
        self.intake=self.build()

    def build(self,**kwargs):
        args={"db_path":self.image_db,"encryption_key":b"e"*32,
              "gate":self.gate,"review_content":self.reviewer,
              "clock":lambda:self.now}
        args.update(kwargs)
        return EncryptedJAssistEvidenceIntake(**args)

    def receive(self,nonce="UniqueSyntheticNonce123",**kwargs):
        args={"trusted_technician":self.person,"session_id":self.session.session_id,
              "session_token":self.token,"device_uid":"1717088",
              "request_nonce":nonce,"image":JPEG,
              "declared_sha256":hashlib.sha256(JPEG).hexdigest()}
        args.update(kwargs)
        return self.intake.receive(**args)

    def retrieve(self,receipt,**kwargs):
        args={"trusted_technician":self.person,"session_id":self.session.session_id,
              "session_token":self.token,"device_uid":"1717088",
              "receipt_id":receipt.receipt_id}
        args.update(kwargs)
        return self.intake.retrieve(**args)

    def test_encrypted_at_rest_and_cross_process_receipt_retrieval(self):
        receipt=self.receive()
        self.assertEqual(self.retrieve(receipt)[1],JPEG)
        self.assertNotIn(JPEG,self.image_db.read_bytes())
        after_restart=self.build()
        read=after_restart.retrieve(trusted_technician=self.person,
            session_id=self.session.session_id,session_token=self.token,
            device_uid="1717088",receipt_id=receipt.receipt_id)
        self.assertEqual(read[0].image_sha256,hashlib.sha256(JPEG).hexdigest())
        self.assertEqual(read[1],JPEG)
        self.assertEqual(self.image_db.stat().st_mode&0o777,0o600)

    def test_replay_rejected_after_new_intake_instance(self):
        self.receive()
        self.intake=self.build()
        with self.assertRaises(Denied):self.receive()
        self.receive(nonce="AnotherSyntheticNonce789")

    def test_revoked_identity_or_device_prevents_receipt_retrieval(self):
        receipt=self.receive()
        self.authorized=False
        with self.assertRaises(Denied):self.retrieve(receipt)
        self.authorized=True
        with self.assertRaises(Denied):self.retrieve(receipt)
        # Session gate records revocation, not an arbitrary one-time check.
        self.assertIsNone(self.gate.credential_for(self.session.session_id))

    def test_cross_user_and_device_isolation(self):
        receipt=self.receive()
        with self.assertRaises(Denied):
            self.retrieve(receipt,trusted_technician=VerifiedTechnician("other","aot"))
        with self.assertRaises(Denied):
            self.retrieve(receipt,device_uid="9999")

    def test_failed_dlp_or_modified_image_blocks_and_nonce_can_retry(self):
        self.reviewer=lambda raw:(_ for _ in ()).throw(ValueError("restricted content"))
        self.intake=self.build()
        with self.assertRaises(Denied):self.receive()
        self.reviewer=lambda raw:AcceptedScreen(raw+b"bad","reviewer","v2")
        self.intake=self.build()
        with self.assertRaises(Denied):self.receive()
        self.reviewer=lambda raw:AcceptedScreen(raw,"approved-reviewer","v3")
        self.intake=self.build()
        receipt=self.receive()
        self.assertEqual(self.retrieve(receipt)[1],JPEG)

    def test_wrong_hash_size_and_key_rejected(self):
        with self.assertRaises(Denied):self.receive(declared_sha256="a"*64)
        with self.assertRaises(Denied):self.receive(image=b"notjpeg")
        with self.assertRaises(ValueError):self.build(encryption_key=b"short")
        receipt=self.receive()
        different=self.build(encryption_key=b"z"*32)
        with self.assertRaises(Denied):
            different.retrieve(trusted_technician=self.person,
                session_id=self.session.session_id,session_token=self.token,
                device_uid="1717088",receipt_id=receipt.receipt_id)

    def test_expired_purged(self):
        receipt=self.receive()
        self.now=receipt.expires_at+1
        with self.assertRaises(Denied):self.retrieve(receipt)
        self.assertEqual(self.intake.purge_expired(),1)

    def test_replay_concurrency_only_one_receipt(self):
        results=[]
        def try_send():
            try:results.append(("ok",self.receive()))
            except Denied:results.append(("denied",None))
        jobs=[threading.Thread(target=try_send) for _ in range(2)]
        for job in jobs:job.start()
        for job in jobs:job.join()
        self.assertEqual(sorted(x[0] for x in results),["denied","ok"])


if __name__=="__main__":unittest.main()
