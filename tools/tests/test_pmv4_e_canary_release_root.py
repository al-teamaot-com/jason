"""Root-only generic E canary route: one exact component, no provider or PMv3."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_e_canary_release_root as root
from tools import pmv4_e_canary_contract as canary
from tools import independent_component_release as core
from tools.tests import test_pmv4_e_providerfree_canary as fixture


def test_worktree_root_entry_never_promotes_production(monkeypatch):
    with pytest.raises(core.ComponentReleaseDenied,match="INSTALLED_ROOT_ONLY"):
        root.invoke("a"*40)


@pytest.fixture
def fake_prod(tmp_path,monkeypatch):
    sha="a"*40
    base=tmp_path/"root"
    candidate=base/"releases"/sha
    candidate.mkdir(parents=True)
    m=canary.manifest(
        compose=fixture.COMPOSE,config=fixture.CONFIG,
        freeze_sha256="e"*64,candidate_sha=sha)
    (candidate/"manifest.json").write_bytes(core.canonical(m))
    out=tmp_path/"outbox";out.mkdir()
    offer={
        "release_id":core.release_id(sha),
        "candidate_sha":sha,
        "component_id":canary.CANARY_ID,
        "image_digest":canary.IMAGE,
        "organization_id":"aot",
        "signed_owner_proof":{"fixture":"not_real_release_proof"},
    }
    (out/(core.release_id(sha)+".json")).write_bytes(core.canonical(offer))
    monkeypatch.setattr(root,"exact_root",lambda:None)
    monkeypatch.setattr(root,"PRODUCTION_ROOT",base)
    monkeypatch.setattr(root,"OWNER_OUTBOX",out)
    monkeypatch.setattr(root,"trusted_file",lambda path,**kwargs:path.read_bytes())
    class FakeAdapter:
        def __init__(self,**kwargs):
            assert kwargs=={"production":True}
        def host_transaction(self):pass
        def freeze_transaction(self,sha):pass
        def protected(self):pass
        def source_and_ci(self,sha):pass
        def image(self,source,sha):pass
        def observe(self,project):pass
        def activate(self,bundle,manifest):pass
        def restore(self,previous,manifest):pass
        def verify_component(self,bundle,manifest):pass
    monkeypatch.setattr(root,"PinnedCanaryHost",FakeAdapter)
    calls=[]
    class FakeController:
        def __init__(self,**kwargs):
            assert kwargs["production"] is True
            assert kwargs["root"]==base
            calls.append(("controller",set(kwargs)))
        def promote(self,manifest,signed):
            assert signed==offer["signed_owner_proof"]
            calls.append(("promote",manifest["candidate_sha"]))
            return {
                "status":"component_accepted",
                "candidate_sha":sha,"component_id":canary.CANARY_ID,
                "protected_services_changed":False,
            }
    monkeypatch.setattr(root,"ComponentReleaseController",FakeController)
    return sha,candidate,out,calls,offer


def test_exact_accepted_root_uses_original_generic_component_controller(fake_prod):
    sha,_,_,calls,_=fake_prod
    result=root.invoke(sha)
    assert result=={
        "status":"providerfree_native_generic_controller_accepted",
        "source_sha":sha,
        "component_id":canary.CANARY_ID,
        "image_digest":canary.IMAGE,
        "provider_writes":0,
        "protected_service_restarts":0,
        "retirement_authorized":False,
        "legacy_unit_changes":0,
    }
    assert calls==[
        ("controller",{
            "root","production","host_transaction","freeze_transaction",
            "verify_protected","verify_source_and_ci","verify_image",
            "observe_component","activate_component","restore_component",
            "verify_component",
        }),
        ("promote",sha),
    ]


@pytest.mark.parametrize("field,bad",[
    ("component_id","financial-statements"),
    ("compose_project","jason-runtime"),
    ("rollback_sha","f"*40),
    ("image_digest","sha256:"+"f"*64),
    ("provider_scope",{"provider":"microsoft_sharepoint"}),
])
def test_root_rejects_foreign_or_provider_enabled_candidate(fake_prod,field,bad):
    sha,p,_,calls,_=fake_prod
    item=json.loads((p/"manifest.json").read_bytes())
    item[field]=bad
    (p/"manifest.json").write_bytes(core.canonical(item))
    with pytest.raises(core.ComponentReleaseDenied,match="SIGNED_SCOPE_NOT_PROVIDERFREE"):
        root.invoke(sha)
    assert calls==[]


@pytest.mark.parametrize("field,bad",[
    ("candidate_sha","f"*40),
    ("component_id","financial-statements"),
    ("image_digest","sha256:"+"f"*64),
    ("organization_id","other"),
    ("release_id","release-"+"f"*16),
    ("signed_owner_proof",None),
])
def test_missing_or_wrong_exact_owner_offer_denies(fake_prod,field,bad):
    sha,_,out,calls,offer=fake_prod
    bad_offer=dict(offer);bad_offer[field]=bad
    path=out/(core.release_id(sha)+".json")
    path.write_bytes(core.canonical(bad_offer))
    with pytest.raises(core.ComponentReleaseDenied,match="OUTBOX_SCOPE_INVALID"):
        root.invoke(sha)
    assert calls==[]


def test_root_never_accepts_arbitrary_source_sha(fake_prod):
    sha,_,_,calls,_=fake_prod
    with pytest.raises(core.ComponentReleaseDenied,match="SOURCE_NOT_SHA"):
        root.invoke("source-branch")
    assert calls==[]


def test_root_has_no_direct_provider_or_legacy_service_executor():
    raw=Path(root.__file__).read_text()
    for forbidden in (
        "provider_api_key","autotask","sharepoint-write",
        "systemctl stop","systemctl disable","subprocess.run(",
        "docker compose up", "oauth_token",
    ):
        assert forbidden not in raw
    assert "controller.promote(manifest,approval[\"signed_owner_proof\"])" in raw
    assert '"retirement_authorized":False' in raw
