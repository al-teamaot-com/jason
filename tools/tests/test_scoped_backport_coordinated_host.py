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


@pytest.mark.parametrize(
    ("transition", "error"),
    [
        ("healthy", None),
        ("unhealthy", "COORDINATED_TARGET_UNHEALTHY"),
        ("starting", "COORDINATED_CANDIDATE_READINESS_TIMEOUT"),
        ("changed_id", "COORDINATED_CANDIDATE_OR_CONFIGURATION_DRIFT"),
        ("restarted", "COORDINATED_CANDIDATE_RESTARTED_DURING_READINESS"),
    ],
)
def test_candidate_readiness_waits_only_for_exact_starting_container(monkeypatch, transition, error):
    m = manifest()
    h = host_fixture(monkeypatch, m)
    target = m["targets"][0]
    name = target["name"]
    revision = m["projections"][target["projection"]]["candidate_sha"]
    starting = container(name, target["candidate_image"], revision, "candidate")
    starting["State"]["Health"]["Status"] = "starting"
    observed = deepcopy(starting)
    if transition == "changed_id":
        observed["Id"] = "foreign"
    elif transition == "restarted":
        observed["State"]["StartedAt"] = "2026-01-01T00:00:01Z"
    else:
        observed["State"]["Health"]["Status"] = transition
    journal = {
        "candidate_ids": {name: "candidate"},
        "original_configs": {name: native.config_fingerprint(starting)},
    }
    monkeypatch.setattr(h, "_journal", lambda _: journal)
    monkeypatch.setattr(native, "required_container", lambda _: observed)
    ticks = iter([0, 0, 60])
    monkeypatch.setattr(native.time, "monotonic", lambda: next(ticks))
    delays = []
    monkeypatch.setattr(native.time, "sleep", delays.append)

    if error:
        with pytest.raises(ScopedBackportDenied, match=error):
            h._wait_candidate_ready(m, target, starting)
    else:
        h._wait_candidate_ready(m, target, starting)
    assert delays == [2]


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


def test_existing_scheduler_never_selects_or_retries_a_release(monkeypatch, tmp_path):
    monkeypatch.setattr(entry,"read_normal_deployment_freeze",lambda:False)
    from tools.tests.test_scoped_backport_coordinated import normal_manifest, normal_profile
    m=normal_manifest(); p=normal_profile(m)
    journal=tmp_path/"journal.json"
    proof_dir=tmp_path/"owner-approvals"; proof_dir.mkdir()
    proof=proof_dir/(m["release_id"]+".json")
    class Host:
        def _journal_path(self, m): return journal
    events=[]
    monkeypatch.setattr(entry,"AUTH",tmp_path)
    monkeypatch.setattr(entry,"promote",lambda host,m,p: events.append(m["release_id"]) or {"status":"exact_native_call"})
    host=Host()
    assert entry.scheduled_approved(host,m,p)["status"]=="exact_owner_decision_not_present"
    assert events==[]
    proof.touch()
    assert entry.scheduled_approved(host,m,p)["status"]=="exact_native_call"
    assert events==[m["release_id"]]
    journal.write_text("{}")
    monkeypatch.setattr(entry,"root_json",lambda path:{"manifest_sha256":digest(m),"scope_sha256":m["scope_sha256"],"outcome":"recovery_required"})
    assert entry.scheduled_approved(host,m,p)["status"]=="interrupted_attempt_recovery_only"
    monkeypatch.setattr(entry,"root_json",lambda path:{"manifest_sha256":digest(m),"scope_sha256":m["scope_sha256"],"outcome":"production_components_verified"})
    assert entry.scheduled_approved(host,m,p)["status"]=="resolved_prior_attempt_no_action"
    monkeypatch.setattr(entry,"root_json",lambda path:{"manifest_sha256":"bad","scope_sha256":m["scope_sha256"]})
    with pytest.raises(ScopedBackportDenied,match="SCHEDULED_JOURNAL_SCOPE"):
        entry.scheduled_approved(host,m,p)
    assert entry.scheduled_approved(host,manifest(),profile(manifest()))["status"]=="legacy_offer_not_scheduled"
    assert events==[m["release_id"]]


def test_effective_scheduler_binds_existing_units_and_narrow_write_scope(monkeypatch):
    import types
    entry_path=str(native.FILES["dispatch"])
    def show(*args, **kwargs):
        unit=args[2]
        if unit.endswith("requests.service"):
            field="normal_request_dispatch"; worker="scoped_backport_native_root.py"; action="promote-approved"; limit="1h"
        elif unit.endswith("recovery.service"):
            field="normal_recovery_dispatch"; worker="scoped_backport_native_recovery.py"; action="recover-scheduled"; limit="30min"
        else:
            return types.SimpleNamespace(stdout=("DropInPaths="+str(native.FILES["normal_approval_watch"])+"\nPaths=/var/lib/jason/authority/scoped-backport-release/requests (PathChanged)\nPaths=/var/lib/jason/authority/scoped-backport-release/owner-approvals (PathChanged)\n").encode())
        raw=(f"DropInPaths={native.FILES[field]}\nExecStart=/usr/local/lib/jason/scoped-backport/tools/{worker}\n"
             f"ExecStartPost=/usr/bin/python3 -I -B {entry_path} {action}\n"
             f"ReadWritePaths=/var/lib/jason-scoped-backport {native.READBACK.parent}\nTimeoutStartUSec={limit}\n")
        return types.SimpleNamespace(stdout=raw.encode())
    monkeypatch.setattr(native,"run",show)
    monkeypatch.setattr(native,"trusted_directory",lambda _:None)
    native.verify_effective_schedule()
    def widened(*args, **kwargs):
        result=show(*args,**kwargs)
        result.stdout=result.stdout.replace(b"ReadWritePaths=",b"ReadWritePaths=/etc/jason-owner-release ")
        return result
    monkeypatch.setattr(native,"run",widened)
    with pytest.raises(ScopedBackportDenied,match="EFFECTIVE_SCHEDULE_DRIFT"):
        native.verify_effective_schedule()
    # Reject missing, extra, duplicated or differently typed watches.
    request = b"Paths=/var/lib/jason/authority/scoped-backport-release/requests (PathChanged)\n"
    approval = b"Paths=/var/lib/jason/authority/scoped-backport-release/owner-approvals (PathChanged)\n"
    for wrong in (b"", request, approval+approval, approval.replace(b"PathChanged",b"PathExists"),
                  approval+b"Paths=/tmp/fixture-foreign (PathChanged)\n"):
        def altered(*args, **kwargs):
            result = show(*args, **kwargs)
            result.stdout = result.stdout.replace(approval,wrong)
            return result
        monkeypatch.setattr(native,"run",altered)
        with pytest.raises(ScopedBackportDenied,match="EFFECTIVE_APPROVAL_WATCH_DRIFT"):
            native.verify_effective_schedule()
    def reversed_order(*args, **kwargs):
        result = show(*args, **kwargs)
        result.stdout = result.stdout.replace(request+approval,approval+request)
        return result
    monkeypatch.setattr(native,"run",reversed_order)
    native.verify_effective_schedule()


def test_reusable_root_offer_stage_preserves_prior_evidence(monkeypatch,tmp_path):
    from tools.tests.test_scoped_backport_coordinated import normal_manifest, normal_profile
    m=normal_manifest(); p=normal_profile(m); review="8"*40
    folder=tmp_path/"offers";folder.mkdir()
    view=tmp_path/"projection";view.mkdir()
    auth=tmp_path/"auth";(auth/"owner-approvals").mkdir(parents=True)
    journals=tmp_path/"transactions";journals.mkdir()
    monkeypatch.setattr(entry,"PRIVATE",tmp_path)
    monkeypatch.setattr(native,"PRIVATE",tmp_path)
    monkeypatch.setattr(entry,"PUBLIC_VIEW",view)
    monkeypatch.setattr(entry,"AUTH",auth)
    def write(path,row,replace=False):
        assert replace or not path.exists()
        path.write_text(json.dumps(row))
    monkeypatch.setattr(entry,"atomic_root_json",write)
    monkeypatch.setattr(entry,"root_json",lambda path,**kw:json.loads(path.read_text()))
    monkeypatch.setattr(native,"root_json",lambda path,**kw:json.loads(path.read_text()))
    monkeypatch.setattr(entry,"root_directory",lambda p:None)
    monkeypatch.setattr(native,"root_directory",lambda p:None)
    monkeypatch.setattr(entry,"publish_normal_eligibility",lambda row:write(view/("eligible-"+row["release_id"]+".json"),row,replace=True))
    monkeypatch.setattr(entry,"exact_file",lambda path,**kw:path.read_bytes())
    events=[]
    class Host:
        def bind_for_stage(self,m,p,review):events.append("bind")
        @contextmanager
        def release_lock(self,m):yield
        def freshly_validate_live_scope(self,m):events.append("review")
        def ensure_breaker_closed_and_workers_quiescent(self):pass
        def deny_unresolved_attempt(self,m):pass
        def _journal_path(self,m):return journals/(m["release_id"]+".json")
    h=Host()
    first=entry.persist_reviewed_offer(h,m,p,review)
    original=folder/(m["release_id"]+".json")
    before=original.read_bytes()
    assert native.active_staged_offer()["eligibility"]==first
    assert entry.persist_reviewed_offer(h,m,p,review)==first
    second=deepcopy(m)
    candidate="7"*40
    anchor=second["targets"][0]["projection"]
    second["projections"][anchor]["candidate_sha"]=candidate
    second["candidate_sha"]=candidate;second["release_id"]="release-"+candidate[:16]
    second["scope_sha256"]=digest(co._scope(second))
    second_profile=normal_profile(second)
    pending=auth/"owner-approvals"/(m["release_id"]+".json")
    pending.touch()
    with pytest.raises(ScopedBackportDenied,match="PRIOR_SIGNED_OFFER_PENDING"):
        entry.persist_reviewed_offer(h,second,second_profile,review)
    pending.unlink()
    result=entry.persist_reviewed_offer(h,second,second_profile,review)
    assert native.active_staged_offer()["eligibility"]==result
    assert original.read_bytes()==before
    assert not (view/("eligible-"+m["release_id"]+".json")).exists()
    assert (view/("eligible-"+second["release_id"]+".json")).exists()


def test_stale_normal_offer_cannot_mutate_after_active_pointer_switch(monkeypatch):
    from tools.tests.test_scoped_backport_coordinated import normal_manifest, normal_profile
    m=normal_manifest();h=host_fixture(monkeypatch,m)
    h.policy={"schema_version":"3.0"};h.active_profile=normal_profile(m);h.active_review_sha="8"*40
    monkeypatch.setattr(native,"active_staged_offer",lambda:None)
    with pytest.raises(ScopedBackportDenied,match="ACTIVE_OFFER_CHANGED_UNDER_LOCK"):
        h._require_current_staged_scope()
    monkeypatch.setattr(native,"active_staged_offer",lambda:{"manifest":m,"profile":h.active_profile,"review_source_sha":h.active_review_sha})
    h._require_current_staged_scope()


def test_reader_migration_checks_effective_manager_artifact_and_root_paths(monkeypatch, tmp_path):
    from hashlib import sha256
    watchdog = tmp_path / "attested" / "jason_self_heal_watchdog.py"
    worker = tmp_path / "attested" / "owner_approved_development_worker.py"
    guard = tmp_path / "native" / "pmv4_host_release_guard.py"
    transition = tmp_path / "native" / "release_control_transition_worker.py"
    for p in (watchdog, worker, guard, transition):
        p.parent.mkdir(exist_ok=True)
    watchdog.write_bytes(b"watchdog reviewed")
    guard.write_bytes(b"guard reviewed")
    transition.write_bytes(b"transition reviewed")
    def h(p): return sha256(p.read_bytes()).hexdigest()
    worker.write_text(f"NATIVE_HEALTH_GUARD = Path({str(guard)!r})\nNATIVE_HEALTH_GUARD_SHA256 = {h(guard)!r}\n")
    monkeypatch.setitem(native.FILES, "host_guard", guard)
    monkeypatch.setattr(native, "TRANSITION_SUCCESSOR", transition)
    monkeypatch.setattr(native, "trusted_bytes", lambda p, **kw: p.read_bytes())
    monkeypatch.setattr(native, "verified_manager_artifacts", lambda: {
        watchdog.name: (watchdog, h(watchdog)), worker.name: (worker, h(worker))})
    commands = []
    monkeypatch.setattr(native, "effective_reader_command", lambda *a, **kw: commands.append((a, kw)))
    scope = {"source_sha": "a"*40}
    record = {"schema_version": "2.0", "source_sha": scope["source_sha"],
              "native_readback_verified": True, "original_authority_preserved": True,
              "installed_readers": [{"path": str(p), "sha256": h(p)}
                                    for p in (watchdog, guard, transition)]}
    native.verify_reader_migration(record, scope)
    assert len(commands) == 3
    assert {args[0][0] for args in commands} == {
        "jason-self-heal-watchdog.service",
        "jason-release-control-transition.service",
        "jason-pmv4-component-transition.service",
    }
    foreign = tmp_path / "foreign" / watchdog.name
    foreign.parent.mkdir()
    foreign.write_bytes(watchdog.read_bytes())
    changed = deepcopy(record)
    changed["installed_readers"][0]["path"] = str(foreign)
    with pytest.raises(ScopedBackportDenied, match="READER_INSTALLED_DRIFT"):
        native.verify_reader_migration(changed, scope)
    changed = deepcopy(record)
    changed["installed_readers"].append(changed["installed_readers"][0])
    with pytest.raises(ScopedBackportDenied, match="READER_INSTALLED_DRIFT"):
        native.verify_reader_migration(changed, scope)
    worker.write_text("NATIVE_HEALTH_GUARD = Path('/foreign.py')\nNATIVE_HEALTH_GUARD_SHA256 = 'bad'\n")
    with pytest.raises(ScopedBackportDenied, match="DEVELOPMENT_GUARD_BINDING"):
        native.verify_reader_migration(record, scope)


def test_effective_reader_command_rejects_other_executable(monkeypatch):
    from types import SimpleNamespace
    argv = ["/usr/bin/python3", "-I", "-B", str(native.TRANSITION_SUCCESSOR)]
    def report(args):
        return SimpleNamespace(stdout=("User=root\nExecStart={ path=/usr/bin/python3 ; argv[]="
                                          +" ".join(args)+" ; ignore_errors=no ; }\n").encode())
    monkeypatch.setattr(native, "run", lambda *a, **kw: report(argv))
    native.effective_reader_command("jason-release-control-transition.service", user="root", argv=argv)
    monkeypatch.setattr(native, "run", lambda *a, **kw: report(argv + ["--foreign"]))
    with pytest.raises(ScopedBackportDenied, match="EFFECTIVE_READER_COMMAND_DRIFT"):
        native.effective_reader_command("jason-release-control-transition.service", user="root", argv=argv)


def test_owner_uat_configuration_is_losslessly_bound_to_exact_container_delta(monkeypatch):
    from datetime import datetime, timezone

    m = {
        "schema_version": "3.0", "release_id": "release-" + "a" * 16,
        "targets": [{"name": name} for name in native.OWNER_UAT_COMPONENTS],
        "projections": {name: {"candidate_sha": digit * 40, "changed_files": [native.OWNER_UAT_SOURCE]}
                        for name, digit in zip(native.OWNER_UAT_COMPONENTS, ("a", "b"))},
    }
    campaign = {
        "schema_version": "1.0", "purpose": "owner_teams_nonexecuting_uat",
        "organization_id": "aot", "recipient": "person-al",
        "capability": "interaction.owner.acceptance.record", "execution_permitted": False,
        "session_id": "CanaryTest", "expires_at": "2026-11-28T23:00:00+00:00",
    }
    monkeypatch.setattr(native.co, "_git", lambda *_: json.dumps(campaign).encode())
    now = datetime(2026, 11, 27, 20, tzinfo=timezone.utc)
    env = native.owner_uat_environment(Path("/unused"), m, now=now)
    assert env["jason-runtime"]["JASON_OWNER_UAT_WORKER_ENABLED"] == "true"
    assert env["jason-mcp-pilot"]["JASON_OWNER_UAT_WORKER_ENABLED"] == "false"
    assert all(not any("PROCUREMENT" in key for key in values) for values in env.values())

    original = container("jason-runtime", "a", "b", "c")
    original["Config"]["Env"].append("JASON_OWNER_UAT_MODE=off")
    replacement = deepcopy(original)
    values = dict(x.split("=", 1) for x in replacement["Config"]["Env"])
    values.update(env["jason-runtime"])
    replacement["Config"]["Env"] = [k + "=" + v for k, v in values.items()]
    k, src, dest, rw = native.OWNER_UAT_BIND
    replacement["Mounts"].append({"Type": k, "Source": src, "Destination": dest, "RW": rw})
    candidate = native.config_fingerprint(
        original, environment=env["jason-runtime"], extra_mount=native.OWNER_UAT_BIND)
    assert candidate == native.config_fingerprint(replacement)
    assert candidate != native.config_fingerprint(original)
    replacement["Mounts"][0]["RW"] = True
    assert candidate != native.config_fingerprint(replacement)
    campaign["execution_permitted"] = True
    with pytest.raises(ScopedBackportDenied, match="OWNER_UAT_CONFIGURATION"):
        native.owner_uat_environment(Path("/unused"), m, now=now)
    with pytest.raises(ScopedBackportDenied, match="OWNER_UAT_TARGET_SCOPE"):
        native.owner_uat_environment(Path("/unused"), dict(m, targets=m["targets"][:1]), now=now)
