"""Stage E consumes original signed native ledger, never fake Compose approval."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from implementation.kernel.signed_owner_release import (
    issue_exact_owner_release, canonical,
)
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_signed_native_ledger as native
from tools import independent_component_release as original

KEY = Ed25519PrivateKey.generate()
OID = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
CANDIDATE = "b" * 40
ROLLBACK = "a" * 40


def fixture(tmp_path):
    root = tmp_path / "component"
    for x in ("releases", "receipts", "control", "active"):
        (root / x).mkdir(parents=True)
    (root/"control"/"production-deployment-freeze").write_text('{"status":"active"}')
    (root/"control"/"component-release.lock").write_text("unclaimed")
    x = contract.draft(candidate_sha=CANDIDATE, rollback_sha=ROLLBACK)
    bundle = root/"releases"/CANDIDATE
    bundle.mkdir()
    (bundle/"manifest.json").write_bytes(canonical(x["manifest"]))
    (bundle/"source-scope.json").write_bytes(canonical(x["source_scope"]))
    return root, x["manifest"]


def approval(m, *, key=KEY, at=None, approval_id=None):
    return issue_exact_owner_release(
        approval_id=approval_id or "owner-mcp-" + "4"*32,
        release_id=original.release_id(CANDIDATE),
        candidate_sha=CANDIDATE,
        rollback_sha=ROLLBACK,
        scope_sha256=m["source_scope_sha256"],
        manifest_sha256=sha256(canonical(m)).hexdigest(),
        freeze_sha256=m["freeze_sha256"],
        verified_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        verified_owner_oid=OID,
        verified_principal="person-entra-" + OID.replace("-", ""),
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=at or datetime.now(timezone.utc),
        private_key=key,
    )


class Host:
    def __init__(self):
        self.installed = ROLLBACK
        self.calls = []
        self.fail_acceptance = False
        self.fail_restore = False
        self.fail_source = False
        self.changed = False
        self.busy = False
        self.freeze_active = False

    @contextmanager
    def lock(self):
        self.calls.append("host_lock")
        if self.busy:
            raise original.ComponentReleaseDenied("HOST_BUSY")
        try:
            yield
        finally:
            self.calls.append("host_release")

    @contextmanager
    def freeze(self, expected):
        self.calls.append("freeze_lock")
        assert expected == packet.EXPECTED_FREEZE
        self.freeze_active = True
        try:
            yield
        finally:
            self.freeze_active = False
            self.calls.append("freeze_release")

    def protected(self):
        v = "modified" if self.changed else "protected"
        return {
            s: {
                "running":True,"health":"healthy","id":s+"-"+v,
                "image":"sha256:"+"f"*64,"started_at":"2026-11-19T12:00:00Z",
            } for s in original.PROTECTED
        }

    def source(self, sha):
        self.calls.append("source")
        return not self.fail_source and sha == CANDIDATE

    def observe(self, component):
        assert component == contract.COMPONENT
        return self.installed

    def activate(self, bundle, manifest):
        assert self.freeze_active
        self.calls.append("activate")
        self.installed = CANDIDATE

    def restore(self, previous, manifest):
        assert self.freeze_active
        assert previous.name == ROLLBACK
        self.calls.append("restore")
        if self.fail_restore:
            raise RuntimeError("restore intentionally failed")
        self.installed = ROLLBACK
        self.changed = False

    def verify(self, bundle, manifest):
        self.calls.append("verify")
        if bundle.name == CANDIDATE and self.fail_acceptance:
            return False
        return True


def ctl(root, host):
    c = native.StageESignedNativeLedger(
        root=root, source_root=packet.ROOT,
        host_transaction=host.lock, freeze_transaction=host.freeze,
        verify_protected=host.protected, verify_source_and_ci=host.source,
        verify_image=lambda *_: False,
        observe_component=host.observe, activate_component=host.activate,
        restore_component=host.restore, verify_component=host.verify,
        production=False, trusted_public_key=KEY.public_key(),
    )
    def verify_exact_freeze(manifest):
        assert manifest["freeze_sha256"] == packet.EXPECTED_FREEZE
        return b'{"status":"active"}'
    c._freeze_bytes = verify_exact_freeze
    return c


def records(root):
    return [json.loads(p.read_text()) for p in (root/"receipts").glob("*.json")]


def test_signed_native_stage_e_success_uses_original_shared_ledger(tmp_path):
    root, manifest=fixture(tmp_path)
    h=Host()
    result=ctl(root,h).promote(manifest,approval(manifest))
    assert result["status"] == "native_stage_e_six_unit_accepted"
    assert h.installed == CANDIDATE
    assert h.calls.index("host_lock") < h.calls.index("freeze_lock") < h.calls.index("activate")
    assert h.calls.index("activate") < h.calls.index("freeze_release")
    assert records(root)[0]["state"] == "accepted"
    assert records(root)[0]["signed_owner_proof"]
    assert (root/"active"/(contract.COMPONENT+".json")).is_file()
    assert h.freeze_active is False


def test_current_source_only_module_denies_real_production_instantiation(tmp_path):
    root, _=fixture(tmp_path)
    h=Host()
    with pytest.raises(original.ComponentReleaseDenied, match="ROOT_INSTALLED_PIN_REQUIRED"):
        native.StageESignedNativeLedger(
            root=root, source_root=packet.ROOT,
            host_transaction=h.lock, freeze_transaction=h.freeze,
            verify_protected=h.protected, verify_source_and_ci=h.source,
            verify_image=lambda *_: False, observe_component=h.observe,
            activate_component=h.activate, restore_component=h.restore,
            verify_component=h.verify, production=True,
        )


@pytest.mark.parametrize("scenario", [
    "invalid_signature", "expired", "scope", "provider",
    "baseline", "source", "replay",
])
def test_invalid_approval_source_or_scope_does_not_activate(tmp_path, scenario):
    root, manifest=fixture(tmp_path)
    host=Host()
    signer=approval(manifest)
    if scenario == "invalid_signature":
        signer=approval(manifest,key=Ed25519PrivateKey.generate())
    elif scenario == "expired":
        signer=approval(manifest,at=datetime.now(timezone.utc)-timedelta(minutes=25))
    elif scenario == "scope":
        manifest=dict(manifest)
        manifest["source_scope_sha256"]="0"*64
    elif scenario == "provider":
        manifest=dict(manifest)
        manifest["provider_scope"]={"provider":"autotask"}
    elif scenario == "baseline":
        host.installed="c"*40
    elif scenario == "source":
        host.fail_source=True
    elif scenario == "replay":
        (root/"receipts"/("owner-"+"owner-mcp-"+"4"*32+".json")).write_text(
            json.dumps({"approval_id":"owner-mcp-"+"4"*32,"state":"accepted"}))
    with pytest.raises((PermissionError, original.ComponentReleaseDenied)):
        ctl(root,host).promote(manifest,signer)
    assert "activate" not in host.calls
    assert host.installed != CANDIDATE


def test_failed_six_unit_acceptance_restores_exact_original(tmp_path):
    root, manifest=fixture(tmp_path)
    host=Host()
    host.fail_acceptance=True
    with pytest.raises(original.ComponentReleaseDenied, match="LIVE_SIX_UNIT_ACCEPTANCE_FAILED"):
        ctl(root,host).promote(manifest,approval(manifest))
    assert host.installed == ROLLBACK
    assert "restore" in host.calls
    assert records(root)[0]["state"] == "rolled_back"
    assert list((root/"active").iterdir()) == []


def test_failed_restore_retains_started_receipt_for_supervised_recovery(tmp_path):
    root, manifest=fixture(tmp_path)
    host=Host()
    host.fail_acceptance=True
    host.fail_restore=True
    with pytest.raises(original.ComponentReleaseDenied):
        ctl(root,host).promote(manifest,approval(manifest))
    assert host.installed == CANDIDATE
    assert records(root)[0]["state"] == "started"
    assert list((root/"active").iterdir()) == []
    host.fail_restore=False
    result=ctl(root,host).recover_interrupted_rollback()
    assert result["status"] == "native_stage_e_six_unit_rollback_verified"
    assert host.installed == ROLLBACK
    assert records(root)[0]["state"] == "rolled_back"
    assert ctl(root,host).recover_interrupted_rollback()["status"] == "nothing_pending"


def test_signed_recovery_denies_modified_manifest(tmp_path):
    root, manifest=fixture(tmp_path)
    h=Host();h.fail_acceptance=True;h.fail_restore=True
    with pytest.raises(original.ComponentReleaseDenied):
        ctl(root,h).promote(manifest,approval(manifest))
    original_file = root/"releases"/CANDIDATE/"manifest.json"
    original_text=original_file.read_text()
    doc=json.loads(original_text);doc["freeze_sha256"]="0"*64
    original_file.write_text(json.dumps(doc))
    with pytest.raises(original.ComponentReleaseDenied, match="RECOVERY_SCOPE_DRIFT"):
        ctl(root,h).recover_interrupted_rollback()
    assert records(root)[0]["state"] == "started"
    original_file.write_text(original_text)


def test_different_owner_signature_cannot_recover_started(tmp_path):
    root, manifest=fixture(tmp_path)
    h=Host();h.fail_acceptance=True;h.fail_restore=True
    with pytest.raises(original.ComponentReleaseDenied):
        ctl(root,h).promote(manifest,approval(manifest))
    receipt=next((root/"receipts").glob("*.json"))
    row=json.loads(receipt.read_text())
    row["signed_owner_proof"]=approval(manifest,key=Ed25519PrivateKey.generate())
    receipt.write_text(json.dumps(row))
    with pytest.raises(PermissionError,match="SIGNATURE_INVALID"):
        ctl(root,h).recover_interrupted_rollback()
    assert records(root)[0]["state"] == "started"
