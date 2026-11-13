from __future__ import annotations
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jassist_durable_sessions import DurableJAssistSessionGate
from session_gate import Denied,VerifiedTechnician

KEY=b"k"*32


class DurableSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"sessions.db"
        self.now=1000.0
        self.permission=True
        self.person=VerifiedTechnician("tech-a","aot")
        self.identity=lambda ctx:ctx
        self.authorize=lambda who,uid:self.permission and who==self.person and uid=="1717088"
        self.gate=self.build()

    def build(self,**changed):
        args={"db_path":self.path,"encryption_key":KEY,
              "identity":self.identity,"can_read_datto_device":self.authorize,
              "clock":lambda:self.now}
        args.update(changed)
        return DurableJAssistSessionGate(**args)

    def open(self):
        return self.gate.start(trusted_context=self.person,device_uid="1717088",
                               consent=True)

    def check(self,receipt,secret,**kwargs):
        args={"trusted_context":self.person,"session_id":receipt.session_id,
              "token":secret,"device_uid":"1717088"}
        args.update(kwargs)
        return self.gate.authorize_read(**args)

    def test_encrypted_credentials_persist_across_restart_and_not_in_sqlite(self):
        receipt,token=self.open()
        self.check(receipt,token)
        second=self.build()
        self.assertEqual(second.credential_for(receipt.session_id),token)
        second.authorize_read(trusted_context=self.person,session_id=receipt.session_id,
                              token=token,device_uid="1717088")
        self.assertNotIn(token.encode(),self.path.read_bytes())
        self.assertNotIn(token,self.path.read_text(errors="ignore"))
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)

    def test_missing_consent_wrong_device_wrong_identity_fail(self):
        for consent in (False,None,"true",1):
            with self.subTest(consent=consent),self.assertRaises(Denied):
                self.gate.start(trusted_context=self.person,
                                device_uid="1717088",consent=consent)
        with self.assertRaises(Denied):
            self.gate.start(trusted_context=self.person,
                            device_uid="9999",consent=True)
        receipt,token=self.open()
        for changed in ({"device_uid":"9999"},{"token":"wrong"},
                        {"trusted_context":VerifiedTechnician("other","aot")}):
            with self.subTest(changed=changed),self.assertRaises(Denied):
                self.check(receipt,token,**changed)

    def test_group_revocation_persistently_closes_session(self):
        receipt,token=self.open()
        self.permission=False
        with self.assertRaises(Denied):self.check(receipt,token)
        self.permission=True
        with self.assertRaises(Denied):self.check(receipt,token)
        self.assertIsNone(self.gate.credential_for(receipt.session_id))

    def test_stop_expiry_and_durable_event_metadata(self):
        receipt,token=self.open()
        self.gate.stop(trusted_context=self.person,session_id=receipt.session_id,
                       token=token,device_uid="1717088")
        with self.assertRaises(Denied):self.check(receipt,token)
        with sqlite3.connect(self.path) as db:
            events=db.execute("SELECT event_type FROM jassist_session_events WHERE session_id=? ORDER BY event_id",
                              (receipt.session_id,)).fetchall()
        self.assertEqual(events,[("opened",),("closed",)])
        receipt,token=self.open()
        self.now=receipt.expires_at+1
        with self.assertRaises(Denied):self.check(receipt,token)
        self.assertIsNone(self.gate.credential_for(receipt.session_id))
        self.assertEqual(self.gate.purge_expired(),2)

    def test_invalid_key_and_unsafe_path_refused(self):
        with self.assertRaises(ValueError):self.build(encryption_key=b"short")
        with self.assertRaises(Denied):
            self.build(encryption_key=b"z"*32).credential_for(self.open()[0].session_id)
        self.path.chmod(0o666)
        with self.assertRaises(ValueError):self.build()


if __name__=="__main__":unittest.main()
