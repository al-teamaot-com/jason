from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from implementation.shared_sessions.durable_events import SqliteSessionEventLedger
from implementation.shared_sessions.lifecycle import SessionLifecycle
from session_gate import Denied, SessionGate, VerifiedTechnician
from shared_session_adapter import SharedSessionAdapter


class SharedSessionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1000.0
        self.user = VerifiedTechnician("technician-x", "aot")
        self.allowed = {("technician-x", "1717088")}
        self.gate = SessionGate(
            identity=lambda obj: obj,
            can_read_datto_device=lambda p, d: (p.subject, d) in self.allowed,
            clock=lambda: self.now,
        )
        self.ledger = SqliteSessionEventLedger(os.path.join(self.tmp.name, "ledger.sqlite"))
        self.lifecycle = SessionLifecycle(self.ledger)
        self.adapter = SharedSessionAdapter(gate=self.gate, lifecycle=self.lifecycle)

    def open(self):
        return self.adapter.start(
            technician=self.user, device_uid="1717088",
            ticket_id="T20261106.0001", consent=True,
        )

    def test_open_inspect_close_persists_shared_ledger(self):
        session = self.open()
        result = self.adapter.inspect(
            technician=self.user,
            session_id=session.receipt.session_id,
            credential=session.session_credential,
            device_uid="1717088",
        )
        self.assertEqual(result["state"], "active")
        self.assertFalse(result["screen_analyzed"])
        self.adapter.close(
            technician=self.user,
            session_id=session.receipt.session_id,
            credential=session.session_credential,
            device_uid="1717088",
        )
        events = self.ledger.history(tenant_id="aot", session_id=session.receipt.session_id)
        self.assertEqual([event.kind for event in events], ["session_opened", "session_closed"])
        self.assertTrue(self.ledger.verify(tenant_id="aot", session_id=session.receipt.session_id))
        with self.assertRaises(Denied):
            self.adapter.inspect(
                technician=self.user, session_id=session.receipt.session_id,
                credential=session.session_credential, device_uid="1717088",
            )

    def test_cross_technician_cannot_read(self):
        session = self.open()
        with self.assertRaises(Denied):
            self.adapter.inspect(
                technician=VerifiedTechnician("other", "aot"),
                session_id=session.receipt.session_id,
                credential=session.session_credential,
                device_uid="1717088",
            )

    def test_permission_revocation_cannot_read(self):
        session = self.open()
        self.allowed.clear()
        with self.assertRaises(Denied):
            self.adapter.inspect(
                technician=self.user, session_id=session.receipt.session_id,
                credential=session.session_credential, device_uid="1717088",
            )

    def test_consent_and_ticket_are_required(self):
        for changes in ({"consent": False}, {"ticket_id": ""}):
            with self.subTest(changes=changes), self.assertRaises(Denied):
                self.adapter.start(
                    technician=self.user, device_uid="1717088",
                    ticket_id=changes.get("ticket_id", "T20261106.0001"),
                    consent=changes.get("consent", True),
                )

    def test_expiration_cannot_read(self):
        session = self.open()
        self.now += 121
        with self.assertRaises(Denied):
            self.adapter.inspect(
                technician=self.user, session_id=session.receipt.session_id,
                credential=session.session_credential, device_uid="1717088",
            )


if __name__ == "__main__":
    unittest.main()
