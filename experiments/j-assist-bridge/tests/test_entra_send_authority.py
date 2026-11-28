from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entra_send_authority import (
    AOT_ENTRA_TENANT_ID,
    JASON_RESOURCE_CLIENT_ID,
    ENTRA_ISSUER,
    EntraSendAuthority,
)
from session_gate import Denied, VerifiedTechnician

SPA_CLIENT = "87654321-4321-4321-4321-abcdefabcdef"
OTHER_CLIENT = "11111111-1111-1111-1111-111111111111"
USER_OID = "22222222-2222-2222-2222-222222222222"


class EntraSendAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signer = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.verification_key = cls.signer.public_key()

    def setUp(self):
        self.active = True
        self.resolved = []
        def resolve(tid, oid):
            self.resolved.append((tid, oid))
            if self.active and tid == AOT_ENTRA_TENANT_ID and oid == USER_OID:
                return VerifiedTechnician("person-entra-verified", "aot")
            return None
        self.auth = EntraSendAuthority(
            allowed_spa_client_id=SPA_CLIENT,
            signing_key_for=lambda raw: self.verification_key,
            resolve_active_aot_identity=resolve,
        )

    def token(self, **changes):
        now = int(time.time())
        claims = {
            "iss": ENTRA_ISSUER,
            "aud": JASON_RESOURCE_CLIENT_ID,
            "tid": AOT_ENTRA_TENANT_ID,
            "oid": USER_OID,
            "scp": "JAssist.Send",
            "azp": SPA_CLIENT,
            "exp": now + 3600,
            "nbf": now - 10,
            "iat": now - 10,
        }
        claims.update(changes)
        return jwt.encode(claims, self.signer, algorithm="RS256", headers={"kid": "preprod-test"})

    def test_valid_signed_narrow_send_scope_yields_active_jason_identity(self):
        person = self.auth.authenticate(self.token())
        self.assertEqual(person, VerifiedTechnician("person-entra-verified", "aot"))
        self.assertEqual(self.resolved, [(AOT_ENTRA_TENANT_ID, USER_OID)])

    def test_rejects_wrong_tenant_audience_issuer_or_spa_client(self):
        for change in [
            {"tid": OTHER_CLIENT}, {"aud": OTHER_CLIENT},
            {"iss": "https://login.microsoftonline.com/common/v2.0"},
            {"azp": OTHER_CLIENT}, {"azp": ""},
            {"oid": "wrong"}, {"oid": ""},
        ]:
            with self.subTest(change=change), self.assertRaises(Denied):
                self.auth.authenticate(self.token(**change))

    def test_scope_is_exactly_jassist_send_not_chatgpt_read(self):
        for scope in ["Jason.Read", "JAssist.Send Jason.Read",
                      "JAssist.Send OtherScope", "", "jassist.send"]:
            with self.subTest(scope=scope), self.assertRaises(Denied):
                self.auth.authenticate(self.token(scp=scope))

    def test_expired_future_not_before_or_missing_required_claims_denied(self):
        now = int(time.time())
        for change in [
            {"exp": now - 100},
            {"nbf": now + 200},
            {"iat": now + 500},
            {"scp": None},
        ]:
            with self.subTest(change=change), self.assertRaises(Denied):
                self.auth.authenticate(self.token(**change))

    def test_token_tampering_wrong_signing_key_or_missing_jwks_denied(self):
        token = self.token()
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        wrong = EntraSendAuthority(
            allowed_spa_client_id=SPA_CLIENT,
            signing_key_for=lambda raw: other_key.public_key(),
            resolve_active_aot_identity=lambda tid, oid: VerifiedTechnician("person", "aot"),
        )
        with self.assertRaises(Denied):
            wrong.authenticate(token)
        jwks_down = EntraSendAuthority(
            allowed_spa_client_id=SPA_CLIENT,
            signing_key_for=lambda raw: (_ for _ in ()).throw(RuntimeError("JWKS unavailable")),
            resolve_active_aot_identity=lambda tid, oid: VerifiedTechnician("person", "aot"),
        )
        with self.assertRaises(Denied):
            jwks_down.authenticate(token)
        with self.assertRaises(Denied):
            self.auth.authenticate(token[:-4] + "xxxx")

    def test_inactive_identity_or_cross_org_rejected(self):
        self.active = False
        with self.assertRaises(Denied):
            self.auth.authenticate(self.token())
        bad_identity = EntraSendAuthority(
            allowed_spa_client_id=SPA_CLIENT,
            signing_key_for=lambda raw: self.verification_key,
            resolve_active_aot_identity=lambda tid, oid: VerifiedTechnician("wrong", "other-org"),
        )
        with self.assertRaises(Denied):
            bad_identity.authenticate(self.token())

    def test_no_client_registration_refuses_startup(self):
        for client in ["", None, "invalid", "a" * 36]:
            with self.subTest(client=client), self.assertRaises(ValueError):
                EntraSendAuthority(
                    allowed_spa_client_id=client,
                    signing_key_for=lambda raw: self.verification_key,
                    resolve_active_aot_identity=lambda tid, oid: None,
                )


if __name__ == "__main__":
    unittest.main()
