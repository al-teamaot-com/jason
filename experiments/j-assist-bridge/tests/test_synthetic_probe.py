from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from session_gate import Denied, SessionGate, VerifiedTechnician
from synthetic_probe import SyntheticProbe, make_probe_request


class SyntheticProbeTests(unittest.TestCase):
    def setUp(self):
        self.now=1000
        self.permissions={("tech-a","12345")}
        self.gate=SessionGate(
            identity=lambda ctx: VerifiedTechnician(*ctx),
            can_read_datto_device=lambda person, device: (person.subject,device) in self.permissions,
            clock=lambda: self.now,
        )
        self.receipt,self.token=self.gate.start(
            trusted_context=("tech-a","tenant-a"), device_uid="12345", consent=True
        )
        self.probe=SyntheticProbe(self.gate)

    def exchange(self, **overrides):
        args=dict(trusted_context=("tech-a","tenant-a"),session_id=self.receipt.session_id,
                  token=self.token,device_uid="12345",request=make_probe_request("probe0001"))
        args.update(overrides)
        return self.probe.exchange(**args)

    def test_synthetic_round_trip(self):
        result=self.exchange()
        self.assertEqual(result.session_id,self.receipt.session_id)
        self.assertEqual(result.sequence,1)
        self.assertIn("no screen was analyzed",result.observation)
        self.assertEqual(len(result.evidence_sha256),64)

    def test_replay_fails_closed(self):
        self.exchange()
        with self.assertRaises(Denied):
            self.exchange()

    def test_foreign_technician_tenant_device_denied(self):
        for update in (
            {"trusted_context":("tech-b","tenant-a")},
            {"trusted_context":("tech-a","tenant-b")},
            {"device_uid":"67890"},
            {"token":"bad"},
        ):
            with self.subTest(update=update),self.assertRaises(Denied):
                self.exchange(**update)

    def test_revoke_expire_stop(self):
        self.permissions.clear()
        with self.assertRaises(Denied):
            self.exchange()
        self.permissions.add(("tech-a","12345"))
        self.now+=121
        with self.assertRaises(Denied):
            self.exchange()

    def test_content_frames_and_schema_extensions_rejected(self):
        for invalid in (
            b'{"version":1,"kind":"synthetic_probe","marker":"SCREENSHOT","request_id":"probe0001"}',
            b'{"version":1,"kind":"synthetic_probe","marker":"JASSIST_SYNTHETIC_TEST_FRAME_V1","request_id":"probe0001","image":"sensitive"}',
            b'not-json',
            b'x'*2049,
        ):
            with self.subTest(invalid=invalid[:32]),self.assertRaises(Denied):
                self.exchange(request=invalid)

    def test_independent_sessions_can_reuse_request_id(self):
        other,token=self.gate.start(
            trusted_context=("tech-a","tenant-a"),device_uid="12345",consent=True
        )
        self.exchange()
        second=self.exchange(session_id=other.session_id,token=token)
        self.assertEqual(second.sequence,1)
