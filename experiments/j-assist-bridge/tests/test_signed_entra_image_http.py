from __future__ import annotations

import hashlib
import http.client
import json
import sys
import threading
import time
import unittest
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entra_send_authority import (
    AOT_ENTRA_TENANT_ID, JASON_RESOURCE_CLIENT_ID,
    ENTRA_ISSUER, EntraSendAuthority,
)
from loopback_transport import create_loopback_server
from screen_evidence_intake import AcceptedScreen, ScreenEvidenceIntake
from session_gate import SessionGate, VerifiedTechnician
from synthetic_probe import SyntheticProbe

SPA = "87654321-4321-4321-4321-abcdefabcdef"
USER = "22222222-2222-2222-2222-222222222222"
JPEG = bytes.fromhex("ffd8ffe000104a46494600") + b"safe-synthetic-jwt-http" + bytes.fromhex("ffd9")


class SignedEntraImageHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signer = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_key = cls.signer.public_key()

    def setUp(self):
        self.user = VerifiedTechnician("person-entra-test", "aot")
        self.enabled = True
        self.gate = SessionGate(
            identity=lambda context: context,
            can_read_datto_device=lambda principal, device:
                self.enabled and principal == self.user and device == "1717088",
        )
        self.session, self.internal_token = self.gate.start(
            trusted_context=self.user, device_uid="1717088", consent=True,
        )
        self.intake = ScreenEvidenceIntake(
            gate=self.gate,
            review_content=lambda data: AcceptedScreen(
                data, "synthetic-offline-review", "test-only",
            ),
        )
        self.auth = EntraSendAuthority(
            allowed_spa_client_id=SPA,
            signing_key_for=lambda token: self.public_key,
            resolve_active_aot_identity=lambda tid, oid:
                self.user if tid == AOT_ENTRA_TENANT_ID and oid == USER else None,
        )
        self.server = create_loopback_server(
            probe=SyntheticProbe(self.gate),
            authenticate=self.auth.authenticate,
            image_intake=self.intake,
            session_credential_for=lambda identity, sid:
                self.internal_token if identity == self.user
                and sid == self.session.session_id else None,
        )
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)

    def signed(self, **changes):
        now = int(time.time())
        data = {
            "iss": ENTRA_ISSUER, "aud": JASON_RESOURCE_CLIENT_ID,
            "tid": AOT_ENTRA_TENANT_ID, "oid": USER,
            "scp": "JAssist.Send", "azp": SPA,
            "iat": now - 10, "nbf": now - 10, "exp": now + 3600,
            "padding": "a" * 700,
        }
        data.update(changes)
        return jwt.encode(data, self.signer, algorithm="RS256", headers={"kid": "test-rsa"})

    def post(self, bearer, nonce="BrowserNonceUnique123", device="1717088"):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=3,
        )
        conn.request(
            "POST", "/v1/jassist/image", JPEG,
            {
                "Authorization": "Bearer " + bearer,
                "Content-Type": "image/jpeg",
                "X-JAssist-Session": self.session.session_id,
                "X-JAssist-Device": device,
                "X-JAssist-Nonce": nonce,
                "X-JAssist-SHA256": hashlib.sha256(JPEG).hexdigest(),
            },
        )
        response = conn.getresponse()
        status, body = response.status, response.read()
        conn.close()
        return status, body

    def test_oversize_real_signed_jwt_authenticates_and_receipts(self):
        jwt_value = self.signed()
        self.assertGreater(len(jwt_value), 512)
        status, body = self.post(jwt_value)
        self.assertEqual(status, 201)
        receipt = json.loads(body)
        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(receipt["image_sha256"], hashlib.sha256(JPEG).hexdigest())
        self.assertFalse(receipt["production_ingress"])
        self.assertFalse(receipt["analyzed_by_model"])
        self.assertNotIn(jwt_value.encode(), body)
        self.assertNotIn(self.internal_token.encode(), body)

    def test_invalid_jwt_scope_spa_and_revocation_denied(self):
        self.assertEqual(self.post(self.signed(scp="Jason.Read"))[0], 401)
        self.assertEqual(self.post(self.signed(azp=USER))[0], 401)
        self.assertEqual(self.post(self.signed(exp=int(time.time()) - 100))[0], 401)
        self.assertEqual(self.post(self.signed(), device="9")[0], 403)
        self.enabled = False
        self.assertEqual(self.post(self.signed())[0], 403)


if __name__ == "__main__":
    unittest.main()
