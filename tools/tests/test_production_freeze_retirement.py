"""Unprivileged approval/identity tests for the proposed migration.

All records are synthetic. A fake adapter must deny before invoking any
native operations. No actual Docker, systemd, release or provider I/O.
"""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools import production_freeze_retirement as r


def fixture_plan():
    return {
        "action": "REPAIR-EXACT-PMV4-ENGINEERING-PIPELINE-CONTRACT",
        "policy": {"candidate_sha": "a"*40, "rollback_sha": r.BASE},
        "installation_targets": ["/fixture/manager.py"],
        "normal_retirement": {
            "action": r.ACTION,
            "candidate_sha": "a"*40,
            "provider_writes": False,
            "standing_authority": False,
            "rollback_authorized": True,
            "configuration_after": {"schema_version": "1.0", "production_freeze": False},
            "installation_targets": ["/fixture/policy.json"],
        },
    }


def test_parent_approval_binds_all_installation_targets():
    plan = fixture_plan()
    scope = r.owner_scope(plan)
    assert scope["manager_preparation_and_retirement"] == plan
    assert set(scope["installation_targets"]) == {
        "/fixture/manager.py", "/fixture/policy.json"}
    changed = deepcopy(plan)
    changed["normal_retirement"]["installation_targets"].append("/fixture/other")
    assert r.digest(r.canonical(r.owner_scope(changed))) != r.digest(r.canonical(scope))


@pytest.mark.parametrize("key,value", [
    ("action", "FOREIGN_ACTION"),
    ("candidate_sha", "b"*40),
    ("provider_writes", True),
    ("standing_authority", True),
    ("rollback_authorized", False),
    ("configuration_after", {"schema_version": "1.0", "production_freeze": "false"}),
])
def test_parent_scope_rejects_authority_expansion(key, value):
    plan = fixture_plan()
    plan["normal_retirement"][key] = value
    with pytest.raises(PermissionError, match="EXACT_PARENT_SCOPE"):
        r.owner_scope(plan)


def fake_adapter(tmp_path, plan, approval=None, acceptance=None):
    rows = {
        "approval.json": r.canonical(approval or {}),
        "scheduled-acceptance.json": r.canonical(acceptance or {}),
    }
    def read(path, *args):
        assert path.parent == tmp_path
        return rows[path.name]
    return SimpleNamespace(
        load_record=lambda: "1"*64,
        plan=plan, directory=tmp_path,
        n={"read": Mock(side_effect=read),
           "locks": Mock(side_effect=AssertionError("native operation attempted")),
           "write": Mock(side_effect=AssertionError("unexpected write"))},
        command=Mock(side_effect=AssertionError("unexpected command")),
        pause=Mock(side_effect=AssertionError("unexpected pause")),
        systemctl=Mock(side_effect=AssertionError("unexpected service change")),
    )


def assert_no_operations(adapter):
    adapter.n["locks"].assert_not_called()
    adapter.n["write"].assert_not_called()
    adapter.command.assert_not_called()
    adapter.pause.assert_not_called()
    adapter.systemctl.assert_not_called()


@pytest.mark.parametrize("recover", [False, True])
def test_manager_only_approval_cannot_reach_retirement(tmp_path, recover):
    p = fixture_plan()
    p.pop("normal_retirement")
    a = fake_adapter(tmp_path, p)
    with pytest.raises(PermissionError, match="PARENT_APPROVAL_REQUIRED"):
        r.activate(a, {}, recover=recover)
    assert_no_operations(a)


@pytest.mark.parametrize("change", ["wrong_action", "wrong_digest", "missing"])
def test_unbound_approval_is_denied_without_native_operations(tmp_path, change):
    p = fixture_plan()
    approval = {"owner_scope_sha256": r.digest(r.canonical(r.owner_scope(p))),
                "owner_action": r.ACTION}
    if change == "wrong_action":
        approval["owner_action"] = "OTHER"
    elif change == "wrong_digest":
        approval["owner_scope_sha256"] = "2"*64
    else:
        approval = {}
    a = fake_adapter(tmp_path, p, approval)
    with pytest.raises(PermissionError, match="PARENT_APPROVAL_BINDING"):
        r.activate(a, {})
    assert_no_operations(a)


@pytest.mark.parametrize("change", ["wrong_scope", "not_accepted", "one_cycle"])
def test_preparation_must_have_exact_two_cycle_acceptance(tmp_path, change):
    p = fixture_plan()
    approval = {"owner_scope_sha256": r.digest(r.canonical(r.owner_scope(p))),
                "owner_action": r.ACTION}
    acceptance = {"scope_sha256": "1"*64,
                  "status": "scheduled_engineering_acceptance_verified",
                  "evidence": {"two_distinct_scheduled_cycles_verified": True}}
    if change == "wrong_scope":
        acceptance["scope_sha256"] = "2"*64
    elif change == "not_accepted":
        acceptance["status"] = "failed"
    else:
        acceptance["evidence"]["two_distinct_scheduled_cycles_verified"] = False
    a = fake_adapter(tmp_path, p, approval, acceptance)
    with pytest.raises(PermissionError, match="PREPARATION_NOT_ACCEPTED"):
        r.activate(a, {})
    assert_no_operations(a)


def test_peer_configuration_fingerprint_checks_readonly_policy_projection():
    row = {"Config": {"Env": ["FIXTURE=1", "JASON_SOURCE_REVISION=old"], "User": "1000:1000"},
           "HostConfig": {"ReadonlyRootfs": True}, "Mounts": [],
           "NetworkSettings": {"Networks": {"fixture": {}}}}
    changed = deepcopy(row)
    changed["Config"]["Env"][1] = "JASON_SOURCE_REVISION=new"
    changed["Mounts"].append({"Type": "bind", "Source": str(r.PUB),
                              "Destination": str(r.PUB), "RW": False})
    assert r.config_fingerprint(row) == r.config_fingerprint(changed, remove_projection=True)
    changed["Mounts"][0]["RW"] = True
    with pytest.raises(PermissionError, match="MCP_PROJECTION_MOUNT"):
        r.config_fingerprint(changed, remove_projection=True)


def test_fixed_deployment_argument_scope_has_no_provider_or_environment_changes():
    args = r.deploy_args()
    assert args[args.index("--live")+1] == r.MCP
    assert args[args.index("--image")+1] == r.IMAGE
    assert args[args.index("--rollback")+1] == r.ROLLBACK
    assert args[args.index("--add-readonly-bind")+1] == str(r.PUB)+":"+str(r.PUB)
    assert "--set-env" not in args
    assert "--promote-image-tag" not in args
    assert "--enforce-no-paid-ai" in args


@pytest.fixture
def transaction_fixture(tmp_path, monkeypatch, request):
    """Run existing orchestration against virtual files and a fake container engine."""
    from contextlib import contextmanager
    from pathlib import Path
    from tools import pmv4_e_engineering_manager_install as manager
    import os
    import stat
    real_files = bool(getattr(request, "param", False))
    if real_files:
        if os.geteuid() != 0 or os.environ.get("JASON_DISPOSABLE_NATIVE_FIXTURE") != "1":
            pytest.skip("requires an explicitly isolated root filesystem fixture")
        assert tmp_path.resolve().is_relative_to(Path("/tmp"))
        from tools import pmv4_e_dispatch_install as dispatch
        from tools import parallel_development_install as parallel

    root = tmp_path / "sandbox"
    root.mkdir()
    install = root / "install"
    etc = root / "etc"
    state = root / "state"
    private = root / "private"
    journal = root / "journal"
    for p in (install, etc, state, journal):
        p.mkdir()
    (install / "tools").mkdir()
    pub = etc / "public"
    paths = {
        "INSTALL": install, "ETC": etc, "STATE": state, "PRIVATE": private,
        "PUB": pub, "CONFIG": pub / "deployment.json",
        "RETIRED": pub / "retired.json", "READBACK": etc / "readback.json",
        "MIGRATION": etc / "migration.json", "POLICY": etc / "policy.json",
        "FREEZE": state / "freeze", "BACKUP": state / "backup",
        "HOLD": state / "hold", "UNITS": root / "units",
    }
    for name, path in paths.items():
        monkeypatch.setattr(r, name, path)
    source_target = install / "tools/release_control_transition_worker.py"
    source_name = "fixture/transition.py"
    monkeypatch.setattr(r, "SOURCES", {source_target: source_name})
    monkeypatch.setattr(r, "TRANSITIONS", {})
    monkeypatch.setattr(r, "DYNAMIC", tuple(paths[n] for n in
        ("CONFIG", "RETIRED", "READBACK", "MIGRATION", "POLICY")))
    dirs = {pub: 0o755, private: 0o700, private/"source.git": 0o700}
    monkeypatch.setattr(r, "DIRS", dirs)
    image = manager.image
    pause_path = state / "pause"
    original_freeze = image(b"fixture original freeze", 1000, 0o600)
    hold = image(b"fixture incident hold", 1000, 0o664)
    monkeypatch.setattr(r, "FREEZE_HASH", r.digest(original_freeze[0]))
    monkeypatch.setattr(r, "HOLD_HASH", r.digest(hold[0]))
    guard = install / "tools/pmv4_host_release_guard.py"
    files = {r.FREEZE: original_freeze, r.BACKUP: original_freeze,
             r.HOLD: hold, guard: image(b"fixture guard",0,0o444)}
    initial_files = dict(files)
    if real_files:
        for path, (raw, uid, gid, mode) in initial_files.items():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fchown(stream.fileno(), uid, gid)
                os.fchmod(stream.fileno(), mode)
                os.fsync(stream.fileno())
            dispatch.sync_dir(path.parent)

    rows = {}
    for i, name in enumerate(r.PEERS):
        rows[name] = {
            "Name": "/"+name, "Id": str(i+1)*64, "Image": "sha256:"+str(i+1)*64,
            "State": {"Running": True, "StartedAt": "fixture",
                      "Health": {"Status": "healthy"}},
            "Config": {"Labels": {"com.teamaot.jason.source_revision": r.BASE},
                       "Env": ["FIXTURE=1","JASON_SOURCE_REVISION="+r.BASE],
                       "User":"1000:1000"},
            "HostConfig": {"ReadonlyRootfs": True}, "Mounts": [],
            "NetworkSettings": {"Networks": {"fixture": {}}},
        }
    original_rows = deepcopy(rows)
    plan = fixture_plan()
    scope = plan["normal_retirement"]
    scope.update(create_directories={str(p):oct(v) for p,v in dirs.items()},
                 peers_before=r.peer_state(rows))
    plan["protected_health"] = {"fixture":"healthy"}
    approval = {"owner_scope_sha256": r.digest(r.canonical(r.owner_scope(plan))),
                "owner_action": r.ACTION}
    acceptance = {"scope_sha256": "1"*64,
                  "status":"scheduled_engineering_acceptance_verified",
                  "evidence":{"two_distinct_scheduled_cycles_verified":True}}
    if real_files:
        dispatch.write(journal/"approval.json",r.canonical(approval),0o400)
        dispatch.write(journal/"scheduled-acceptance.json",r.canonical(acceptance),0o400)
    else:
        (journal/"approval.json").write_bytes(r.canonical(approval))
        (journal/"scheduled-acceptance.json").write_bytes(r.canonical(acceptance))
    events = []
    fixture = SimpleNamespace(fail=None, lock=False, files=files, rows=rows,
        initial_files=initial_files, original_rows=original_rows, journal=journal,
        events=events, plan=plan, pause_path=pause_path)

    def event(name):
        events.append(name)
        if fixture.fail == name:
            fixture.fail = None
            raise RuntimeError("injected "+name)

    @contextmanager
    def locks():
        assert not fixture.lock
        fixture.lock = True
        try:
            yield
        finally:
            fixture.lock = False

    def read(path, *args):
        assert path.is_relative_to(root)
        if real_files and path in files:
            st=path.lstat()
            assert (st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode)) == files[path][1:]
            assert path.read_bytes()==files[path][0]
        return files[path][0] if path in files else path.read_bytes()

    def write(path, raw, mode):
        assert path.parent == journal and not path.exists()
        if real_files:
            dispatch.write(path,raw,mode)
        else:
            path.write_bytes(raw)
        event("record:"+path.name)

    def replace(path, before, after, unused=None):
        assert fixture.lock and path.is_relative_to(root)
        assert files.get(path) == before
        if real_files:
            manager.replace_exact(path,before,after,parallel.rename_noreplace)
        if after is None:
            files.pop(path, None)
        else:
            files[path] = after
        event("file:"+path.name)
        if path==r.CONFIG and after is not None and json.loads(after[0])["production_freeze"] is False:
            event("configuration_commit")

    def pause():
        assert fixture.lock
        value=image(b"fixture pause",1000,0o600)
        if real_files:
            replace(pause_path,files.get(pause_path),value)
        else:
            files[pause_path] = value
        event("pause")

    def command(args, timeout):
        # This is a fake backend. It never invokes subprocess or Docker.
        if args[0] == "/usr/bin/git":
            assert fixture.lock
            event("git:"+args[1])
            return b""
        if args == [*r.deploy_args(),"--preflight"]:
            event("preflight")
            return b""
        if args == r.deploy_args():
            old = rows[r.MCP]
            rows[r.ROLLBACK] = deepcopy(old)
            rows[r.ROLLBACK]["Name"] = "/"+r.ROLLBACK
            rows[r.ROLLBACK]["State"]["Running"] = False
            new = deepcopy(old)
            new.update(Id="f"*64,Image=r.IMAGE)
            new["Config"]["Labels"]["com.teamaot.jason.source_revision"] = r.PROJECTION
            new["Config"]["Env"][-1] = "JASON_SOURCE_REVISION="+r.PROJECTION
            new["Mounts"].append({"Type":"bind","Source":str(r.PUB),
                                  "Destination":str(r.PUB),"RW":False})
            rows[r.MCP] = new
            event("deploy")
            return b""
        assert args[0] == "/usr/bin/docker", args
        if args[1] == "inspect":
            names = args[4:] if args[2:4] == ["--type","container"] else args[2:]
            return r.canonical([rows[n] for n in names])
        if args[1] == "exec":
            event("issuer_readback")
            return r.canonical([r.digest(files[r.RETIRED][0]),
                                json.loads(files[r.CONFIG][0])["production_freeze"]])
        assert fixture.lock
        if args[1] == "ps":
            return ("\n".join(rows)+"\n").encode()
        if args[1] == "rm":
            assert args[-1] == r.MCP
            rows.pop(r.MCP)
        elif args[1] == "rename":
            assert args[2:] == [r.ROLLBACK,r.MCP]
            rows[r.MCP] = rows.pop(r.ROLLBACK)
            rows[r.MCP]["Name"] = "/"+r.MCP
        elif args[1] == "start":
            assert args[-1] == r.MCP
            rows[r.MCP]["State"]["Running"] = True
        else:
            raise AssertionError(args)
        event("docker:"+args[1])
        return b""

    def observe(adapter, expression):
        if "verified_manager_artifacts" in expression:
            return {"jason_self_heal_watchdog.py":[str(guard),"a"*64]}
        if "h.FILES.items" in expression:
            return {"fixture":"a"*64}
        if expression == "h.verify_installed_policy()":
            event("policy_readback")
            return {"fixture":True}
        assert expression == "r.verify_live()"
        event("component_readback")
        return json.loads(files[r.READBACK][0])

    def native_revalidation():
        assert not fixture.lock
        event("native_revalidation")

    monkeypatch.setattr(r, "prepare", lambda *args: deepcopy(scope))
    monkeypatch.setattr(r, "check_pending", lambda a: event("pending_check"))
    monkeypatch.setattr(r, "root_observation", observe)

    adapter = SimpleNamespace(candidate="a"*40, directory=journal, plan=plan,
        load_record=lambda:"1"*64, code={source_name:b"fixture reviewed transition"},
        n={"read":read,"write":write,"locks":locks,"sync_dir":lambda p:None},
        p={"read":read,"rename_noreplace":None},
        verify_successor_topology_and_source=lambda **kw:event("manager_readback"),
        protected=lambda:deepcopy(plan["protected_health"]),
        pause=pause, pause_image=image(b"fixture pause",1000,0o600),
        quiesce=lambda names:event("quiesce"), command=command,
        systemctl=lambda args:event("reload"),
        native_revalidation=native_revalidation,
        change=lambda p,b,a:replace(p,b,a) if b!=a else None)
    def snapshot(path):
        value=files.get(path)
        if real_files:
            assert manager.snapshot(path)==value,str(path)
        return value
    ops = {"snapshot":snapshot,"image":image,"replace_exact":replace,
           "encode":manager.encode,"decode":manager.decode,
           "cleanup_staged":manager.cleanup_staged if real_files else lambda *args:None,
           "PAUSE":pause_path,"SERVICES":("fixture",)}
    fixture.adapter,fixture.ops = adapter,ops
    return fixture


def test_isolated_retirement_transaction_preserves_protected_peers(transaction_fixture):
    f = transaction_fixture
    result = r.activate(f.adapter,f.ops)
    assert result["status"] == "global_production_freeze_retired"
    assert json.loads(f.files[r.CONFIG][0])["production_freeze"] is False
    assert r.FREEZE not in f.files and r.BACKUP not in f.files
    assert f.files[r.HOLD] == f.initial_files[r.HOLD]
    assert f.rows[r.ROLLBACK]["Id"] == f.original_rows[r.MCP]["Id"]
    assert f.rows[r.ROLLBACK]["State"]["Running"] is False
    for name in r.PEERS:
        if name != r.MCP:
            assert f.rows[name] == f.original_rows[name]
    assert f.events.index("record:retirement-intent.json") < f.events.index("deploy")
    assert f.events.index("native_revalidation") < f.events.index("record:retirement-ready.json")
    assert (f.journal/"retirement-complete.json").exists()


@pytest.mark.parametrize("fault", ["preflight", "deploy", "native_revalidation", "issuer_readback"])
def test_isolated_retirement_failure_restores_exact_before_state(transaction_fixture,fault):
    f = transaction_fixture
    f.fail = fault
    with pytest.raises(RuntimeError,match="injected "+fault):
        r.activate(f.adapter,f.ops)
    assert f.files == f.initial_files
    assert f.rows == f.original_rows
    assert (f.journal/"retirement-rollback.json").exists()
    assert not (f.journal/"retirement-complete.json").exists()


def test_isolated_recovery_of_interruption_before_native_cutover(transaction_fixture):
    f = transaction_fixture
    f.fail = "pause"
    with pytest.raises(RuntimeError,match="injected pause"):
        r.activate(f.adapter,f.ops)
    assert (f.journal/"retirement-intent.json").exists()
    assert f.rows == f.original_rows
    assert r.activate(f.adapter,f.ops,recover=True)["status"] == "original_freeze_and_mcp_restored"
    assert f.files == f.initial_files
    assert f.rows == f.original_rows


@pytest.mark.parametrize("transaction_fixture", [True], indirect=True)
@pytest.mark.parametrize("fault", [None, "deploy", "native_revalidation", "record:retirement-ready.json", "configuration_commit"])
def test_disposable_native_filesystem_transaction(transaction_fixture, fault):
    """Real before/after image publication and custody; Docker and systemd remain mocked."""
    import stat
    from tools import pmv4_e_engineering_manager_install as manager
    f=transaction_fixture
    f.fail=fault
    if fault is None:
        assert r.activate(f.adapter,f.ops)["status"]=="global_production_freeze_retired"
    else:
        with pytest.raises(RuntimeError,match="injected "+fault):
            r.activate(f.adapter,f.ops)
        if fault=="configuration_commit":
            # A crash after the durable commit must not restore the old freeze.
            assert not (f.journal/"retirement-complete.json").exists()
            recovered=r.activate(f.adapter,f.ops,recover=True)
            assert recovered["status"]=="retirement_commit_recovered"
            assert recovered["live_verification_required"] is True
            assert recovered["receipt"]["status"]=="global_production_freeze_retired"
        else:
            assert f.files==f.initial_files
            assert f.rows==f.original_rows
            assert (f.journal/"retirement-rollback.json").is_file()
    if fault in (None,"configuration_commit"):
        assert json.loads(r.CONFIG.read_bytes())["production_freeze"] is False
        assert not r.FREEZE.exists() and not r.BACKUP.exists()
        assert (f.journal/"retirement-complete.json").is_file()
    else:
        assert manager.snapshot(r.FREEZE)==f.initial_files[r.FREEZE]
        assert manager.snapshot(r.BACKUP)==f.initial_files[r.BACKUP]
        assert not r.CONFIG.exists()
    assert r.HOLD.read_bytes()==f.initial_files[r.HOLD][0]
    for path in f.journal.glob("*.json"):
        st=path.lstat()
        assert st.st_uid==st.st_gid==0 and stat.S_IMODE(st.st_mode)==0o400


def test_concurrent_recovery_is_denied_while_activation_owns_intent(transaction_fixture):
    f=transaction_fixture
    original=f.adapter.native_revalidation
    checked=[]
    def readback():
        with pytest.raises(PermissionError,match="TRANSACTION_ALREADY_ACTIVE"):
            r.activate(f.adapter,f.ops,recover=True)
        checked.append(True)
        original()
    f.adapter.native_revalidation=readback
    assert r.activate(f.adapter,f.ops)["status"]=="global_production_freeze_retired"
    assert checked==[True]
    assert not (f.journal/"retirement-rollback.json").exists()


def test_repeated_activation_returns_historical_receipt_without_native_operations(transaction_fixture):
    f=transaction_fixture
    assert r.activate(f.adapter,f.ops)["status"]=="global_production_freeze_retired"
    before=list(f.events)
    result=r.activate(f.adapter,f.ops)
    assert result["status"]=="retirement_previously_committed"
    assert result["live_verification_required"] is True
    assert result["receipt"]["status"]=="global_production_freeze_retired"
    assert f.events==before
