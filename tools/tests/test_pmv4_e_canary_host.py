"""Provider-free companion: same signed generic root controller, no finance edits."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_e_canary_host as adapter
from tools import pmv4_e_canary_contract as contract
from tools import independent_component_release as generic
from tools.tests import test_pmv4_e_providerfree_canary as source

CAN=source.CANDIDATE
BUNDLE=Path("/var/lib/jason/independent-component-release/releases")/CAN


class FakeExistingHost:
    def __init__(self):
        self.cmds=[]
        self.extra=None
        self.container=False
        self.corrupt=None
        self.ci_source=CAN

    @contextmanager
    def host_transaction(self):
        yield

    @contextmanager
    def freeze_transaction(self,sha):
        yield

    def protected(self):
        return {name:{
            "running":True,"health":"healthy",
            "id":name+"-stable","image":"sha256:"+"e"*64,
            "started_at":"2026-11-18T14:00:00Z",
        } for name in generic.PROTECTED}

    def source_and_ci(self,sha):
        return sha==self.ci_source

    def _run(self,args,*,env=None,timeout=30):
        self.cmds.append((list(args),dict(env or {})))
        if args[1:3]==["image","inspect"]:
            return json.dumps([source.image_record()])
        if args[1:3]==["network","inspect"]:
            return json.dumps([{
                "Name":contract.NETWORK,"Internal":True,
                "Driver":"bridge","Attachable":False,
                "Containers":{"synthetic-container":{}},
            }])
        if "config" in args:
            v=source.resolved()
            if self.extra:
                field,value=self.extra
                v["services"][contract.CANARY_ID][field]=value
            return json.dumps(v)
        if args[1]=="ps":
            return "synthetic-container\n" if self.container else ""
        if args[1]=="inspect":
            row={
                "Id":"synthetic-container","Image":contract.IMAGE,
                "State":{"Running":True,
                         "Health":{"Status":"healthy"}},
                "HostConfig":{
                    "Memory":contract.MEMORY_BYTES,
                    "PidsLimit":64,"Privileged":False,"ReadonlyRootfs":True,
                    "NetworkMode":contract.NETWORK,
                    "PortBindings":{},"CapDrop":["ALL"],
                    "SecurityOpt":["no-new-privileges:true"],
                },
                "Config":{
                    "User":"1000:1000",
                    "Labels":{
                        "com.docker.compose.project":contract.CANARY_PROJECT,
                        "com.docker.compose.service":contract.CANARY_ID,
                        "com.aot.jason.release_sha":CAN,
                    },
                },
                "Mounts":[{
                    "Source":contract.mount_source(CAN),
                    "Destination":"/canary/config.json","RW":False,
                }],
                "NetworkSettings":{"Networks":{contract.NETWORK:{}}},
            }
            if self.corrupt:
                group,key,value=self.corrupt
                row[group][key]=value
            return json.dumps([row])
        return ""


def fake_adapter():
    f=FakeExistingHost()
    return adapter.PinnedCanaryHost(production=False,legacy=f),f


def manifest():
    return contract.manifest(
        compose=source.COMPOSE,config=source.CONFIG,
        freeze_sha256="c"*64,candidate_sha=CAN)


def test_providerfree_companion_uses_only_original_generic_adapters():
    h,f=fake_adapter()
    assert h.host_transaction
    assert h.freeze_transaction
    assert h.source_and_ci(CAN) is True
    assert h.image(contract.IMAGE,CAN) is True
    assert h.image("sha256:"+"f"*64,CAN) is False
    assert h.image(contract.IMAGE,"0"*40) is True
    assert f.cmds[-1][0]==["/usr/bin/docker","image","inspect",contract.IMAGE]


def test_providerfree_companion_resolves_only_exact_compose(tmp_path,monkeypatch):
    h,f=fake_adapter()
    b=tmp_path/"bundle";b.mkdir()
    (b/"compose.yaml").write_bytes(source.COMPOSE)
    # Source bundle path is pinned by root source, but this synthetic
    # injected Host test uses production=False and no privileged effects.
    h._compose(b,manifest(),operation=None)
    assert len(f.cmds)==1
    args,env=f.cmds[0]
    assert args==[
        "/usr/bin/docker","compose","--project-name",contract.CANARY_PROJECT,
        "--file",str(b/"compose.yaml"),
        "config","--format","json",
    ]
    assert env=={
        "PATH":"/usr/bin:/bin",
        "JASON_PMV4_E_CONFIG":str(b/"config.json"),
        "JASON_PMV4_E_SOURCE":CAN,
    }
    assert not any("SECRET" in key or "AUTH" in key for key in env)


@pytest.mark.parametrize("field,value",[
    ("image","sha256:"+"f"*64),
    ("volumes",[]),
    ("ports",["443:443"]),
    ("networks",{}),
    ("privileged",True),
    ("environment",{"TOKEN":"unreviewed"}),
])
def test_companion_rejects_resolved_extra_privileges_before_action(tmp_path,field,value):
    h,f=fake_adapter()
    b=tmp_path/"bundle";b.mkdir()
    (b/"compose.yaml").write_bytes(source.COMPOSE)
    f.extra=(field,value)
    with pytest.raises(generic.ComponentReleaseDenied,match="PMV4_E_CANARY_"):
        h._compose(b,manifest(),operation=None)
    assert len(f.cmds)==1
    assert "config" in f.cmds[0][0]


def test_untrusted_source_cannot_instantiate_production_callback():
    with pytest.raises(generic.ComponentReleaseDenied,match="ROOT_SOURCE_NOT_INSTALLED"):
        adapter.PinnedCanaryHost(production=True)


def test_observed_canary_requires_pinned_image_and_private_network():
    h,f=fake_adapter()
    assert h.observe(contract.CANARY_PROJECT) is None
    f.container=True
    assert h.observe(contract.CANARY_PROJECT)==CAN
    assert any(cmd[0][1]=="inspect" for cmd in f.cmds)


@pytest.mark.parametrize("group,key,value",[
    ("HostConfig","Memory",2*1024**3),
    ("HostConfig","Privileged",True),
    ("HostConfig","ReadonlyRootfs",False),
    ("NetworkSettings","Networks",{"jason-core":{}}),
    ("Config","User","root"),
    ("State","Running",False),
])
def test_corrupted_effective_isolation_fails_readback(group,key,value):
    h,f=fake_adapter();f.container=True
    f.corrupt=(group,key,value)
    with pytest.raises(generic.ComponentReleaseDenied,match="ISOLATED_CONTAINER_NOT_ACCEPTED"):
        h.observe(contract.CANARY_PROJECT)


def test_existing_core_and_financial_adapter_hashes_are_unchanged():
    from hashlib import sha256
    main=Path(__file__).resolve().parents[2]
    assert sha256((main/"tools/independent_component_release.py").read_bytes()).hexdigest()==(
        "1e6f981344f6bfb87977f2d3f4c5e76875447efd78aba03a8968ba94240bd4c7")
    assert sha256((main/"tools/independent_component_host_adapter.py").read_bytes()).hexdigest()==(
        "36f667fd53c2410a902772d3fae7cec7b08f89f99d71f71009c5a8f8029dedce")


def test_no_network_or_extra_peers_may_be_treated_as_providerfree(monkeypatch):
    h,f=fake_adapter();f.container=True
    original=f._run
    def foreign_network(args,**kwargs):
        if args[1:3]==["network","inspect"]:
            return json.dumps([{
                "Name":contract.NETWORK,
                "Internal":False,"Driver":"bridge","Attachable":False,
                "Containers":{"synthetic-container":{},"foreign-container":{}},
            }])
        return original(args,**kwargs)
    f._run=foreign_network
    with pytest.raises(generic.ComponentReleaseDenied,match="PRIVATE_NETWORK_EGRESS_OR_PEER"):
        h.observe(contract.CANARY_PROJECT)


def test_unreviewed_effective_docker_security_cannot_pass(monkeypatch):
    h,f=fake_adapter();f.container=True
    f.corrupt=("HostConfig","SecurityOpt",[])
    with pytest.raises(generic.ComponentReleaseDenied,match="EFFECTIVE_DOCKER_SECURITY"):
        h.observe(contract.CANARY_PROJECT)


def test_providerfree_image_has_pinned_older_source_but_exact_new_manifest():
    h,f=fake_adapter()
    assert h.source_and_ci(CAN) is True
    assert h.image(contract.IMAGE,CAN) is True
    assert h.image(contract.IMAGE,"not-a-source") is False
    assert h.image("sha256:"+"0"*64,CAN) is False
