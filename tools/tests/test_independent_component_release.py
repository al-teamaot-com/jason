from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import sqlite3
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from implementation.kernel.signed_owner_release import issue_exact_owner_release, canonical
from tools import independent_component_release as c

KEY = Ed25519PrivateKey.generate()
OWNER = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"
OID = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"


def _json(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True) + "\n")


def fixture(tmp_path, *, candidate="a" * 40, rollback=c.ZERO):
    root = tmp_path / "component"
    for name in ("releases", "receipts", "control", "active"):
        (root / name).mkdir(parents=True)
    freeze = b'{"status":"active"}'
    (root / "control" / "production-deployment-freeze").write_bytes(freeze)
    (root / "control" / "component-release.lock").write_text("unclaimed")
    bundle = root / "releases" / candidate
    bundle.mkdir()
    compose = (
        "name: jason-financial-statements\n"
        "services:\n"
        "  financial-statements:\n"
        "    image: sha256:" + "f" * 64 + "\n"
        '    user: "1000:1000"\n'
        "    read_only: true\n"
        "    cap_drop: [ALL]\n"
        "    security_opt: [no-new-privileges:true]\n"
        "    volumes:\n"
        "      - /trusted/config.json:/app/config.json:ro\n"
    ).encode()
    config = b'{"enabled":true,"schedule":"05:00 America/New_York"}\n'
    boundary_path = bundle / "boundary.sqlite3"
    with sqlite3.connect(boundary_path) as db:
        db.executescript(
            "CREATE TABLE client_boundaries("
            "client_id TEXT,provider TEXT,external_tenant_id TEXT,"
            "profile TEXT,application_id TEXT,status TEXT,external_scope_ids TEXT);"
            "CREATE TABLE onboarding_transactions(id TEXT);"
        )
        db.execute(
            "INSERT INTO client_boundaries VALUES(?,?,?,?,?,?,?)",
            ("client-aot-internal", "microsoft_sharepoint",
             "f7054323-d52b-4863-8c2f-1898f0b6077c", "sharepoint-write",
             "3d362478-a873-4ba2-b8a5-c04e66ef2f32", "validated",
             json.dumps(["absolnet.sharepoint.com,abc,def"])),
        )
    boundary = boundary_path.read_bytes()
    (bundle / "compose.yaml").write_bytes(compose)
    (bundle / "config.json").write_bytes(config)
    m = {
        "schema_version": "1.0",
        "release_mode": "owner-signed-independent-compose",
        "repository": "al-teamaot-com/jason",
        "component_id": "financial-statements",
        "compose_project": "jason-financial-statements",
        "compose_service": "financial-statements",
        "candidate_sha": candidate,
        "rollback_sha": rollback,
        "image_digest": "sha256:" + "f" * 64,
        "compose_sha256": sha256(compose).hexdigest(),
        "config_sha256": sha256(config).hexdigest(),
        "boundary_sha256": sha256(boundary).hexdigest(),
        "scope_sha256": "",
        "freeze_sha256": sha256(freeze).hexdigest(),
        "provider_scope": {
            "provider": "microsoft_sharepoint",
            "profile": "sharepoint-write",
            "tenant_id": "f7054323-d52b-4863-8c2f-1898f0b6077c",
            "scope_id": "absolnet.sharepoint.com,abc,def",
            "client_id": "client-aot-internal",
            "application_id": "3d362478-a873-4ba2-b8a5-c04e66ef2f32",
        },
        "protected_services": list(c.PROTECTED),
        "rollback_mode": "remove-component-only" if rollback == c.ZERO else "restore-prior-component-only",
    }
    scope = {k: m[k] for k in c.SCOPE_FIELDS}
    m["scope_sha256"] = sha256(canonical(scope)).hexdigest()
    _json(bundle / "scope.json", scope)
    _json(bundle / "manifest.json", m)
    return root, m


def approval(m, *, key=KEY, at=None, decision="approve"):
    at = at or datetime.now(timezone.utc)
    return issue_exact_owner_release(
        approval_id="owner-mcp-" + "1" * 32,
        release_id=c.release_id(m["candidate_sha"]),
        candidate_sha=m["candidate_sha"],
        rollback_sha=m["rollback_sha"],
        scope_sha256=m["scope_sha256"],
        manifest_sha256=sha256(canonical(m)).hexdigest(),
        freeze_sha256=m["freeze_sha256"],
        verified_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        verified_owner_oid=OID,
        verified_principal=OWNER,
        verified_organization_id="aot",
        confirmed_decision=decision,
        at=at,
        private_key=key,
    )


class Host:
    def __init__(self):
        self.installed = None
        self.call_log = []
        self.fail_acceptance = False
        self.fail_restore = False
        self.mutate_protected = False
        self.busy = False
        self.freeze_changed = False
        self.frozen = False

    @contextmanager
    def host_transaction(self):
        self.call_log.append("host_lock_enter")
        if self.busy:
            raise c.ComponentReleaseDenied("HOST_RELEASE_BUSY")
        try:
            yield
        finally:
            self.call_log.append("host_lock_exit")

    @contextmanager
    def freeze_transaction(self, expected_sha):
        self.call_log.append("freeze_enter")
        self.frozen = True
        try:
            yield
        finally:
            self.frozen = False
            self.call_log.append("freeze_restored")

    def protected(self):
        version = "changed" if self.mutate_protected else "original"
        return {
            n: {
                "running": True, "health": "healthy",
                "id": n + "-" + version,
                "image": "sha256:" + "e" * 64,
                "started_at": "2026-11-17T12:00:00Z",
            } for n in c.PROTECTED
        }

    def source(self, candidate):
        self.call_log.append("source_check")
        return True

    def image(self, image, source):
        self.call_log.append("image_check")
        return True

    def observe(self, project):
        return self.installed

    def activate(self, bundle, manifest):
        assert self.frozen
        self.call_log.append("activate")
        self.installed = manifest["candidate_sha"]

    def restore(self, previous, manifest):
        assert self.frozen
        self.call_log.append("restore")
        if self.fail_restore:
            raise RuntimeError("restore failed")
        self.installed = None if previous is None else manifest["rollback_sha"]
        self.mutate_protected = False

    def verify_component(self, bundle, manifest):
        self.call_log.append("verify")
        if bundle is not None and self.fail_acceptance:
            return False
        return True


def controller(root, host):
    return c.ComponentReleaseController(
        root=root, host_transaction=host.host_transaction,
        freeze_transaction=host.freeze_transaction,
        verify_protected=host.protected,
        verify_source_and_ci=host.source,
        verify_image=host.image,
        observe_component=host.observe,
        activate_component=host.activate,
        restore_component=host.restore,
        verify_component=host.verify_component,
        production=False, trusted_public_key=KEY.public_key(),
    )


def test_first_install_accepts_exact_signed_single_component(tmp_path):
    root, m = fixture(tmp_path)
    host = Host()
    result = controller(root, host).promote(m, approval(m))
    assert result["status"] == "component_accepted"
    assert result["protected_services_changed"] is False
    assert host.installed == m["candidate_sha"]
    assert host.call_log.index("host_lock_enter") < host.call_log.index("activate")
    assert host.call_log.index("freeze_enter") < host.call_log.index("activate")
    assert host.call_log.index("activate") < host.call_log.index("freeze_restored")
    receipt = json.loads(next((root / "receipts").glob("*.json")).read_text())
    assert receipt["state"] == "accepted"
    assert (root / "active" / "financial-statements.json").is_file()
    assert (root / "control" / "production-deployment-freeze").read_bytes() == b'{"status":"active"}'
    with pytest.raises(c.ComponentReleaseDenied, match="ROLLBACK_NOT_CURRENT"):
        controller(root, host).promote(m, approval(m))


@pytest.mark.parametrize("field,replacement,error", [
    ("image_digest", "sha256:" + "9" * 64, "IMMUTABLE_MANIFEST_DRIFT"),
    ("compose_sha256", "8" * 64, "IMMUTABLE_MANIFEST_DRIFT"),
    ("config_sha256", "7" * 64, "IMMUTABLE_MANIFEST_DRIFT"),
    ("scope_sha256", "6" * 64, "IMMUTABLE_MANIFEST_DRIFT"),
    ("freeze_sha256", "5" * 64, "IMMUTABLE_MANIFEST_DRIFT"),
    ("rollback_sha", "b" * 40, "MANIFEST_FIELDS"),
])
def test_manifest_tamper_denied_before_mutation(tmp_path, field, replacement, error):
    root, m = fixture(tmp_path)
    m[field] = replacement
    host = Host()
    with pytest.raises(c.ComponentReleaseDenied, match=error):
        controller(root, host).promote(m, approval(fixture(tmp_path / "other")[1]))
    assert "activate" not in host.call_log


@pytest.mark.parametrize("modification,expected", [
    (lambda y: y["services"].update({"jason-runtime": dict(y["services"]["financial-statements"])}), "MULTISERVICE"),
    (lambda y: y["services"]["financial-statements"].update({"privileged": True}), "ESCALATION"),
    (lambda y: y["services"]["financial-statements"].update({"read_only": False}), "ISOLATION"),
    (lambda y: y.update({"name": "jason-runtime"}), "PROJECT_MISMATCH"),
    (lambda y: y["services"]["financial-statements"].update({"volumes": ["/var/run/docker.sock:/run/docker.sock:rw"]}), "PROTECTED_MOUNT"),
])
def test_compose_rejects_protected_or_escalating_content(tmp_path, modification, expected):
    import yaml
    _, m = fixture(tmp_path)
    y = yaml.safe_load((tmp_path / "component" / "releases" / m["candidate_sha"] / "compose.yaml").read_text())
    modification(y)
    with pytest.raises(c.ComponentReleaseDenied, match=expected):
        c.validate_compose(yaml.safe_dump(y).encode(), m)


def test_invalid_owner_signature_and_expiry_fail_before_activate(tmp_path):
    root, m = fixture(tmp_path)
    host = Host()
    bad = approval(m, key=Ed25519PrivateKey.generate())
    with pytest.raises(PermissionError, match="SIGNATURE_INVALID"):
        controller(root, host).promote(m, bad)
    expired = approval(m, at=datetime.now(timezone.utc) - timedelta(minutes=20))
    with pytest.raises(PermissionError, match="EXPIRED_OR_FUTURE"):
        controller(root, host).promote(m, expired)
    assert "activate" not in host.call_log
    assert list((root / "receipts").iterdir()) == []


def test_freeze_drift_denies_without_mutation(tmp_path):
    root, m = fixture(tmp_path)
    (root / "control" / "production-deployment-freeze").write_text('{"status":"inactive"}')
    host = Host()
    with pytest.raises(c.ComponentReleaseDenied, match="FROZEN_STATE_CHANGED"):
        controller(root, host).promote(m, approval(m))
    assert "activate" not in host.call_log


def test_busy_host_lock_denies_without_journal(tmp_path):
    root, m = fixture(tmp_path)
    host = Host()
    host.busy = True
    with pytest.raises(c.ComponentReleaseDenied, match="HOST_RELEASE_BUSY"):
        controller(root, host).promote(m, approval(m))
    assert list((root / "receipts").iterdir()) == []


def test_provider_acceptance_failure_rolls_back_only_component(tmp_path):
    root, m = fixture(tmp_path)
    host = Host()
    host.fail_acceptance = True
    with pytest.raises(c.ComponentReleaseDenied, match="ACCEPTANCE_FAILED"):
        controller(root, host).promote(m, approval(m))
    assert host.installed is None
    assert "restore" in host.call_log
    assert "freeze_restored" in host.call_log
    assert json.loads(next((root / "receipts").glob("*.json")).read_text())["state"] == "rolled_back"
    assert list((root / "active").iterdir()) == []


def test_protected_container_identity_drift_rolls_back(tmp_path):
    root, m = fixture(tmp_path)
    host = Host()
    orig = host.activate
    def changed(bundle, manifest):
        orig(bundle, manifest)
        host.mutate_protected = True
    host.activate = changed
    with pytest.raises(c.ComponentReleaseDenied, match="PROTECTED_RUNTIME_CHANGED"):
        controller(root, host).promote(m, approval(m))
    assert host.installed is None
    assert "restore" in host.call_log


def test_failed_rollback_leaves_pending_receipt_and_blocks_new_release(tmp_path):
    root, m = fixture(tmp_path)
    host = Host()
    host.fail_acceptance = True
    host.fail_restore = True
    with pytest.raises(c.ComponentReleaseDenied, match="ACCEPTANCE_FAILED"):
        controller(root, host).promote(m, approval(m))
    receipt = json.loads(next((root / "receipts").glob("*.json")).read_text())
    assert receipt["state"] == "started"
    host.installed = None
    host.fail_acceptance = False
    with pytest.raises(c.ComponentReleaseDenied, match="UNRESOLVED_TRANSACTION"):
        controller(root, host).promote(m, approval(m))


def test_untrusted_worktree_never_allowed_as_production_controller(tmp_path):
    root, m = fixture(tmp_path)
    host = Host()
    with pytest.raises(c.ComponentReleaseDenied, match="ROOT_INSTALLED_TRUST_REQUIRED"):
        c.ComponentReleaseController(
            root=root, production=True, host_transaction=host.host_transaction,
            freeze_transaction=host.freeze_transaction,
            verify_protected=host.protected, verify_source_and_ci=host.source,
            verify_image=host.image, observe_component=host.observe,
            activate_component=host.activate, restore_component=host.restore,
            verify_component=host.verify_component,
        )


def test_missing_production_host_callback_denied(tmp_path):
    root, m = fixture(tmp_path)
    host = Host()
    with pytest.raises(c.ComponentReleaseDenied, match="CALLBACK_MISSING"):
        c.ComponentReleaseController(
            root=root, production=False, host_transaction=None,
            freeze_transaction=host.freeze_transaction,
            verify_protected=host.protected, verify_source_and_ci=host.source,
            verify_image=host.image, observe_component=host.observe,
            activate_component=host.activate, restore_component=host.restore,
            verify_component=host.verify_component,
            trusted_public_key=KEY.public_key(),
        )


def test_actual_financial_compose_is_single_service_and_isolated():
    base = Path(__file__).resolve().parents[2]
    compose = (base / "infrastructure" / "financial-statements" / "compose.yaml").read_bytes()
    m = {
        "compose_project": "jason-financial-statements",
        "compose_service": "financial-statements",
    }
    c.validate_compose(compose, m)


def test_interrupted_release_recovers_with_original_signed_proof(tmp_path):
    root, manifest = fixture(tmp_path)
    host = Host()
    host.fail_acceptance = True
    host.fail_restore = True
    with pytest.raises(c.ComponentReleaseDenied, match="ACCEPTANCE_FAILED"):
        controller(root, host).promote(manifest, approval(manifest))
    assert host.installed == manifest["candidate_sha"]
    assert next((root / "receipts").glob("*.json")).is_file()
    host.fail_acceptance = False
    host.fail_restore = False
    recovered = controller(root, host).recover_interrupted_rollback()
    assert recovered["status"] == "component_rollback_verified"
    assert recovered["protected_services_changed"] is False
    assert host.installed is None
    assert not list((root / "active").iterdir())
    record = json.loads(next((root / "receipts").glob("*.json")).read_text())
    assert record["state"] == "rolled_back"
    assert record["reconciled"] is True
    assert controller(root, host).recover_interrupted_rollback() == {
        "status": "nothing_pending", "production_mutation": False,
    }


def test_recovery_rejects_tampered_signed_owner_proof(tmp_path):
    root, manifest = fixture(tmp_path)
    host = Host()
    host.fail_acceptance = True
    host.fail_restore = True
    with pytest.raises(c.ComponentReleaseDenied):
        controller(root, host).promote(manifest, approval(manifest))
    path = next((root / "receipts").glob("*.json"))
    record = json.loads(path.read_text())
    record["signed_owner_proof"]["payload"]["scope_sha256"] = "9" * 64
    path.write_text(json.dumps(record))
    host.fail_acceptance = False
    host.fail_restore = False
    with pytest.raises(PermissionError, match="SIGNATURE_INVALID"):
        controller(root, host).recover_interrupted_rollback()
    assert host.installed == manifest["candidate_sha"]


def test_boundary_forbids_wrong_site_or_delegated_profile(tmp_path):
    root, manifest = fixture(tmp_path)
    bundle = root / "releases" / manifest["candidate_sha"]
    boundary = bundle / "boundary.sqlite3"
    with sqlite3.connect(boundary) as db:
        db.execute("UPDATE client_boundaries SET external_scope_ids=?", (
            json.dumps(["a-different-site"]),))
    # Rebinding the digest alone must not make an incorrect site acceptable.
    manifest["boundary_sha256"] = sha256(boundary.read_bytes()).hexdigest()
    scope = {k: manifest[k] for k in c.SCOPE_FIELDS}
    manifest["scope_sha256"] = sha256(canonical(scope)).hexdigest()
    _json(bundle / "scope.json", scope)
    _json(bundle / "manifest.json", manifest)
    host = Host()
    with pytest.raises(c.ComponentReleaseDenied, match="BOUNDARY_SITE_SCOPE_INVALID"):
        controller(root, host).promote(manifest, approval(manifest))
    assert "activate" not in host.call_log
