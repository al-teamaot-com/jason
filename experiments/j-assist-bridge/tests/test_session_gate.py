from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from session_gate import Denied, SessionGate, VerifiedTechnician


class SessionGateTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.permissions = {("tech-a", "1717088")}
        self.gate = SessionGate(
            identity=lambda ctx: VerifiedTechnician(ctx[0], ctx[1]),
            can_read_datto_device=lambda p, d: (p.subject, d) in self.permissions,
            clock=lambda: self.now,
        )

    def start(self):
        receipt, token = self.gate.start(
            trusted_context=("tech-a", "aot"), device_uid="1717088", consent=True
        )
        return receipt.session_id, token

    def ack(self, sid, token, **kwargs):
        defaults=dict(trusted_context=("tech-a", "aot"), session_id=sid,
                      token=token, device_uid="1717088", event="heartbeat")
        defaults.update(kwargs)
        return self.gate.acknowledge_metadata(**defaults)

    def test_authorized_explicit_consent(self):
        sid, token=self.start()
        self.assertEqual(self.ack(sid, token), 1)
        self.assertEqual(self.ack(sid, token), 2)

    def test_consent_is_mandatory(self):
        with self.assertRaises(Denied):
            self.gate.start(trusted_context=("tech-a","aot"),device_uid="1717088",consent=False)

    def test_native_device_authority_required(self):
        with self.assertRaises(Denied):
            self.gate.start(trusted_context=("tech-b","aot"),device_uid="1717088",consent=True)

    def test_no_cross_technician_or_tenant_replay(self):
        sid,token=self.start()
        for principal in [("tech-b","aot"),("tech-a","foreign")]:
            with self.assertRaises(Denied):
                self.ack(sid,token,trusted_context=principal)

    def test_wrong_device_and_token_denied(self):
        sid,token=self.start()
        for changes in [{"device_uid":"9"},{"token":"bad"}]:
            with self.assertRaises(Denied):
                self.ack(sid,changes.get("token",token),**{k:v for k,v in changes.items() if k!="token"})

    def test_stopped_and_expired_sessions_fail_closed(self):
        sid,token=self.start()
        self.gate.stop(trusted_context=("tech-a","aot"),session_id=sid,token=token,device_uid="1717088")
        with self.assertRaises(Denied):
            self.ack(sid,token)
        sid,token=self.start()
        self.now+=121
        with self.assertRaises(Denied):
            self.ack(sid,token)

    def test_permission_revocation_ends_session(self):
        sid,token=self.start()
        self.permissions.clear()
        with self.assertRaises(Denied):
            self.ack(sid,token)

    def test_raw_content_rejected(self):
        sid,token=self.start()
        with self.assertRaises(Denied):
            self.ack(sid,token,bytes_sent=1)
        with self.assertRaises(Denied):
            self.ack(sid,token,event="frame")

    def test_invalid_identity_and_device_rejected(self):
        with self.assertRaises(Denied):
            self.gate.start(trusted_context=("tech-a","aot"),device_uid="1717088/../",consent=True)
        with self.assertRaises(Denied):
            self.gate.start(trusted_context=("","aot"),device_uid="1717088",consent=True)

    def test_lifetime_bound(self):
        with self.assertRaises(Denied):
            self.gate.start(trusted_context=("tech-a","aot"),device_uid="1717088",consent=True,lifetime_seconds=301)


if __name__ == "__main__":
    unittest.main()
