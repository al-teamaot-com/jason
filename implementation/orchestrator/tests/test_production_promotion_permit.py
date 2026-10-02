from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from orchestrator.production_promotion_approval import ProductionPromotionAuthorization
from orchestrator.production_promotion_permit import (
    ProductionPromotionPermit,
    ProductionPromotionPermitError,
    ProductionPromotionPermitIssuer,
    ProductionPromotionPermitVerifier,
    SQLiteProductionPromotionPermitClaims,
)


NOW = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)
SOURCE = "a" * 40
ARTIFACT = "sha256:" + "b" * 64
PLAN = "c" * 64


class ProductionPromotionPermitTests(unittest.TestCase):
    def setUp(self) -> None:
        private = Ed25519PrivateKey.generate()
        self.private_pem = private.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption(),
        )
        self.public_pem = private.public_key().public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        )
        self.authorization = ProductionPromotionAuthorization(
            approval_id="approval-1",
            promotion_id="promotion-1",
            plan_sha256=PLAN,
            authority_context_id="context-1",
            decided_by="owner-al",
            expires_at=NOW + timedelta(minutes=20),
        )
        self.issuer = ProductionPromotionPermitIssuer(
            private_key_pem=self.private_pem,
            signer_key_id="promotion-key-1",
        )
        self.verifier = ProductionPromotionPermitVerifier(
            public_keys={"promotion-key-1": self.public_pem}
        )

    def issue(self):
        return self.issuer.issue(
            authorization=self.authorization,
            component="jason-runtime",
            operation="deploy",
            source_sha=SOURCE,
            artifact_digest=ARTIFACT,
            now=NOW,
        )

    def verify(self, permit, **overrides):
        values = dict(
            component="jason-runtime",
            operation="deploy",
            source_sha=SOURCE,
            artifact_digest=ARTIFACT,
            plan_sha256=PLAN,
            now=NOW + timedelta(minutes=1),
        )
        values.update(overrides)
        self.verifier.verify(permit, **values)

    def test_exact_signed_permit_verifies(self):
        self.verify(self.issue())

    def test_plan_artifact_component_and_source_drift_fail_closed(self):
        permit = self.issue()
        for key, value in (
            ("plan_sha256", "d" * 64),
            ("artifact_digest", "sha256:" + "e" * 64),
            ("component", "jason-mcp"),
            ("source_sha", "f" * 40),
        ):
            with self.subTest(key=key):
                with self.assertRaises(ProductionPromotionPermitError):
                    self.verify(permit, **{key: value})

    def test_signature_tampering_fails_closed(self):
        permit = self.issue()
        raw = permit.as_dict()
        raw["promotion_id"] = "promotion-tampered"
        tampered = ProductionPromotionPermit.from_mapping(raw)
        with self.assertRaises(ProductionPromotionPermitError):
            self.verify(tampered)

    def test_unknown_signer_fails_closed(self):
        permit = self.issue()
        verifier = ProductionPromotionPermitVerifier(public_keys={})
        with self.assertRaises(ProductionPromotionPermitError):
            verifier.verify(
                permit,
                component="jason-runtime",
                operation="deploy",
                source_sha=SOURCE,
                artifact_digest=ARTIFACT,
                plan_sha256=PLAN,
                now=NOW + timedelta(minutes=1),
            )

    def test_expired_permit_fails_closed(self):
        permit = self.issue()
        with self.assertRaises(ProductionPromotionPermitError):
            self.verify(permit, now=NOW + timedelta(minutes=11))

    def test_permit_cannot_outlive_owner_approval(self):
        short = replace(
            self.authorization,
            expires_at=NOW + timedelta(minutes=3),
        )
        permit = self.issuer.issue(
            authorization=short,
            component="jason-runtime",
            operation="deploy",
            source_sha=SOURCE,
            artifact_digest=ARTIFACT,
            now=NOW,
            ttl=timedelta(minutes=10),
        )
        self.assertEqual(permit.expires_at, short.expires_at)

    def test_claim_is_durable_and_single_use(self):
        permit = self.issue()
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/claims.sqlite3"
            claims = SQLiteProductionPromotionPermitClaims(path)
            claims.initialize()
            first = claims.claim(permit, now=NOW + timedelta(minutes=1))
            self.assertEqual(first.permit_id, permit.permit_id)
            reopened = SQLiteProductionPromotionPermitClaims(path)
            with self.assertRaises(ProductionPromotionPermitError):
                reopened.claim(permit, now=NOW + timedelta(minutes=2))
            evidence = reopened.evidence(permit.permit_id)
            self.assertEqual(evidence["plan_sha256"], PLAN)


if __name__ == "__main__":
    unittest.main()
