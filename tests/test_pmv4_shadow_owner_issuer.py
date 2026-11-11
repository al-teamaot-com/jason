"""Offline only: signer adapter does NOT substitute for real Entra OAuth."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from implementation.kernel.signed_owner_release import (
    TID, OWNER_OID, OWNER_PRINCIPAL, verify_exact_owner_release,
)
from pmv4_shadow_owner_issuer import issue_shadow_owner_proof, ISSUER
from test_pmv4_shadow_release import provision


class StandaloneIssuerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pmv4-issuer-test-")
        self.addCleanup(tmp.cleanup)
        self.root, self.trust, self.manifest, self.proof, self.at, self.key = provision(Path(tmp.name))
        self.audience = Path(tmp.name) / "audience.json"
        self.audience.write_text(json.dumps({
            "schema_version": "1.0", "service": "jason-pmv4-shadow",
            "audience": "api://pmv4-shadow-acceptance-only",
        }))
        self.signer = Path(tmp.name) / "signer.key"
        self.signer.write_bytes(self.key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        self.signer.chmod(0o400)
        control = self.root / "control"
        (control / "approved-manifest.json").write_text(json.dumps(self.manifest))
        (control / "signed-owner-decisions").mkdir()
        t = int(self.at.timestamp())
        self.claims = {
            "iss": ISSUER, "tid": TID, "oid": OWNER_OID,
            "aud": "api://pmv4-shadow-acceptance-only",
            "iat": t-10, "nbf": t-10, "exp": t+300,
        }
        self.consent_bindings = []

    def issue(self, *, verifier=None, consent=True, ci=True):
        return issue_shadow_owner_proof(
            root=self.root, bearer_token="preprod-test-opaque-bearer",
            jwt_verifier=verifier or (lambda _: self.claims),
            exact_owner_consent=lambda binding: self.consent_bindings.append(dict(binding)) or consent,
            protected_main_check=lambda sha: ci and sha == self.manifest["candidate_sha"],
            audience_path=self.audience, signer_path=self.signer,
            at=self.at, production=False,
        )

    def test_exact_authenticated_owner_simulation_one_use(self):
        result = self.issue()
        self.assertEqual(result["status"], "owner_decision_signed_for_exact_shadow_release")
        self.assertFalse(result["teams_required"])
        self.assertEqual(self.consent_bindings[0]["owner_principal"], OWNER_PRINCIPAL)
        receipt = self.root / "control" / "signed-owner-decisions" / (result["release_id"] + ".json")
        record = json.loads(receipt.read_text())
        signed = record["signed_owner_proof"]
        verify_exact_owner_release(
            signed, public_key=self.key.public_key(),
            expected_candidate_sha=self.manifest["candidate_sha"],
            expected_rollback_sha=self.manifest["rollback_sha"],
            expected_release_id=result["release_id"],
            expected_scope_sha256=self.manifest["scope_sha256"],
            expected_manifest_sha256=self.consent_bindings[0]["manifest_sha256"],
            expected_freeze_sha256=self.consent_bindings[0]["freeze_sha256"],
            at=self.at,
        )
        with self.assertRaisesRegex(PermissionError, "SHADOW_RECEIPT_EXISTS_OR_UNAVAILABLE"):
            self.issue()

    def test_source_only_issuer_to_standalone_release_end_to_end(self):
        # Synthetic token verifier and signer are TEST ONLY. This proves the
        # two reusable components interoperate without PMV3 release records.
        from pmv4_shadow_release import ShadowController
        result = self.issue()
        receipt_path = self.root / "control" / "signed-owner-decisions" / (
            result["release_id"] + ".json")
        proof = json.loads(receipt_path.read_text())["signed_owner_proof"]
        controller = ShadowController(
            self.root, public_key_path=self.trust,
            protected_ci_check=lambda sha: sha == self.manifest["candidate_sha"],
            activate_shadow=lambda _: None,
            restore_shadow=lambda _: None,
            verify_shadow_and_core=lambda _: True,
            production=False,
        )
        accepted = controller.promote(self.manifest, proof, at=self.at)
        self.assertEqual(accepted["status"], "shadow_accepted")
        self.assertFalse(accepted["teams_approval"])
        self.assertFalse(accepted["pmv3_mutation"])
        self.assertEqual((self.root / "current").readlink(),
                         Path("releases") / self.manifest["candidate_sha"])

    def test_invalid_claims_do_not_issue(self):
        for field, value in (
            ("iss", "https://evil.invalid/"),
            ("tid", "other-tenant"),
            ("oid", "unknown-person"),
            ("aud", "api://wrong"),
            ("iat", int(self.at.timestamp())-1000),
            ("exp", int(self.at.timestamp())-1),
            ("nbf", int(self.at.timestamp())+1),
            ("iat", True),
            ("nbf", True),
        ):
            with self.subTest(field=field,value=value):
                original = self.claims[field]
                self.claims[field] = value
                with self.assertRaises(PermissionError):
                    self.issue()
                self.claims[field] = original
        self.assertEqual(list((self.root / "control" / "signed-owner-decisions").iterdir()), [])

    def test_oauth_verifier_unavailable_fails_closed(self):
        def broken(_):
            raise RuntimeError("JWT signature not verified")
        with self.assertRaisesRegex(PermissionError, "SHADOW_ENTRA_TOKEN_VERIFICATION_FAILED"):
            self.issue(verifier=broken)

    def test_no_authenticated_exact_owner_consent_fails(self):
        with self.assertRaisesRegex(PermissionError, "SHADOW_EXACT_OWNER_CONFIRMATION_MISSING"):
            self.issue(consent=False)

    def test_protected_source_must_pass(self):
        with self.assertRaisesRegex(PermissionError, "SHADOW_PROTECTED_MAIN_UNVERIFIED"):
            self.issue(ci=False)

    def test_tampered_reviewed_scope_refused(self):
        file = self.root / "control" / "reviewed-scope.json"
        file.write_text('{"tampered":true}')
        with self.assertRaisesRegex(PermissionError, "SHADOW_OWNER_REVIEWED_SCOPE_CHANGED"):
            self.issue()

    def test_wrong_signer_permissions_refused(self):
        self.signer.chmod(0o644)
        with self.assertRaises(PermissionError):
            self.issue()

    def test_missing_private_signer_refused(self):
        self.signer.unlink()
        with self.assertRaises(PermissionError):
            self.issue()

    def test_wrong_audience_denied(self):
        self.audience.write_text(json.dumps({
            "schema_version":"1.0", "service":"jason-pmv4-shadow", "audience":"api://not-the-real-audience",
        }))
        with self.assertRaises(PermissionError):
            self.issue()


if __name__ == "__main__":
    unittest.main()
