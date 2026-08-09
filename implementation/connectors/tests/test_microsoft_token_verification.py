from __future__ import annotations

import unittest
from datetime import datetime, timezone

from connectors.microsoft_graph.microsoft_token_verification import (
    MicrosoftTokenPolicy,
    MicrosoftTokenVerificationError,
    MicrosoftTokenVerifier,
)


NOW = datetime(2026, 8, 9, 16, 0, tzinfo=timezone.utc)
NOW_EPOCH = int(NOW.timestamp())
TENANT = "11111111-1111-1111-1111-111111111111"
AUDIENCE = "api://jason-approval-ingress"


class FakeCryptoVerifier:
    def __init__(self, claims=None, error=None):
        self.claims = claims
        self.error = error

    def verify_signature(self, token):
        if self.error is not None:
            raise self.error
        return dict(self.claims)


def claims(**overrides):
    value = {
        "tid": TENANT,
        "oid": "22222222-2222-2222-2222-222222222222",
        "sub": "subject-1",
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": AUDIENCE,
        "iat": NOW_EPOCH - 60,
        "nbf": NOW_EPOCH - 60,
        "exp": NOW_EPOCH + 300,
        "amr": ["pwd", "mfa"],
    }
    value.update(overrides)
    return value


def verifier(token_claims):
    return MicrosoftTokenVerifier(
        crypto=FakeCryptoVerifier(token_claims),
        policy=MicrosoftTokenPolicy(audience=AUDIENCE, allowed_tenant_ids=(TENANT,)),
        clock=lambda: NOW,
    )


class MicrosoftTokenVerifierTests(unittest.TestCase):
    def test_verified_token_produces_trusted_principal(self):
        principal = verifier(claims()).verify("signed-token")
        self.assertEqual(TENANT, principal.tenant_id)
        self.assertEqual("22222222-2222-2222-2222-222222222222", principal.object_id)
        self.assertEqual("mfa", principal.authentication_assurance)

    def test_signature_failure_fails_closed(self):
        service = MicrosoftTokenVerifier(
            crypto=FakeCryptoVerifier(error=ValueError("bad signature")),
            policy=MicrosoftTokenPolicy(audience=AUDIENCE, allowed_tenant_ids=(TENANT,)),
            clock=lambda: NOW,
        )
        with self.assertRaises(MicrosoftTokenVerificationError):
            service.verify("forged-token")

    def test_unapproved_tenant_fails_closed(self):
        with self.assertRaises(MicrosoftTokenVerificationError):
            verifier(claims(tid="other-tenant", iss="https://login.microsoftonline.com/other-tenant/v2.0")).verify("token")

    def test_issuer_must_match_tenant(self):
        with self.assertRaises(MicrosoftTokenVerificationError):
            verifier(claims(iss="https://login.microsoftonline.com/other-tenant/v2.0")).verify("token")

    def test_audience_mismatch_fails_closed(self):
        with self.assertRaises(MicrosoftTokenVerificationError):
            verifier(claims(aud="api://attacker")).verify("token")

    def test_expired_token_fails_closed(self):
        with self.assertRaises(MicrosoftTokenVerificationError):
            verifier(claims(exp=NOW_EPOCH - 121)).verify("token")

    def test_future_not_before_fails_closed(self):
        with self.assertRaises(MicrosoftTokenVerificationError):
            verifier(claims(nbf=NOW_EPOCH + 121)).verify("token")

    def test_missing_assurance_fails_closed(self):
        token_claims = claims()
        token_claims.pop("amr")
        with self.assertRaises(MicrosoftTokenVerificationError):
            verifier(token_claims).verify("token")

    def test_acr_can_supply_assurance(self):
        token_claims = claims(acr="1")
        token_claims.pop("amr")
        principal = verifier(token_claims).verify("token")
        self.assertEqual("acr:1", principal.authentication_assurance)


if __name__ == "__main__":
    unittest.main()
