"""Exact boot-readback maintenance: pure and disposable transaction tests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from tools import scoped_backport_boot_readback_reconcile as r
from tools.scoped_backport_release import canonical, digest


def fixture():
    manifest = {"schema_version": "3.0", "release_id": "release-" + "a" * 16,
                "scope_sha256": "b" * 64}
    rows = {name: {"revision": str(i+1)*40, "image_id": "sha256:"+str(i+1)*64,
                   "container_id": str(i+4)*64}
            for i, name in enumerate(r.readback.COMPONENTS)}
    policy = b"synthetic retirement policy"
    old = {"schema_version": "3.0", "status": "verified_component_release",
           "host_revision": "c"*40, "release_id": manifest["release_id"],
           "manifest_sha256": digest(manifest), "scope_sha256": manifest["scope_sha256"],
           "release_policy_sha256": sha256(policy).hexdigest(), "components": rows}
    fingerprints = {name: str(i+1)*64 for i, name in enumerate(rows)}
    approval_id = "owner-mcp-" + "a"*32
    historical = {"outcome": "production_components_verified", "mutation_attempted": True,
                  "proposed_readback": old, "release_id": old["release_id"],
                  "manifest_sha256": old["manifest_sha256"],
                  "scope_sha256": old["scope_sha256"],
                  "candidate_ids": {k:v["container_id"] for k,v in rows.items()},
                  "approval_id": approval_id, "original_configs": fingerprints}
    actual = deepcopy(rows)
    actual[r.RUNTIME]["container_id"] = "9"*64
    consumed = {"schema_version": "2.0", "one_use": True,
                "release_id": old["release_id"], "approval_id": approval_id}
    return {"before": canonical(old), "historical": canonical(historical),
            "actual": actual, "fingerprints": fingerprints,
            "host_revision": old["host_revision"], "policy_sha256": old["release_policy_sha256"],
            "manifest": manifest, "consumed": consumed}, policy


def test_plan_changes_one_container_id_and_preserves_original():
    args, _ = fixture()
    plan, new = r.make_plan(**args)
    expected = json.loads(args["before"])
    expected["components"][r.RUNTIME]["container_id"] = "9"*64
    assert new == expected
    assert plan["approved_record_sha256"] == sha256(args["before"]).hexdigest()
    assert plan["transaction_sha256"] == sha256(args["historical"]).hexdigest()
    assert plan["proposed_readback_canonical_sha256"] == digest(new)
    assert plan["action"] == r.ACTION
    assert json.loads(args["historical"])["proposed_readback"] == json.loads(args["before"])


@pytest.mark.parametrize("fault", [
    "other_id", "runtime_image", "runtime_revision", "same_id", "extra_component",
    "config", "policy", "host", "journal", "candidate_id", "approval", "unconsumed",
])
def test_any_foreign_evidence_fails_closed(fault):
    a, _ = fixture()
    if fault == "other_id":
        a["actual"]["jason-mcp-pilot"]["container_id"] = "8"*64
    elif fault == "runtime_image":
        a["actual"][r.RUNTIME]["image_id"] = "sha256:"+"f"*64
    elif fault == "runtime_revision":
        a["actual"][r.RUNTIME]["revision"] = "f"*40
    elif fault == "same_id":
        a["actual"] = json.loads(a["before"])["components"]
    elif fault == "extra_component":
        a["actual"]["foreign"] = {}
    elif fault == "config":
        a["fingerprints"][r.RUNTIME] = "0"*64
    elif fault == "policy":
        a["policy_sha256"] = "0"*64
    elif fault == "host":
        a["host_revision"] = "0"*40
    elif fault in ("journal", "candidate_id"):
        j = json.loads(a["historical"])
        if fault == "journal":
            j["outcome"] = "rollback_verified"
        else:
            j["candidate_ids"][r.RUNTIME] = "9"*64
        a["historical"] = canonical(j)
    elif fault == "approval":
        a["consumed"]["approval_id"] = "owner-mcp-"+"c"*32
    elif fault == "unconsumed":
        a["consumed"]["one_use"] = False
    with pytest.raises(PermissionError):
        r.make_plan(**a)


def signed_fixture(owner=None):
    args, policy = fixture()
    plan, new = r.make_plan(**args)
    offer = r.maintenance_offer(plan, "e"*40, "d"*40, "c"*40, digest(plan))
    key = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    oid = owner or r.signing.OWNER_OID
    proof = r.signing.issue_exact_owner_release(
        approval_id="owner-mcp-"+"b"*32, release_id=offer["release_id"],
        candidate_sha=offer["candidate_sha"], rollback_sha=offer["rollback_sha"],
        scope_sha256=digest(offer), manifest_sha256=digest(offer),
        release_policy_sha256=offer["release_policy_sha256"],
        verified_tenant_id=r.signing.TID, verified_owner_oid=oid,
        verified_principal=r.signing.EXACT_OWNER_OAUTH_SUBJECTS[oid],
        verified_organization_id="aot", confirmed_decision="approve",
        at=now, private_key=key)
    return args, policy, plan, new, offer, proof, key, now


def test_maintenance_proof_binds_current_source_and_recovery():
    _, _, _, _, offer, proof, key, now = signed_fixture()
    assert r.verify_decision(proof, offer, key=key.public_key(), at=now,
                             consumed=frozenset())["owner_oid"] == r.signing.OWNER_OID
    for field in ("installer_sha", "candidate_sha", "rollback_sha", "recovery_scope_sha256"):
        changed = dict(offer, **{field:"f"*len(offer[field])})
        with pytest.raises(PermissionError):
            r.verify_decision(proof, changed, key=key.public_key(), at=now, consumed=frozenset())
    with pytest.raises(PermissionError):
        r.verify_decision(proof, offer, key=key.public_key(), at=now,
                         consumed=frozenset({proof["payload"]["approval_id"]}))
    with pytest.raises(PermissionError):
        r.verify_decision(proof, offer, key=key.public_key(),
                         at=now+timedelta(minutes=20), consumed=frozenset())


def test_admin_is_not_licensed_owner_for_maintenance():
    _, _, _, _, offer, proof, key, now = signed_fixture(r.signing.ADMIN_OWNER_OID)
    with pytest.raises(PermissionError, match="LICENSED_OWNER_REQUIRED"):
        r.verify_decision(proof, offer, key=key.public_key(), at=now, consumed=frozenset())


@pytest.mark.parametrize("fault", ["none", "denied_proof", "consumption_failure", "native_readback", "foreign_file"])
def test_exact_maintenance_disposable_transaction(tmp_path, monkeypatch, fault):
    a, policy, plan, new, offer, proof, key, _ = signed_fixture()
    path, journal = tmp_path/"component.json", tmp_path/"historical.json"
    ledger, consumed = tmp_path/"maintenance", tmp_path/"consumed"
    ledger.mkdir(); consumed.mkdir()
    path.write_bytes(a["before"]); journal.write_bytes(a["historical"])
    calls = []
    monkeypatch.setattr(r, "LEDGER", ledger)
    monkeypatch.setattr(r, "CONSUMED", consumed)
    monkeypatch.setattr(r.readback, "READBACK", path)
    monkeypatch.setattr(r, "read_offer", lambda: offer)
    monkeypatch.setattr(r.signing, "read_pinned_root_owner_public_key", lambda _: key.public_key())
    monkeypatch.setattr(r.live, "root_directory", lambda _: None)
    monkeypatch.setattr(r.live, "exact_file", lambda p, **kw: p.read_bytes())
    monkeypatch.setattr(r.readback, "_root_read", lambda _: policy)
    monkeypatch.setattr(r.live, "required_container", lambda name: name)
    monkeypatch.setattr(r.live, "config_fingerprint", lambda name: a["fingerprints"][name])

    def write_record(p, value):
        assert not p.exists()
        if fault == "consumption_failure" and p.parent == consumed:
            raise OSError("synthetic consumption failure")
        p.write_bytes(canonical(value))
        calls.append(("record", p.parent.name))
    monkeypatch.setattr(r.live, "atomic_root_json", write_record)

    def replace(p, before, after, mode):
        assert calls[-1] == ("record", "consumed")
        assert p.read_bytes() == before and mode == 0o644
        p.write_bytes(b"foreign" if fault == "foreign_file" else after)
        calls.append(("replace", p.name))
    monkeypatch.setattr(r, "atomic_exact_root_file", replace)

    def verify():
        if fault in ("native_readback", "foreign_file"):
            raise PermissionError("synthetic native denial")
        return json.loads(path.read_bytes())
    monkeypatch.setattr(r.readback, "verify_live", verify)

    def restore(changes):
        for p, before, after, _ in changes:
            if p.read_bytes() == after:
                p.write_bytes(before)
            else:
                assert p.read_bytes() == before, "foreign mutation not overwritten"
    monkeypatch.setattr(r, "restore_attempted_root_files", restore)
    host = SimpleNamespace(_locked=lambda: calls.append(("lock", "held")),
                           _require_current_staged_scope=lambda: None,
                           consumed_approvals=lambda: frozenset(),
                           snapshot_protected=lambda: {"peer":"same"},
                           verify_protected_unchanged=lambda peers: peers == {"peer":"same"},
                           _journal_path=lambda m: journal)
    if fault == "denied_proof":
        proof = {}
    if fault == "none":
        result = r.apply_exact(host, a["manifest"], offer, plan, new, a["before"], a["historical"], proof)
        assert result["native_breaker_revalidation_required"] is True
        assert json.loads(path.read_bytes()) == new
        assert len(list(consumed.glob("*.json"))) == 1
    else:
        with pytest.raises((PermissionError, OSError, AssertionError)):
            r.apply_exact(host, a["manifest"], offer, plan, new, a["before"], a["historical"], proof)
        if fault == "foreign_file":
            assert path.read_bytes() == b"foreign"
        else:
            assert path.read_bytes() == a["before"]
        if fault == "denied_proof":
            assert not list(ledger.glob("*.json")) and not list(consumed.glob("*.json"))
    assert journal.read_bytes() == a["historical"]



def test_maintenance_reads_root_authority_not_worker_projection(monkeypatch):
    calls = []
    control = {"schema_version":"1.0", "circuit_breaker":{
        "state":"open", "reason":"continuous_production_drift_detected"}}
    drift = {"schema_version":"1.0", "status":"pass", "problems":[],
             "observed_at":datetime.now(timezone.utc).isoformat()}
    def trusted_read(path):
        calls.append(str(path))
        return control if path.name == "production-control-state.json" else drift
    monkeypatch.setattr(r.live, "root_json", trusted_read)
    assert r.native_health() == (control, drift)
    assert calls == [
        "/var/lib/jason/openclaw/release-manager/production-control-state.json",
        "/var/lib/jason/openclaw/release-manager/production-drift.json",
    ]
    drift["problems"] = [{"kind":"synthetic"}]
    with pytest.raises(PermissionError, match="NATIVE_HEALTH_BOUNDARY"):
        r.native_health()
