"""A1 failed-transaction rollback proves original authorization without reauth."""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
import os
from pathlib import Path
from types import SimpleNamespace
import stat

import pytest

from tools import pmv4_a1_v3_recover_consumed_owner as rec


@pytest.fixture
def pending(tmp_path,monkeypatch):
    receipt=tmp_path/("owner-"+rec.APPROVAL_ID+".json")
    data={
        "schema_version":"1.0","service":"jason-pmv4-shadow",
        "state":"started","release_id":"release-"+rec.SOURCE[:16],
        "approval_id":rec.APPROVAL_ID,"candidate_sha":rec.SOURCE,
        "rollback_sha":rec.ROLLBACK,"manifest_sha256":"a"*64,
        "scope_sha256":"b"*64,"freeze_sha256":"c"*64,
        "started_at":datetime.now(timezone.utc).isoformat(),
        "no_pmv3_or_provider_mutation":True,
    }
    receipt.write_text(json.dumps(data)); receipt.chmod(0o600)
    monkeypatch.setattr(rec,"RECEIPT",receipt)
    return receipt,data


def test_exact_original_pending_receipt_read(pending):
    receipt,data=pending
    assert rec.read_exact_receipt(expected_uid=os.geteuid(),expected_gid=os.getegid())==data


@pytest.mark.parametrize("field,wrong",[
    ("state","accepted"),("approval_id","owner-mcp-other"),
    ("candidate_sha","f"*40),("rollback_sha","2"*40),
    ("no_pmv3_or_provider_mutation",False),
    ("release_id","release-unrelated"),
])
def test_recovery_cannot_use_unrelated_transaction(pending,field,wrong):
    receipt,data=pending
    data[field]=wrong
    receipt.write_text(json.dumps(data))
    with pytest.raises(rec.A1RecoveryDenied):
        rec.read_exact_receipt(expected_uid=os.geteuid(),expected_gid=os.getegid())


def test_receipt_wrong_permissions_denied(pending):
    receipt,data=pending
    receipt.chmod(0o666)
    with pytest.raises(rec.A1RecoveryDenied,match="METADATA_CHANGED"):
        rec.read_exact_receipt(expected_uid=os.geteuid(),expected_gid=os.getegid())


def test_receipt_foreign_duplicate_denied(pending):
    receipt,data=pending
    foreign=receipt.parent/("owner-"+"f"*32+".json")
    foreign.write_text("{}")
    foreign.chmod(0o600)
    with pytest.raises(rec.A1RecoveryDenied,match="UNTRUSTED_RECEIPT_OBJECT"):
        rec.read_exact_receipt(expected_uid=os.geteuid(),expected_gid=os.getegid())


def test_root_entrypoint_must_be_new_exact_root_copy():
    if os.geteuid()!=0:
        with pytest.raises(rec.A1RecoveryDenied,match="ROOT_TTY_REQUIRED"):
            rec.is_real_root_script()


def test_recover_uses_native_signed_rollback_and_no_new_owner(pending,monkeypatch):
    receipt,data=pending
    prior=receipt.parent/"releases"/rec.ROLLBACK
    prior.mkdir(parents=True)
    (prior/"baseline.json").write_text(json.dumps({
        "schema_version":"1.0","service":"jason-pmv4-shadow",
        "baseline":"no_prior_shadow_runtime"}))
    pointer=receipt.parent/"current"
    pointer.symlink_to("releases/"+rec.ROLLBACK)
    original_token=receipt.parent/"gateway-token"
    original_token.write_text("synthetic")
    control=receipt.parent/"fixture-global-freeze"
    control.write_bytes(b"same")
    audit=[{"event":"requires_review"}]
    events=[]

    class FakeController:
        def _reconcile_pending_rollback_locked(self,*,rollback_acceptance):
            events.append("native-reconcile-under-lock")
            assert rollback_acceptance(prior) is True
            data.update(state="rolled_back",finished_at="synthetic",reconciled=True)
            receipt.write_text(json.dumps(data))
            return {"status":"shadow_rollback_verified",
                    "rollback_sha":rec.ROLLBACK}

    class FakeAdapter:
        def _owned_or_absent(self):
            return None

    class FakeHost:
        def _assert_protected_release_state(self):pass
        @contextmanager
        def host_release_transaction(self):
            events.append("dual-lock-acquired")
            yield
            events.append("dual-lock-released")
        def preexisting_core_health(self):return True
        def protected_release_status(self):return {"ready":True}

    class FakeOriginal:
        CURRENT=pointer
        TARGET=receipt.parent/"not-present-target"
        APPROVED=receipt.parent/"not-present-approved"
        REVIEWED=receipt.parent/"not-present-review"
        TOKEN=receipt.parent/"not-present-token"
        GLOBAL_FREEZE=control
        GLOBAL_HOLD=control
        FREEZE_SHA="fixed"
        HOLD_SHA="fixed"
        shadow=SimpleNamespace(read_json=lambda x:json.loads(x.read_text()))
        def sha(self,_raw):return "fixed"
        def cleanup_exact_unpromoted(self,approval):
            assert approval==rec.APPROVAL_ID
            events.append("only-original-audit-files-cleaned")
        def audit_rows(self):return audit
        def append(self,event,approval,details):
            assert approval==rec.APPROVAL_ID
            assert details.get("new_owner_approval") is False
            audit.append({"event":event})
            events.append(event)

    original=FakeOriginal()
    monkeypatch.setattr(rec,"preflight",lambda:(
        original,FakeHost(),FakeAdapter(),FakeController(),{}
    ))
    monkeypatch.setattr(rec,"inspect_exact_shadow",lambda:None)
    monkeypatch.setattr(rec,"only_exact_compose_project",lambda **_:None)
    monkeypatch.setattr(rec,"authenticate_historical_recovery",lambda *a:None)
    monkeypatch.setattr(rec,"read_exact_receipt",lambda:data)
    monkeypatch.setattr(rec,"postflight",lambda:events.append("postflight"))
    rec.recover()
    assert data["state"]=="rolled_back"
    assert events.index("dual-lock-acquired") < events.index(
        "native-reconcile-under-lock")
    assert events.index("native-reconcile-under-lock") < events.index(
        "only-original-audit-files-cleaned")
    assert events.index("only-original-audit-files-cleaned") < events.index(
        "reconciled_original_exact_owner_rollback")
    assert events.index("dual-lock-released") < events.index("postflight")


def test_recovery_does_not_modify_original_files_if_unproven(pending,monkeypatch):
    receipt,data=pending
    before=receipt.read_bytes()
    def denied():
        raise rec.A1RecoveryDenied("A1_ORIGINAL_SIGNATURE_INVALID")
    monkeypatch.setattr(rec,"preflight",denied)
    with pytest.raises(rec.A1RecoveryDenied,match="SIGNATURE_INVALID"):
        rec.recover()
    assert receipt.read_bytes()==before


def test_recovery_refuses_new_promotion_and_auth():
    script=(Path(__file__).resolve().parents[1]/
            "tools/pmv4_a1_v3_recover_consumed_owner.py").read_text()
    for prohibited in ("--execute", "--authorize","--promote",
                       "issue_exact_owner_release(", "create_subprocess_shell("):
        assert prohibited not in script
    assert "_reconcile_pending_rollback_locked(" in script
    assert "cleanup_exact_unpromoted(" in script


def test_historical_signature_pair_bound_to_native_receipt(tmp_path,monkeypatch):
    from hashlib import sha256
    from types import SimpleNamespace
    import copy
    payload={
        "approval_id":rec.APPROVAL_ID,
        "issued_at":datetime.now(timezone.utc).isoformat(),
        "expires_at":datetime.now(timezone.utc).isoformat(),
        "owner_oid":"synthetic-owner",
        "owner_principal":"synthetic@invalid.local",
    }
    proof={
        "schema_version":"1.0","approval_id":rec.APPROVAL_ID,
        "source_sha":rec.SOURCE,"scope_sha256":rec.EXACT_SCOPE,
        "signed_root_release":{"payload":copy.deepcopy(payload)},
        "signed_shadow_release":{"payload":copy.deepcopy(payload)},
    }
    manifest={"candidate_sha":rec.SOURCE,"rollback_sha":rec.ROLLBACK,
              "scope_sha256":"e"*64}
    canon=lambda value:json.dumps(value,sort_keys=True).encode()
    sha=lambda raw:sha256(raw).hexdigest()
    plan={"scope_sha256":rec.EXACT_SCOPE,
          "shadow_manifest_sha256":"f"*64,
          "shadow_freeze_sha256":"a"*64}
    proof["manifest_sha256"]=sha(canon(plan))
    receipt={"manifest_sha256":sha(canon(manifest)),
             "scope_sha256":manifest["scope_sha256"],
             "freeze_sha256":plan["shadow_freeze_sha256"],
             "started_at":datetime.now(timezone.utc).isoformat()}
    journal=[{"event":"begin","approval_id":rec.APPROVAL_ID,
              "details":{"parent_scope_sha256":rec.EXACT_SCOPE,
                         "shadow_manifest_sha256":"f"*64}},
             {"event":"requires_review","approval_id":rec.APPROVAL_ID}]
    original=SimpleNamespace(
        plan_and_source=lambda:(plan,manifest,{}),
        read_json=lambda *_args,**_kwargs:proof,
        sha=sha,canon=canon,audit_rows=lambda:journal,
        ROOT_PIN=tmp_path/"mock-root-public-key",
    )
    monkeypatch.setattr(rec.shadow,"read_pinned_root_owner_public_key",
                        lambda *_args,**_kwargs:object())
    calls=[]
    def verifier(signed,**kw):
        calls.append(kw)
        assert kw["expected_candidate_sha"]==rec.SOURCE
        assert kw["expected_rollback_sha"]==rec.ROLLBACK
        assert kw["expected_freeze_sha256"]==plan["shadow_freeze_sha256"]
        return signed["payload"]
    monkeypatch.setattr(rec.shadow,"verify_exact_owner_release",verifier)
    assert rec.authenticate_historical_recovery(original,receipt)==plan
    assert len(calls)==2
    assert {x["expected_scope_sha256"] for x in calls}=={
        rec.EXACT_SCOPE,manifest["scope_sha256"]}
    bad_receipt=dict(receipt,manifest_sha256="0"*64)
    with pytest.raises(rec.A1RecoveryDenied,
                       match="NATIVE_JOURNAL_NOT_SIGNED_CHILD"):
        rec.authenticate_historical_recovery(original,bad_receipt)
    proof["signed_shadow_release"]["payload"]["owner_oid"]="other-owner"
    with pytest.raises(rec.A1RecoveryDenied,match="ONE_OWNER_PROOF_PAIR"):
        rec.authenticate_historical_recovery(original,receipt)
    journal[0]["details"]["parent_scope_sha256"]="0"*64
    with pytest.raises(rec.A1RecoveryDenied,match="ROOT_AUDIT_NOT_PENDING"):
        rec.authenticate_historical_recovery(original,receipt)


def _sample_docker29_shadow():
    return {
        "Id": rec.EXACT_CONTAINER_ID,
        "Image": rec.EXACT_IMAGE,
        "Name": "/" + rec.SHADOW,
        "Config": {
            "Labels": {
                "com.aot.jason.component": "pmv4-shadow",
                "com.aot.jason.production-core": "excluded",
                "com.aot.jason.provider-mutation": "disabled",
                "com.docker.compose.project": rec.PROJECT,
                "com.docker.compose.service": "pmv4-shadow-gateway",
            },
            "User": "1000:1000",
            "Env": ["HOME=/home/node", "OPENCLAW_GATEWAY_TOKEN=synthetic"],
        },
        "HostConfig": {
            "NetworkMode": "none", "ReadonlyRootfs": True,
            "Privileged": False, "CapDrop": ["ALL"], "CapAdd": None,
            "SecurityOpt": ["no-new-privileges:true"],
            "Init": True, "RestartPolicy": {"Name": "no"},
            "PidsLimit": 256, "Memory": 2 * 1024 ** 3,
            "NanoCpus": 1_000_000_000,
            "PublishAllPorts": False, "PortBindings": {},
            "Devices": None, "Binds": [rec.EXPECTED_BIND],
        },
        "Mounts": [{
            "Type": "volume", "Name": rec.VOLUME,
            "Destination": "/home/node/.openclaw",
        }],
    }


def test_exact_real_docker29_named_volume_runtime_accepted_for_recovery():
    rec.validate_exact_running_shadow(_sample_docker29_shadow())


@pytest.mark.parametrize("change", [
    lambda d: d.__setitem__("Id", "0" * 64),
    lambda d: d.__setitem__("Image", "sha256:" + "0" * 64),
    lambda d: d["HostConfig"].__setitem__("NetworkMode", "bridge"),
    lambda d: d["HostConfig"].__setitem__("Privileged", True),
    lambda d: d["HostConfig"].__setitem__("CapDrop", []),
    lambda d: d["HostConfig"].__setitem__("SecurityOpt", []),
    lambda d: d["HostConfig"].__setitem__("Memory", 0),
    lambda d: d["HostConfig"].__setitem__("PidsLimit", 64),
    lambda d: d["HostConfig"].__setitem__("Binds", ["/etc:/etc:ro"]),
    lambda d: d["HostConfig"].__setitem__("Binds", [rec.EXPECTED_BIND, "/:/host:ro"]),
    lambda d: d["Mounts"][0].__setitem__("Type", "bind"),
    lambda d: d["Mounts"][0].__setitem__("Name", "production-secret-volume"),
    lambda d: d["Mounts"].append({
        "Type": "bind", "Destination": "/var/lib/jason",
    }),
    lambda d: d["Config"]["Env"].append("AWS_SECRET_ACCESS_KEY=synthetic"),
])
def test_unrelated_docker_object_or_security_relaxation_does_not_recover(change):
    import copy
    sample = copy.deepcopy(_sample_docker29_shadow())
    change(sample)
    with pytest.raises(rec.A1RecoveryDenied):
        rec.validate_exact_running_shadow(sample)


def test_native_rolled_back_receipt_may_be_finalized_after_interruption(pending):
    receipt, record = pending
    record.update(state="rolled_back", reconciled=True, finished_at="synthetic")
    receipt.write_text(json.dumps(record))
    assert rec.read_exact_receipt(
        expected_uid=os.geteuid(), expected_gid=os.getegid()
    )["state"] == "rolled_back"


def test_older_settled_receipt_does_not_consume_new_action(pending):
    receipt, record = pending
    old_id = "owner-mcp-" + "f" * 32
    old_path = receipt.parent / ("owner-" + old_id + ".json")
    old_path.write_text(json.dumps({
        "approval_id": old_id, "state": "rolled_back",
    }))
    old_path.chmod(0o600)
    assert rec.read_exact_receipt(
        expected_uid=os.geteuid(), expected_gid=os.getegid()
    )["state"] == "started"


def test_original_compose_down_stays_fixed_scoped_and_preserves_volumes(
    tmp_path, monkeypatch
):
    compose = tmp_path / "control" / "docker-compose.yml"
    compose.parent.mkdir()
    compose.write_text("fake-rollback-config")
    compose.chmod(0o640)
    token = tmp_path / "gateway-token"
    token.write_text("synthetic-only-" + "x" * 40)
    real_lstat = Path.lstat

    def scoped_lstat(path):
        data = real_lstat(path)
        if path == compose:
            return SimpleNamespace(
                st_uid=0, st_nlink=data.st_nlink, st_mode=data.st_mode
            )
        return data

    monkeypatch.setattr(Path, "lstat", scoped_lstat)
    runner_calls = []

    def fake_run(argv, **kwargs):
        runner_calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(rec.subprocess, "run", fake_run)
    monkeypatch.setattr(rec, "inspect_exact_shadow", lambda: None)
    monkeypatch.setattr(rec, "only_exact_compose_project", lambda **_: None)
    original = SimpleNamespace(
        ROOT=tmp_path, TOKEN=token,
        sha=lambda _: "892f7a506fcb759887697f4a9882a76e2377969a701a4ca1aff240f6cb23277b",
    )
    rec.shutdown_original_shadow(original)
    assert len(runner_calls) == 1
    argv, kwargs = runner_calls[0]
    assert argv == [
        "/usr/bin/docker", "compose", "--project-name", rec.PROJECT,
        "-f", str(compose), "down",
    ]
    assert "--volumes" not in argv and "--remove-orphans" not in argv
    assert kwargs["shell"] is False
    assert kwargs["env"]["PMV4_SHADOW_IMAGE_SHA"] == rec.EXACT_IMAGE
