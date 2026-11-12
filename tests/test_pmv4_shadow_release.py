"""Preproduction-only standalone PMv4 shadow release/rollback acceptance."""
from __future__ import annotations

import base64
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from implementation.kernel.signed_owner_release import (
    canonical, issue_exact_owner_release, TID, OWNER_OID, OWNER_PRINCIPAL,
    EXACT_OWNER_OAUTH_SUBJECTS, public_key_sha256,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from pmv4_shadow_release import (
    ShadowController, ShadowReleaseDenied, bundle_digest, manifest_check,
    digest_file, PRODUCTION_ROOT,
)

CANDIDATE = "a" * 40
ROLLBACK = "b" * 40


def provision(tmp: Path):
    root = tmp / "pmv4-shadow"
    for name in ("releases", "receipts", "control"):
        (root / name).mkdir(parents=True, exist_ok=True)
    trust = tmp / "trust"
    trust.mkdir()
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    trust.chmod(0o700)
    (trust / "owner-release-trust.json").write_text(json.dumps({
        "schema_version": "1.0",
        "authorization": "authenticated_entra_owner_exact_release",
        "organization_id": "aot",
        "tenant_id": TID,
        "authorized_owner_subjects": [
            {"owner_oid": oid, "owner_principal": principal}
            for oid, principal in sorted(EXACT_OWNER_OAUTH_SUBJECTS.items())
        ],
        "public_key_base64": base64.b64encode(raw).decode(),
        "public_key_sha256": public_key_sha256(key.public_key()),
        "standing_authority": False,
    }))
    (trust / "owner-release-trust.json").chmod(0o600)
    for sha in (ROLLBACK, CANDIDATE):
        package = root / "releases" / sha / "bundle" / "config"
        package.mkdir(parents=True)
        (package / "profile.json").write_text(json.dumps({"sha": sha, "mode": "shadow"}))
    (root / "current").symlink_to("releases/" + ROLLBACK)
    (root / "control" / "shadow-release.lock").touch()
    compose = root / "control" / "docker-compose.yml"
    compose.write_bytes((ROOT / "config/pmv4-shadow/docker-compose.yml").read_bytes())
    freeze = root / "control" / "shadow-freeze.json"
    freeze.write_text(json.dumps({"schema_version": "1.0", "status": "active",
                                  "service": "jason-pmv4-shadow"}, sort_keys=True))
    bundle_sha = bundle_digest(root / "releases" / CANDIDATE / "bundle")
    scope = {
        "schema_version": "1.0", "service": "jason-pmv4-shadow",
        "candidate_sha": CANDIDATE, "rollback_sha": ROLLBACK,
        "bundle_sha256": bundle_sha, "files": ["config/openclaw-specialists/manifest.json"],
        "protected_core": ["ticket-processing"], "provider_writes": False,
    }
    (root / "control" / "reviewed-scope.json").write_text(json.dumps(scope))
    manifest = {
        "schema_version": "1.0", "service": "jason-pmv4-shadow",
        "release_mode": "owner-signed-isolated-shadow",
        "repository": "al-teamaot-com/jason",
        "candidate_sha": CANDIDATE, "rollback_sha": ROLLBACK,
        "scope_sha256": sha256(canonical(scope)).hexdigest(),
        "bundle_sha256": bundle_sha, "compose_sha256": digest_file(compose),
        "image_digest": "sha256:" + "c" * 64,
        "read_only": True, "provider_writes": False,
        "teams_approval_required": False, "production_core_changes": [],
        "network_profile": "disconnected", "activation": "shadow-only",
    }
    (root / "releases" / CANDIDATE / "release-manifest.json").write_text(
        json.dumps(manifest))
    now = datetime.now(timezone.utc)
    proof = issue_exact_owner_release(
        approval_id="owner-mcp-" + "d" * 32,
        release_id="release-" + CANDIDATE[:16],
        candidate_sha=CANDIDATE, rollback_sha=ROLLBACK,
        scope_sha256=manifest["scope_sha256"],
        manifest_sha256=sha256(canonical(manifest)).hexdigest(),
        freeze_sha256=digest_file(freeze), verified_tenant_id=TID,
        verified_owner_oid=OWNER_OID, verified_principal=OWNER_PRINCIPAL,
        verified_organization_id="aot", confirmed_decision="approve",
        at=now, private_key=key,
    )
    return root, trust / "owner-release-trust.json", manifest, proof, now, key


class StandaloneReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pmv4-shadow-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root, self.trust, self.manifest, self.proof, self.now, self.signer_key = provision(Path(self.tmp.name))
        self.calls = []
        self.ci_accepted = True
        self.healthy = True
        self.fail_activation = False

        def activate(folder: Path):
            self.calls.append(("activate", folder.name))
            if self.fail_activation:
                raise RuntimeError("simulated failure after pointer switch")

        def restore(folder: Path):
            self.calls.append(("restore", folder.name))

        def health(folder: Path):
            self.calls.append(("health_and_core", folder.name))
            return self.healthy

        self.controller = ShadowController(
            self.root, public_key_path=self.trust,
            protected_ci_check=lambda sha: self.ci_accepted and sha == CANDIDATE,
            activate_shadow=activate,
            restore_shadow=restore,
            verify_shadow_and_core=health,
            production=False,
        )

    def active(self):
        return os.readlink(self.root / "current")

    def promote(self):
        return self.controller.promote(self.manifest, self.proof, at=self.now)

    def assert_denied(self, reason):
        with self.assertRaises((ShadowReleaseDenied, PermissionError)) as cm:
            self.promote()
        self.assertIn(reason, str(cm.exception))
        self.assertEqual(self.active(), "releases/" + ROLLBACK)
        self.assertEqual(self.calls, [])

    def test_one_signed_owner_decision_promotes_shadow_only(self):
        freeze = (self.root / "control" / "shadow-freeze.json").read_bytes()
        status = self.promote()
        self.assertEqual(status["status"], "shadow_accepted")
        self.assertEqual(self.active(), "releases/" + CANDIDATE)
        self.assertEqual(self.calls, [("activate", CANDIDATE), ("health_and_core", CANDIDATE)])
        self.assertEqual((self.root / "control" / "shadow-freeze.json").read_bytes(), freeze)
        self.assertFalse(status["pmv3_mutation"])
        self.assertFalse(status["teams_approval"])
        self.assertTrue(status["ticket_core_verified"])

    def test_signed_replay_refused_even_if_pointer_restored(self):
        self.promote()
        (self.root / "current").unlink()
        (self.root / "current").symlink_to("releases/" + ROLLBACK)
        with self.assertRaises(PermissionError):
            self.promote()
        self.assertEqual(len(self.calls), 2)

    def test_shared_host_production_transaction_must_be_quiescent(self):
        self.controller.host_mutation_quiescent = lambda: False
        self.assert_denied("SHADOW_SHARED_HOST_MUTATION_NOT_QUIESCENT")

    def test_existing_ticket_core_must_have_independent_preflight(self):
        self.controller.preexisting_core_health = lambda: False
        self.assert_denied("SHADOW_EXISTING_TICKET_CORE_UNVERIFIED")

    def test_host_and_core_probes_are_evaluated_before_any_activation(self):
        calls = []
        self.controller.host_mutation_quiescent = lambda: calls.append("host") or True
        self.controller.preexisting_core_health = lambda: calls.append("core") or True
        status = self.promote()
        self.assertEqual(status["status"], "shadow_accepted")
        self.assertEqual(calls, ["host", "core"])

    def test_invalid_ci_prevents_mutation(self):
        self.ci_accepted = False
        self.assert_denied("SHADOW_PROTECTED_SOURCE_OR_CI_UNVERIFIED")

    def test_wrong_exact_scope_fails_before_mutation(self):
        self.manifest["scope_sha256"] = "f" * 64
        self.assert_denied("SHADOW_STAGED_MANIFEST_MISMATCH")

    def test_unreviewed_scope_file_blocks(self):
        p = self.root / "control" / "reviewed-scope.json"
        doc = json.loads(p.read_text())
        doc["files"] = ["tools/release_manager_host_runner.py"]
        p.write_text(json.dumps(doc))
        self.assert_denied("SHADOW_REVIEWED_SCOPE_MISMATCH")

    def test_bundle_tampering_fails_before_mutation(self):
        p = self.root / "releases" / CANDIDATE / "bundle/config/profile.json"
        p.write_text("{}")
        self.assert_denied("SHADOW_BUNDLE_DIGEST_MISMATCH")

    def test_staged_manifest_mismatch_rejected(self):
        p = self.root / "releases" / CANDIDATE / "release-manifest.json"
        m = json.loads(p.read_text())
        m["network_profile"] = "internet"
        p.write_text(json.dumps(m))
        self.assert_denied("SHADOW_STAGED_MANIFEST_MISMATCH")

    def test_empty_initial_baseline_supported_without_pmv3(self):
        # A separately provisioned clean shadow namespace is a legitimate
        # initial rollback, rather than faking a previous deployed gateway.
        zero = "0"*40
        (self.root / "current").unlink()
        (self.root / "current").symlink_to("releases/" + zero)
        (self.root / "releases" / zero).mkdir()
        (self.root / "releases" / zero / "baseline.json").write_text(
            json.dumps({"schema_version": "1.0", "service": "jason-pmv4-shadow",
                        "baseline": "no_prior_shadow_runtime"}))
        self.manifest["rollback_sha"] = zero
        reviewed = self.root / "control" / "reviewed-scope.json"
        s = json.loads(reviewed.read_text())
        s["rollback_sha"] = zero
        reviewed.write_text(json.dumps(s))
        self.manifest["scope_sha256"] = sha256(canonical(s)).hexdigest()
        (self.root / "releases" / CANDIDATE / "release-manifest.json").write_text(json.dumps(self.manifest))
        self.proof = issue_exact_owner_release(
            approval_id="owner-mcp-"+"e"*32,
            release_id="release-"+CANDIDATE[:16],
            candidate_sha=CANDIDATE, rollback_sha=zero,
            scope_sha256=self.manifest["scope_sha256"],
            manifest_sha256=sha256(canonical(self.manifest)).hexdigest(),
            freeze_sha256=digest_file(self.root / "control" / "shadow-freeze.json"),
            verified_tenant_id=TID, verified_owner_oid=OWNER_OID,
            verified_principal=OWNER_PRINCIPAL,
            verified_organization_id="aot", confirmed_decision="approve",
            at=self.now, private_key=self.signer_key,
        )
        result = self.promote()
        self.assertEqual(result["status"], "shadow_accepted")
        self.assertEqual(self.active(), "releases/" + CANDIDATE)

    def test_symlink_in_bundle_fails_closed(self):
        p = self.root / "releases" / CANDIDATE / "bundle/config/extra"
        p.symlink_to("/etc/passwd")
        self.assert_denied("SHADOW_BUNDLE_SYMLINK")

    def test_wrong_owner_signer_refused(self):
        key = Ed25519PrivateKey.generate()
        self.proof = issue_exact_owner_release(
            approval_id="owner-mcp-" + "e" * 32,
            release_id="release-" + CANDIDATE[:16],
            candidate_sha=CANDIDATE, rollback_sha=ROLLBACK,
            scope_sha256=self.manifest["scope_sha256"],
            manifest_sha256=sha256(canonical(self.manifest)).hexdigest(),
            freeze_sha256=digest_file(self.root / "control" / "shadow-freeze.json"),
            verified_tenant_id=TID, verified_owner_oid=OWNER_OID,
            verified_principal=OWNER_PRINCIPAL,
            verified_organization_id="aot", confirmed_decision="approve",
            at=self.now, private_key=key,
        )
        with self.assertRaises(PermissionError):
            self.promote()
        self.assertEqual(self.active(), "releases/" + ROLLBACK)

    def test_proof_tampering_refused(self):
        self.proof["payload"]["rollback_sha"] = "1" * 40
        with self.assertRaises(PermissionError):
            self.promote()
        self.assertEqual(self.active(), "releases/" + ROLLBACK)

    def test_approval_expiry_refused(self):
        with self.assertRaises(PermissionError):
            self.controller.promote(self.manifest, self.proof, at=self.now + timedelta(minutes=16))
        self.assertEqual(self.active(), "releases/" + ROLLBACK)

    def test_freeze_change_refused(self):
        p = self.root / "control" / "shadow-freeze.json"
        p.write_text('{"status":"inactive"}')
        self.assert_denied("SHADOW_FREEZE_NOT_ACTIVE")

    def test_root_pinned_compose_cannot_drift(self):
        compose = self.root / "control" / "docker-compose.yml"
        compose.write_text(compose.read_text() + "\n# drift\n")
        self.assert_denied("SHADOW_COMPOSE_DRIFT")

    def test_unsafe_service_identity_fails(self):
        self.manifest["provider_writes"] = True
        self.assert_denied("SHADOW_MANIFEST_FIELDS_INVALID")

    def test_runtime_failure_rolls_back(self):
        self.fail_activation = True
        with self.assertRaises(RuntimeError):
            self.promote()
        self.assertEqual(self.active(), "releases/" + ROLLBACK)
        self.assertEqual(self.calls, [("activate", CANDIDATE), ("restore", ROLLBACK)])
        receipt = next((self.root / "receipts").glob("*.json"))
        self.assertEqual(json.loads(receipt.read_text())["state"], "rolled_back")

    def test_health_failure_rolls_back(self):
        self.healthy = False
        with self.assertRaises(ShadowReleaseDenied):
            self.promote()
        self.assertEqual(self.active(), "releases/" + ROLLBACK)
        self.assertIn(("restore", ROLLBACK), self.calls)

    def test_crash_journal_blocks_future_release(self):
        self.fail_activation = True
        def failed_restore(_path):
            raise RuntimeError("simulated power loss in rollback")
        self.controller.restore_shadow = failed_restore
        with self.assertRaises(RuntimeError):
            self.promote()
        self.assertEqual(self.active(), "releases/" + ROLLBACK)
        journal = next((self.root / "receipts").glob("*.json"))
        self.assertEqual(json.loads(journal.read_text())["state"], "started")
        with self.assertRaisesRegex(PermissionError, "SHADOW_UNRECONCILED_TRANSACTION"):
            self.promote()

    def test_interrupted_rollback_is_reconciled_without_repromotion(self):
        self.fail_activation = True
        original_restore = self.controller.restore_shadow
        def failed_restore(_):
            raise RuntimeError("first rollback interrupted")
        self.controller.restore_shadow = failed_restore
        with self.assertRaises(RuntimeError):
            self.promote()
        receipt = next((self.root / "receipts").glob("*.json"))
        self.assertEqual(json.loads(receipt.read_text())["state"], "started")
        self.controller.restore_shadow = original_restore
        accepted = self.controller.reconcile_pending_rollback(
            rollback_acceptance=lambda prior: prior.name == ROLLBACK,
        )
        self.assertEqual(accepted["status"], "shadow_rollback_verified")
        self.assertEqual(self.active(), "releases/" + ROLLBACK)
        self.assertEqual(json.loads(receipt.read_text())["state"], "rolled_back")
        with self.assertRaises(PermissionError):
            self.promote()  # exact Owner approval already consumed

    def test_pending_rollback_requires_independent_health_proof(self):
        self.fail_activation = True
        self.controller.restore_shadow = lambda _: (_ for _ in ()).throw(RuntimeError("failed"))
        with self.assertRaises(RuntimeError):
            self.promote()
        self.controller.restore_shadow = lambda _: None
        with self.assertRaisesRegex(PermissionError, "SHADOW_ROLLBACK_HEALTH_UNVERIFIED"):
            self.controller.reconcile_pending_rollback(
                rollback_acceptance=lambda _: False,
            )
        receipt = next((self.root / "receipts").glob("*.json"))
        self.assertEqual(json.loads(receipt.read_text())["state"], "started")

    def test_pending_rollback_freeze_drift_blocks(self):
        self.fail_activation = True
        self.controller.restore_shadow = lambda _: (_ for _ in ()).throw(RuntimeError("failed"))
        with self.assertRaises(RuntimeError):
            self.promote()
        self.controller.restore_shadow = lambda _: None
        (self.root / "control" / "shadow-freeze.json").write_text(
            '{"schema_version":"1.0","status":"changed","service":"jason-pmv4-shadow"}'
        )
        with self.assertRaisesRegex(PermissionError, "SHADOW_PENDING_EVIDENCE_INVALID"):
            self.controller.reconcile_pending_rollback(
                rollback_acceptance=lambda _: True,
            )

    def test_reconcile_no_pending_is_readonly(self):
        result = self.controller.reconcile_pending_rollback(
            rollback_acceptance=lambda _: self.fail("must not be invoked"),
        )
        self.assertEqual(result["status"], "nothing_pending")
        self.assertEqual(self.active(), "releases/" + ROLLBACK)

    def test_does_not_allow_pmv3_paths_or_untrusted_root(self):
        with self.assertRaisesRegex(PermissionError, "SHADOW_OVERLAPS_PMV3"):
            ShadowController(Path("/var/lib/jason/openclaw/release-manager"),
                             public_key_path=self.trust,
                             protected_ci_check=lambda _: True,
                             activate_shadow=lambda _: None,
                             verify_shadow_and_core=lambda _: True,
                             restore_shadow=lambda _: None,
                             production=False)
        with self.assertRaisesRegex(PermissionError, "SHADOW_PRODUCTION_ROOT_NOT_PINNED"):
            ShadowController(self.root, public_key_path=self.trust,
                             protected_ci_check=lambda _: True,
                             activate_shadow=lambda _: None,
                             verify_shadow_and_core=lambda _: True,
                             restore_shadow=lambda _: None,
                             production=True)

    def test_full_host_transaction_lease_encloses_promotion_and_verification(self):
        from contextlib import contextmanager
        events = []
        in_lease = {"value": False}

        @contextmanager
        def host_transaction():
            events.append("host_acquired")
            in_lease["value"] = True
            try:
                yield
            finally:
                in_lease["value"] = False
                events.append("host_released")

        self.controller.host_release_transaction = host_transaction
        self.controller.host_mutation_quiescent = lambda: in_lease["value"]
        self.controller.preexisting_core_health = lambda: in_lease["value"]
        original_activate = self.controller.activate_shadow
        original_verify = self.controller.verify_shadow_and_core

        def active(path):
            self.assertTrue(in_lease["value"])
            events.append("activate")
            original_activate(path)

        def verify(path):
            self.assertTrue(in_lease["value"])
            events.append("verified")
            return original_verify(path)

        self.controller.activate_shadow = active
        self.controller.verify_shadow_and_core = verify
        self.assertEqual(self.promote()["status"], "shadow_accepted")
        self.assertEqual(
            events, ["host_acquired", "activate", "verified", "host_released"]
        )

    def test_full_host_transaction_lease_encloses_crash_reconciliation(self):
        from contextlib import contextmanager
        held = {"value": False}
        events = []

        @contextmanager
        def host_transaction():
            self.assertFalse(held["value"])
            held["value"] = True
            events.append("acquired")
            try:
                yield
            finally:
                events.append("released")
                held["value"] = False

        self.controller.host_release_transaction = host_transaction
        self.controller.host_mutation_quiescent = lambda: held["value"]
        self.fail_activation = True
        self.controller.restore_shadow = lambda _: (
            (_ for _ in ()).throw(RuntimeError("test interrupted restore"))
        )
        with self.assertRaises(RuntimeError):
            self.promote()
        events.clear()
        self.controller.restore_shadow = lambda _: (
            self.assertTrue(held["value"]), events.append("restored")
        )
        result = self.controller.reconcile_pending_rollback(
            rollback_acceptance=lambda _: held["value"],
        )
        self.assertEqual(result["status"], "shadow_rollback_verified")
        self.assertEqual(events, ["acquired", "restored", "released"])

    def test_missing_pinned_trust_fails(self):
        self.trust.unlink()
        with self.assertRaises(PermissionError):
            self.promote()
        self.assertEqual(self.active(), "releases/" + ROLLBACK)


if __name__ == "__main__":
    unittest.main()
