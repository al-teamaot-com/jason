"""Existing generic component controller, provider-free exact source-only canary."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from implementation.kernel.signed_owner_release import issue_exact_owner_release
from tools import independent_component_release as core
from tools import pmv4_e_canary_contract as canary

BASE=Path(__file__).resolve().parents[2]
COMPOSE=(BASE/"infrastructure/pmv4-e-canary/compose.yaml").read_bytes()
CONFIG=(BASE/"infrastructure/pmv4-e-canary/config.json").read_bytes()
KEY=Ed25519PrivateKey.generate()
OID="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
OWNER="person-entra-bee80bdcffb04c50b453c09d4d411f5f"
FREEZE=b'{"status":"active"}'
CANDIDATE="a"*40


def packet(tmp_path):
    root=tmp_path/"root"
    for part in ("releases","receipts","control","active"):
        (root/part).mkdir(parents=True)
    (root/"control/production-deployment-freeze").write_bytes(FREEZE)
    (root/"control/component-release.lock").write_bytes(b"unclaimed")
    m=canary.manifest(
        compose=COMPOSE,config=CONFIG,freeze_sha256=sha256(FREEZE).hexdigest(),
        candidate_sha=CANDIDATE)
    bundle=root/"releases"/m["candidate_sha"]
    bundle.mkdir()
    for name,raw in (
        ("compose.yaml",COMPOSE),("config.json",CONFIG),
        ("manifest.json",core.canonical(m)),
        ("scope.json",core.canonical({k:m[k] for k in core.SCOPE_FIELDS})),
    ):
        (bundle/name).write_bytes(raw)
    return root,m


def exact_owner_proof(m):
    return issue_exact_owner_release(
        approval_id="owner-mcp-"+"1"*32,
        release_id=core.release_id(m["candidate_sha"]),
        candidate_sha=m["candidate_sha"],
        rollback_sha=m["rollback_sha"],
        scope_sha256=m["scope_sha256"],
        manifest_sha256=sha256(core.canonical(m)).hexdigest(),
        freeze_sha256=m["freeze_sha256"],
        verified_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        verified_owner_oid=OID,
        verified_principal=OWNER,
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=datetime.now(timezone.utc),
        private_key=KEY,
    )


class NoProviderHost:
    def __init__(self):
        self.calls=[];self.installed=None
        self.fail_acceptance=False;self.fail_restore=False

    @contextmanager
    def lock(self):
        self.calls.append("locked")
        try:yield
        finally:self.calls.append("unlocked")

    @contextmanager
    def freeze(self,_):
        self.calls.append("freeze_locked")
        try:yield
        finally:self.calls.append("freeze_unchanged")

    def protected(self):
        return {name:{
            "running":True,"health":"healthy",
            "id":name+"-original",
            "image":"sha256:"+"f"*64,
            "started_at":"2026-11-18T12:00:00Z",
        } for name in core.PROTECTED}

    def source(self,sha):
        return sha==CANDIDATE

    def image(self,digest,sha):
        return digest==canary.IMAGE and sha==CANDIDATE

    def observe(self,project):
        assert project==canary.CANARY_PROJECT
        return self.installed

    def activate(self,bundle,manifest):
        assert self.calls[-1]=="freeze_locked"
        assert manifest["provider_scope"]==canary.SCOPE
        self.calls.append("isolated_no_provider_activation")
        self.installed=manifest["candidate_sha"]

    def restore(self,previous,manifest):
        assert previous is None
        self.calls.append("rollback_only_isolated_canary")
        if self.fail_restore:
            raise PermissionError("ROLLBACK_NOT_VERIFIED")
        self.installed=None

    def verify(self,bundle,manifest):
        if bundle is not None and self.fail_acceptance:
            return False
        return self.installed==(None if bundle is None else manifest["candidate_sha"])

    def controller(self,root):
        return core.ComponentReleaseController(
            root=root,production=False,
            trusted_public_key=KEY.public_key(),
            host_transaction=self.lock,
            freeze_transaction=self.freeze,
            verify_protected=self.protected,
            verify_source_and_ci=self.source,
            verify_image=self.image,
            observe_component=self.observe,
            activate_component=self.activate,
            restore_component=self.restore,
            verify_component=self.verify,
        )


def test_exact_no_provider_manifest_accepted_by_unchanged_generic_controller(tmp_path):
    root,m=packet(tmp_path)
    native_packet=canary.source_only_canary_packet(
        BASE,freeze_sha256=sha256(FREEZE).hexdigest(),
        candidate_sha=CANDIDATE)
    assert native_packet["manifest"]==m
    assert native_packet["production_mutations"] is False
    assert native_packet["native_controller_production_parity_accepted"] is False
    core.validate_manifest(m)
    core.validate_compose(COMPOSE,m)
    h=NoProviderHost()
    result=h.controller(root).promote(m,exact_owner_proof(m))
    assert result["status"]=="component_accepted"
    assert result["protected_services_changed"] is False
    assert h.installed==CANDIDATE
    assert h.calls.count("isolated_no_provider_activation")==1
    assert h.calls[-1]=="unlocked"
    receipt=json.loads(next((root/"receipts").glob("*.json")).read_text())
    assert receipt["state"]=="accepted"
    assert (root/"active/pmv4-e-canary.json").is_file()
    with pytest.raises(core.ComponentReleaseDenied,match="ROLLBACK_NOT_CURRENT"):
        h.controller(root).promote(m,exact_owner_proof(m))


def test_failed_accepted_canary_rollback_uses_original_controller(tmp_path):
    root,m=packet(tmp_path)
    h=NoProviderHost();h.fail_acceptance=True
    with pytest.raises(core.ComponentReleaseDenied,match="ACCEPTANCE_FAILED"):
        h.controller(root).promote(m,exact_owner_proof(m))
    assert h.installed is None
    assert h.calls.count("rollback_only_isolated_canary")==1
    assert json.loads(next((root/"receipts").glob("*.json")).read_text())["state"]=="rolled_back"
    assert list((root/"active").iterdir())==[]


def test_failed_canary_rollback_preserves_pending_journal(tmp_path):
    root,m=packet(tmp_path)
    h=NoProviderHost();h.fail_acceptance=True;h.fail_restore=True
    with pytest.raises(core.ComponentReleaseDenied,match="ACCEPTANCE_FAILED"):
        h.controller(root).promote(m,exact_owner_proof(m))
    assert json.loads(next((root/"receipts").glob("*.json")).read_text())["state"]=="started"
    h.installed=None
    with pytest.raises(core.ComponentReleaseDenied,match="UNRESOLVED_TRANSACTION"):
        h.controller(root).promote(m,exact_owner_proof(m))


def resolved():
    service={
        "cap_drop":["ALL"],"command":None,
        "entrypoint":["node","-e","setInterval(() => {}, 30000)"],
        "healthcheck":{
            "test":["CMD","node","-e","process.exit(0)"],
            "timeout":"3s","interval":"10s","retries":3,
        },
        "image":canary.IMAGE,
        "mem_limit":str(canary.MEMORY_BYTES),
        "labels":{"com.aot.jason.release_sha":CANDIDATE},
        "networks":{"isolation":None},
        "pids_limit":64,"pull_policy":"never",
        "read_only":True,"restart":"no",
        "security_opt":["no-new-privileges:true"],
        "user":"1000:1000",
        "volumes":[{"type":"bind","source":canary.mount_source(CANDIDATE),
                    "target":"/canary/config.json","read_only":True,
                    "bind":{}}],
    }
    return {
        "name":canary.CANARY_PROJECT,
        "services":{canary.CANARY_ID:service},
        "networks":{"isolation":{
            "name":canary.NETWORK,"ipam":{},"internal":True}},
    }


def test_reviewed_actual_compose_projection_is_provider_free():
    canary.validate_resolved_compose(resolved(),candidate_sha=CANDIDATE)
    assert b"environment" not in COMPOSE
    assert b"role_id" not in COMPOSE
    assert b"secret_id" not in COMPOSE
    assert b"/var/lib/jason/authority" not in COMPOSE
    assert b"ports:" not in COMPOSE
    assert b"internal: true" in COMPOSE
    assert b"${JASON_PMV4_E_CONFIG}:/canary/config.json:ro" in COMPOSE
    assert b"no-new-privileges:true" in COMPOSE


@pytest.mark.parametrize("field,value",[
    ("image","sha256:"+"e"*64),
    ("cap_drop",[]),
    ("read_only",False),
    ("user","root"),
    ("mem_limit","4294967296"),
    ("pids_limit",1024),
    ("pull_policy","always"),
    ("restart","always"),
    ("networks",{}),
    ("command",["bash"]),
    ("environment",{"KEY":"secret"}),
    ("volumes",[{"type":"bind","source":"/var/run/docker.sock",
                 "target":"/var/run/docker.sock","read_only":False}]),
])
def test_resolved_providerfree_service_escalation_denied(field,value):
    a=resolved()
    a["services"][canary.CANARY_ID][field]=value
    with pytest.raises(core.ComponentReleaseDenied,match="PMV4_E_CANARY_"):
        canary.validate_resolved_compose(a,candidate_sha=CANDIDATE)


@pytest.mark.parametrize("field,value",[
    ("name","jason-runtime"),
    ("networks",{"isolation":{"name":"jason-core","internal":True}}),
    ("services",{"openbao":{}}),
])
def test_foreign_production_network_project_or_service_denied(field,value):
    a=resolved();a[field]=value
    with pytest.raises(core.ComponentReleaseDenied,match="PMV4_E_CANARY_"):
        canary.validate_resolved_compose(a,candidate_sha=CANDIDATE)


def image_record():
    return {"Id":canary.IMAGE,"Config":{"Labels":{
        "com.aot.jason.component":"pmv4-shadow",
        "com.aot.jason.lifecycle":"preproduction-only",
        "com.aot.jason.production-core":"excluded",
        "com.aot.jason.provider-mutations":"disabled",
        "com.aot.jason.source_revision":canary.IMAGE_SOURCE,
    }}}


def test_reviewed_existing_image_labels_are_strict():
    canary.validate_exact_image(image_record())


@pytest.mark.parametrize("field,bad",[
    ("com.aot.jason.component","jason-runtime"),
    ("com.aot.jason.lifecycle","production"),
    ("com.aot.jason.production-core","included"),
    ("com.aot.jason.provider-mutations","enabled"),
    ("com.aot.jason.source_revision","a"*40),
])
def test_existing_image_security_label_change_denied(field,bad):
    x=image_record();x["Config"]["Labels"][field]=bad
    with pytest.raises(core.ComponentReleaseDenied,match="IMAGE_SECURITY_LABELS_NOT_PINNED"):
        canary.validate_exact_image(x)


def test_wrong_content_address_never_accepted():
    x=image_record();x["Id"]="sha256:"+"e"*64
    with pytest.raises(core.ComponentReleaseDenied,match="IMAGE_NOT_PINNED"):
        canary.validate_exact_image(x)


def test_original_financial_controller_and_adapter_unchanged():
    root=BASE
    controller=(root/"tools/independent_component_release.py").read_bytes()
    adapter=(root/"tools/independent_component_host_adapter.py").read_bytes()
    assert sha256(controller).hexdigest()=="1e6f981344f6bfb87977f2d3f4c5e76875447efd78aba03a8968ba94240bd4c7"
    assert sha256(adapter).hexdigest()=="36f667fd53c2410a902772d3fae7cec7b08f89f99d71f71009c5a8f8029dedce"


def test_canary_source_only_does_not_grant_retirement():
    result=canary.source_only_canary_packet(
        BASE,freeze_sha256=sha256(FREEZE).hexdigest(),
        candidate_sha=CANDIDATE)
    assert result["owner_approval_issued"] is False
    assert result["root_installed"] is False
    assert result["native_controller_production_parity_accepted"] is False
    assert result["production_mutations"] is False
