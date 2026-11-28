from __future__ import annotations

import http.client
import json
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loopback_transport import create_loopback_server
from session_gate import SessionGate, VerifiedTechnician
from synthetic_probe import SyntheticProbe, MARKER


class LoopbackTransportTests(unittest.TestCase):
    def setUp(self):
        self.permissions = {("tech-a", "12345")}
        self.now = 1000
        self.gate = SessionGate(
            identity=lambda ctx: VerifiedTechnician(*ctx),
            can_read_datto_device=lambda p, d: (p.subject, d) in self.permissions,
            clock=lambda: self.now,
        )
        self.receipt, self.token = self.gate.start(
            trusted_context=("tech-a", "aot"), device_uid="12345", consent=True
        )
        self.probe = SyntheticProbe(self.gate)
        self.identity_tokens = {"dev-identity-token": ("tech-a", "aot")}
        self.server = create_loopback_server(
            probe=self.probe, authenticate=self.identity_tokens.get
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def post(self, *, auth="dev-identity-token", overrides=None):
        body = {
            "session_id": self.receipt.session_id,
            "session_token": self.token,
            "device_uid": "12345",
            "probe": {
                "version": 1,
                "kind": "synthetic_probe",
                "marker": MARKER,
                "request_id": "uniqueprobe123",
            },
        }
        body.update(overrides or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=3)
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer " + auth
        connection.request("POST", "/v1/synthetic-probe", json.dumps(body).encode(), headers)
        response = connection.getresponse()
        code = response.status
        raw = response.read()
        connection.close()
        return code, raw

    def test_real_http_round_trip_synthetic_only(self):
        status, raw = self.post()
        self.assertEqual(status, 200)
        result = json.loads(raw)
        self.assertTrue(result["synthetic_only"])
        self.assertFalse(result["screen_analyzed"])
        self.assertNotIn(self.token, raw.decode())

    def test_missing_or_invalid_identity_denied(self):
        for auth in ("", "invalid"):
            with self.subTest(auth=auth):
                self.assertEqual(self.post(auth=auth)[0], 401)

    def test_wrong_device_and_bad_session_token_denied(self):
        for change in ({"device_uid": "9"}, {"session_token": "invalid"}):
            with self.subTest(change=change):
                self.assertEqual(self.post(overrides=change)[0], 403)

    def test_replayed_probe_denied(self):
        self.assertEqual(self.post()[0], 200)
        self.assertEqual(self.post()[0], 403)

    def test_revoked_native_permission_denied(self):
        self.permissions.clear()
        self.assertEqual(self.post()[0], 403)

    def test_content_smuggling_denied(self):
        self.assertEqual(self.post(overrides={"image": "private image"})[0], 403)
        self.assertEqual(self.post(overrides={"probe": {"image": "private"}})[0], 403)

    def test_loopback_binding_is_not_external(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
