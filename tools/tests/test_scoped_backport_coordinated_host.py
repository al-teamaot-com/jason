"""Fail-closed native port and interrupted-transaction behavior, no live I/O."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json
import subprocess
import pytest

from tools import scoped_backport_coordinated_host as native
from tools import scoped_backport_coordinated_root as entry
from tools import scoped_backport_coordinated as co
from tools.scoped_backport_release import ScopedBackportDenied, digest
from tools.tests.test_scoped_backport_coordinated import manifest, profile


def container(name, image, revision, cid, running=True):
    return {"Name":"/"+name, "Image":image, "Id":cid,
            "Config":{"Labels":{"org.opencontainers.image.revision":revision,
                                "com.teamaot.jason.source_revision":revision},
                      "Env":["JASON_SOURCE_REVISION="+revision,"EXAMPLE=unchanged"],
                      "User":"1000:1000"},
            "HostConfig":{"NetworkMode":"jason-core","ReadonlyRootfs":True},
            "State":{"Running":running,"Status":"running" if running else "exited",
                     "StartedAt":"2026-01-01T00:00:00Z","Health":{"Status":"healthy"}},
            "Mounts":[],"NetworkSettings":{"Networks":{"jason-core":{}}}}


def test_mutable_checkout_cannot_install_or_dispatch():
    with pytest.raises(ScopedBackportDenied, match="IMMUTABLE_ROOT_INSTALL_REQUIRED"):
        native.verify_installed_policy({})
    with pytest.raises(ScopedBackportDenied, match="INSTALLED_ROOT_ENTRY_REQUIRED"):
        entry.load_installed()


def test_fingerprint_checks_config_but_not_revision():
    item=container("jason-runtime","a","b","c")
    other=deepcopy(item)
    other["Config"]["Env"][0]="JASON_SOURCE_REVISION=d"
    assert native.config_fingerprint(item)==native.config_fingerprint(other)
    other["Config"]["Env"][1]="EXAMPLE=changed"
    assert native.config_fingerprint(item)!=native.config_fingerprint(other)
    other["Config"]["Env"].append("EXAMPLE=duplicate")
    with pytest.raises(ScopedBackportDenied,match="ENVIRONMENT_AMBIGUOUS"):
        native.config_fingerprint(other)


@pytest.mark.parametrize("foreign",["image","id","source"])
def test_original_identity_requires_all_three(foreign):
    m=manifest()
    t=m["targets"][0]
    item=container(t["name"],t["rollback_image"],t["rollback_revision"],t["rollback_container_id"])
    assert native.exact_original(item,t)
    if foreign=="image":
        item["Image"]="foreign"
    elif foreign=="id":
        item["Id"]="foreign"
    else:
        item["Config"]["Labels"]={"org.opencontainers.image.revision":"foreign"}
    assert not native.exact_original(item,t)


def host_fixture(monkeypatch,m):
    h=native.CoordinatedHost()
    h.active_offer=m
    monkeypatch.setattr(h,"_require_root_trust",lambda:None)
    monkeypatch.setattr(h,"_locked",lambda:None)
    return h


def test_native_helper_has_no_unreviewed_arguments(monkeypatch):
    m=manifest()
    h=host_fixture(monkeypatch,m)
    for t in m["targets"]:
        argv=h._args(m,t)
        assert argv[argv.index("--live")+1]==t["name"]
        assert argv[argv.index("--image")+1]==t["candidate_image"]
        assert "--set-env" not in argv and "--add-readonly-bind" not in argv
        assert argv[-1]==("node" if t["name"]=="jason-teams-gateway" else "python")


@pytest.mark.parametrize("foreign",[False,True])
def test_rollback_interrupted_after_rename(monkeypatch,foreign):
    m=manifest()
    h=host_fixture(monkeypatch,m)
    t=m["targets"][2]
    name=t["name"]
    retained=h._rollback_name(name,m)
    item=container(retained,t["rollback_image"],t["rollback_revision"],
                   "foreign" if foreign else t["rollback_container_id"],False)
    monkeypatch.setattr(native,"inspect_container",lambda n:item if n==retained else None)
    commands=[]
    monkeypatch.setattr(native,"run",lambda *args,**kwargs:commands.append(args))
    if foreign:
        with pytest.raises(ScopedBackportDenied,match="ROLLBACK_ORIGINAL_NOT_EXACT"):
            h.restore_exact_target(m,t)
        assert commands==[]
    else:
        h.restore_exact_target(m,t)
        assert commands==[("docker","rename",retained,name),("docker","start",name)]


def test_foreign_live_container_never_deleted(monkeypatch):
    m=manifest()
    h=host_fixture(monkeypatch,m)
    t=m["targets"][0]
    name=t["name"]
    retained=h._rollback_name(name,m)
    original=container(retained,t["rollback_image"],t["rollback_revision"],t["rollback_container_id"],False)
    foreign=container(name,"foreign",t["rollback_revision"],"foreign")
    monkeypatch.setattr(native,"inspect_container",lambda n:original if n==retained else foreign)
    commands=[]
    monkeypatch.setattr(native,"run",lambda *a,**kw:commands.append(a))
    with pytest.raises(ScopedBackportDenied,match="FOREIGN_CONTAINER"):
        h.restore_exact_target(m,t)
    assert commands==[]


def test_frozen_transaction_preserves_marker(monkeypatch):
    m=manifest()
    h=host_fixture(monkeypatch,m)
    h.freeze_before={"raw":b"immutable"}
    monkeypatch.setattr(h,"_frozen",lambda m:h.freeze_before)
    monkeypatch.setattr(h,"consumed_approvals",lambda:frozenset({"a"}))
    statuses=[]
    monkeypatch.setattr(h,"_journal_update",lambda m,status,**kw:statuses.append(status))
    with h.frozen_transaction(m,{"approval_id":"a"}):
        assert h.freeze_before=={"raw":b"immutable"}
    assert statuses==["exact_signed_scope_under_active_freeze","freeze_preserved_pending_verify"]
    with pytest.raises(ScopedBackportDenied,match="NOT_AUTHORIZED"):
        with h.frozen_transaction(m,{"approval_id":"b"}):
            pytest.fail("unconsumed approval reached mutation")


def test_root_promotion_requires_exact_native_stage(monkeypatch):
    m=manifest()
    monkeypatch.setattr(entry,"root_json",lambda p:{"status":"source_only"})
    with pytest.raises(ScopedBackportDenied,match="NATIVE_ELIGIBILITY_REQUIRED"):
        entry.promote(None,m,profile(m))


def test_native_stage_never_issues_approval_or_mutates(monkeypatch,tmp_path):
    m=manifest()
    class Fake:
        @contextmanager
        def release_lock(self,m):
            yield
        def freshly_validate_live_scope(self,m): pass
        def ensure_breaker_closed_and_workers_quiescent(self): pass
        def deny_unresolved_attempt(self,m): pass
    monkeypatch.setattr(entry,"PRIVATE",tmp_path)
    records=[]
    monkeypatch.setattr(entry,"atomic_root_json",lambda p,record:records.append(record))
    r=entry.stage(Fake(),m)
    assert r["status"]=="native_coordinated_eligible_not_approved"
    assert r["owner_approval_recorded"] is False and r["production_mutations"] is False
    assert records==[r]


def test_crash_recovery_reverse_order_never_promotes(monkeypatch):
    m=manifest()
    h=host_fixture(monkeypatch,m)
    journal={"manifest_sha256":digest(m),"scope_sha256":m["scope_sha256"],
             "mutation_attempted":True,"approval_id":"a","protected_before":{}}
    @contextmanager
    def lock(m): yield
    monkeypatch.setattr(h,"release_lock",lock)
    monkeypatch.setattr(h,"_journal",lambda m:journal)
    monkeypatch.setattr(h,"consumed_approvals",lambda:{"a"})
    events=[]
    monkeypatch.setattr(h,"open_breaker",lambda reason:events.append("breaker"))
    monkeypatch.setattr(h,"restore_exact_target",lambda m,t:events.append(t["name"]))
    monkeypatch.setattr(h,"verify_rollback",lambda m:events.append("rollback"))
    monkeypatch.setattr(h,"clear_component_readback",lambda m:events.append("readback"))
    monkeypatch.setattr(h,"verify_protected_unchanged",lambda p:events.append("peers"))
    monkeypatch.setattr(h,"verify_freeze_restored",lambda m:events.append("freeze"))
    monkeypatch.setattr(h,"record_outcome",lambda m,outcome:events.append(outcome))
    assert h.recover(m)["status"]=="interrupted_rollback_verified_breaker_open"
    assert events==["breaker",*reversed(co.TARGET_ORDER),"rollback","readback","peers","freeze","rollback_verified"]


@pytest.mark.parametrize("recorded",["different",None])
def test_candidate_image_label_alone_never_authorizes_removal(monkeypatch,recorded):
    m=manifest()
    h=host_fixture(monkeypatch,m)
    t=m["targets"][0]
    name=t["name"]
    retained=h._rollback_name(name,m)
    original=container(retained,t["rollback_image"],t["rollback_revision"],t["rollback_container_id"],False)
    candidate=container(name,t["candidate_image"],m["candidate_sha"],"candidate")
    candidate["Config"]["Env"][1]="EXAMPLE=foreign"
    monkeypatch.setattr(native,"inspect_container",lambda n:original if n==retained else candidate)
    monkeypatch.setattr(h,"_journal",lambda m:{
        "candidate_ids":{name:recorded},"original_configs":{name:native.config_fingerprint(original)}})
    commands=[]
    monkeypatch.setattr(native,"run",lambda *a,**kw:commands.append(a))
    with pytest.raises(ScopedBackportDenied,match="REPLACEMENT_ID_DRIFT|INTERRUPTED_CANDIDATE_UNVERIFIED"):
        h.restore_exact_target(m,t)
    assert commands==[]


def test_normal_native_mode_preserves_policy_and_marker_absence(monkeypatch,tmp_path):
    from tools.tests.test_scoped_backport_coordinated import normal_manifest
    from implementation.kernel.signed_owner_release_v2 import OwnerReleaseProofDenied
    m=normal_manifest(); h=host_fixture(monkeypatch,m)
    marker=tmp_path/"production-deployment-freeze"
    monkeypatch.setattr(native,"FREEZE",marker)
    monkeypatch.setattr(native,"read_retired_release_policy",lambda:m["release_policy_sha256"])
    assert h._frozen(m)=={"release_policy_sha256":m["release_policy_sha256"]}
    with pytest.raises(ScopedBackportDenied,match="LEGACY_SCOPE_AFTER_RETIREMENT"):
        h._frozen(manifest())
    marker.write_text("active")
    with pytest.raises(OwnerReleaseProofDenied,match="MODE_CONFLICT"):h._frozen(m)
    marker.unlink()
    monkeypatch.setattr(native,"read_retired_release_policy",lambda:None)
    with pytest.raises(ScopedBackportDenied,match="NORMAL_POLICY_DRIFT"):h._frozen(m)


def test_normal_native_stage_projects_only_root_private_exact_offer(monkeypatch,tmp_path):
    from tools.tests.test_scoped_backport_coordinated import normal_manifest
    m=normal_manifest()
    class Fake:
        @contextmanager
        def release_lock(self,m): yield
        def freshly_validate_live_scope(self,m): pass
        def ensure_breaker_closed_and_workers_quiescent(self): pass
        def deny_unresolved_attempt(self,m): pass
    monkeypatch.setattr(entry,'PRIVATE',tmp_path)
    records=[];published=[]
    monkeypatch.setattr(entry,'atomic_root_json',lambda p,record:records.append(record))
    monkeypatch.setattr(entry,'publish_normal_eligibility',lambda record:published.append(record))
    result=entry.stage(Fake(),m)
    assert records==published==[result]
    assert result['schema_version']=='3.0'
    assert result['release_policy_sha256']==m['release_policy_sha256']
    assert 'freeze_sha256' not in result
    assert result['owner_approval_recorded'] is False and result['production_mutations'] is False
