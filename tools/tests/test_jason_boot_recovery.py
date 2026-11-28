from __future__ import annotations

import importlib.util
from copy import deepcopy
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'tools/jason_boot_recovery.py'
spec=importlib.util.spec_from_file_location('boot_recovery_tested',SCRIPT)
mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod)


def write(path: Path, value: bytes, mode: int, uid: int | None=None, gid: int | None=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(value); path.chmod(mode)
    if uid is not None:
        path.chown(uid, gid if gid is not None else -1)


def test_current_credentials_do_not_refresh(tmp_path):
    pairs=[]
    for provider in ('autotask','it-glue'):
        for name in ('role','secret'):
            src=tmp_path/'src'/provider/name
            dst=tmp_path/'dst'/provider/name
            write(src,(provider+name).encode(),0o600)
            write(dst,(provider+name).encode(),0o400)
            pairs.append((src,dst))
    with (
        patch.object(mod,'BOOTSTRAP_TO_STAGED',tuple(pairs)),
        patch.object(mod,'STAGED_FILES',tuple(dst for _,dst in pairs)),
        patch.object(mod.os,'geteuid',return_value=0),
        patch.object(mod.os,'lstat',side_effect=lambda p: _fake_lstat(Path(p), pairs)),
    ):
        assert mod.staged_credentials_current() is True


def _fake_lstat(path: Path, pairs):
    st=path.stat()
    source={a for a,_ in pairs}
    uid=0 if path in source else 1000
    gid=0 if path in source else 1000
    return SimpleNamespace(st_mode=st.st_mode,st_uid=uid,st_gid=gid,st_size=st.st_size,st_ino=st.st_ino,st_dev=st.st_dev)


def test_mismatch_is_detected_without_printing_values(tmp_path):
    pairs=[]
    for i in range(4):
        src=tmp_path/'src'/str(i); dst=tmp_path/'dst'/str(i)
        write(src,b'authoritative-'+bytes([48+i]),0o600)
        write(dst,b'authoritative-'+bytes([48+i]),0o400)
        pairs.append((src,dst))
    pairs[-1][1].chmod(0o600); pairs[-1][1].write_bytes(b'stale-runtime-value'); pairs[-1][1].chmod(0o400)
    with (
        patch.object(mod,'BOOTSTRAP_TO_STAGED',tuple(pairs)),
        patch.object(mod,'STAGED_FILES',tuple(dst for _,dst in pairs)),
        patch.object(mod.os,'lstat',side_effect=lambda p: _fake_lstat(Path(p), pairs)),
    ):
        assert mod.staged_credentials_current() is False


def test_stage_refresh_requests_replace_and_remount_is_separate(tmp_path):
    stager=tmp_path/'stager.py'; stager.write_text('# stub')
    with (
        patch.object(mod,'STAGER',stager),
        patch.object(mod,'STAGED_FILES',(tmp_path/'existing',)),
        patch.object(Path,'exists',return_value=True),
        patch.object(mod,'staged_credentials_ready',return_value=True),
        patch.object(mod,'staged_credentials_current',side_effect=[False,True]),
        patch.object(mod,'run',return_value=SimpleNamespace(returncode=0)) as run,
    ):
        assert mod.stage_runtime_credentials() is True
    args=run.call_args.args[0]
    assert '--replace-existing' in args
    assert '--stage' in args


def runtime_info(state="running"):
    return {
        "Id": "a" * 64, "Name": "/jason-runtime", "Image": "sha256:" + "b" * 64,
        "Config": {"Labels": {"com.teamaot.jason.source_revision": "c" * 40}},
        "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"}},
        "State": {"Status": state, "Health": {"Status": "healthy"}},
        "Mounts": [
            {"Source": source, "Destination": destination, "Type": "bind", "RW": False}
            for source, destination in mod.runtime_credential_destinations().items()
        ],
    }


def invoke(before, after, observations, *, result=0):
    with (
        patch.object(mod, "inspect_container", side_effect=[before, after]),
        patch.object(mod, "runtime_credential_mounts_current", side_effect=observations),
        patch.object(mod, "wait_container_health") as health,
        patch.object(mod, "run", return_value=SimpleNamespace(returncode=result)) as run,
    ):
        mod.ensure_runtime_credential_mounts()
        return [call.args[0] for call in run.call_args_list], health.call_args_list


@pytest.mark.parametrize("state,current,expected", [
    ("running", True, []),
    ("running", False, [["docker", "restart", "a" * 64]]),
    ("exited", False, [["docker", "start", "a" * 64]]),
    ("created", False, [["docker", "start", "a" * 64]]),
])
def test_recovery_preserves_existing_runtime_identity(state, current, expected):
    before, after = runtime_info(state), runtime_info()
    after["Mounts"].reverse()  # Docker inspection does not promise map order.
    calls, health = invoke(before, after, [current, True] if state == "running" else [True])
    assert calls == expected
    assert len(health) == 1
    assert health[0].args == (mod.RUNTIME_CONTAINER,)
    assert not any(call[1] in ("rm", "run", "create", "rename", "update") for call in calls)


@pytest.mark.parametrize("kind", [
    "wrong_id", "wrong_image", "wrong_revision", "changed_config", "unhealthy",
    "stale_after_restart", "restart_failure", "wrong_destination", "writable_bind",
    "duplicate_mount", "paused", "probe_failure",
])
def test_unexpected_runtime_recovery_fails_closed(kind):
    before, after = runtime_info(), runtime_info()
    observations = [False, True]
    rc = 0
    if kind == "wrong_id":
        after["Id"] = "d" * 64
    elif kind == "wrong_image":
        after["Image"] = "sha256:" + "d" * 64
    elif kind == "wrong_revision":
        after["Config"]["Labels"]["com.teamaot.jason.source_revision"] = "d" * 40
    elif kind == "changed_config":
        after["Config"]["Env"] = ["UNRELATED=synthetic"]
    elif kind == "unhealthy":
        after["State"]["Health"]["Status"] = "unhealthy"
    elif kind == "stale_after_restart":
        observations = [False, False]
    elif kind == "restart_failure":
        rc = 1
    elif kind == "wrong_destination":
        before["Mounts"][0]["Destination"] = "/unexpected"
    elif kind == "writable_bind":
        before["Mounts"][0]["RW"] = True
    elif kind == "duplicate_mount":
        before["Mounts"].append(deepcopy(before["Mounts"][0]))
    elif kind == "paused":
        before["State"]["Status"] = "paused"
    elif kind == "probe_failure":
        observations = [mod.RecoveryError("probe failed")]
    with (
        patch.object(mod, "inspect_container", side_effect=[before, after]),
        patch.object(mod, "runtime_credential_mounts_current", side_effect=observations),
        patch.object(mod, "wait_container_health"),
        patch.object(mod, "run", return_value=SimpleNamespace(returncode=rc)) as run,
    ):
        with pytest.raises(mod.RecoveryError):
            mod.ensure_runtime_credential_mounts()
        if kind in ("wrong_destination", "writable_bind", "duplicate_mount", "paused", "probe_failure"):
            run.assert_not_called()


@pytest.mark.parametrize("rc,expected", [(0, True), (42, False), (1, None), (126, None)])
def test_mount_probe_uses_metadata_only(rc, expected):
    synthetic = SimpleNamespace(
        st_mode=0o100400, st_uid=1000, st_gid=1000, st_size=12, st_dev=5, st_ino=23,
    )
    with (
        patch.object(mod.os, "lstat", return_value=synthetic),
        patch.object(mod, "run", return_value=SimpleNamespace(returncode=rc)) as run,
    ):
        if expected is None:
            with pytest.raises(mod.RecoveryError):
                mod.runtime_credential_mounts_current("a" * 64)
        else:
            assert mod.runtime_credential_mounts_current("a" * 64) is expected
        args = run.call_args.args[0]
        assert args[:5] == ["docker", "exec", "--user", "1000:1000", "a" * 64]
        assert "os.lstat(path)" in args[-2]
        assert "open(" not in args[-2]
        assert json.loads(args[-1]) == [[destination, 5, 23]
            for destination in mod.runtime_credential_destinations().values()]
        assert run.call_args.kwargs == {"quiet": True}


def test_legacy_recovery_defers_when_release_lock_held(tmp_path):
    lock = tmp_path / "production.lock"
    lock.touch()
    metadata = SimpleNamespace(st_mode=0o100664, st_nlink=1, st_uid=1000)
    with (
        patch.object(mod, "LEGACY_RELEASE_LOCK", lock),
        patch.object(mod, "PMV4_RELEASE_LOCK", tmp_path / "absent-pmv4"),
        patch.object(mod, "COORDINATED_READBACK", tmp_path / "absent-readback"),
        patch.object(mod.os, "fstat", return_value=metadata),
    ):
        with lock.open("rb") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX)
            with pytest.raises(mod.RecoveryDeferred):
                with mod.runtime_recovery_transaction():
                    pytest.fail("entered locked release transaction")
        with mod.runtime_recovery_transaction():
            pass


def test_pmv4_recovery_never_falls_back_to_legacy_lock(tmp_path):
    pmv4 = tmp_path / "pmv4.lock"
    pmv4.touch()
    with (
        patch.object(mod, "PMV4_RELEASE_LOCK", pmv4),
        patch.object(mod, "HOST_GUARD", tmp_path / "missing-guard.py"),
        patch.object(mod, "LEGACY_RELEASE_LOCK", tmp_path / "legacy.lock"),
    ):
        with pytest.raises(FileNotFoundError):
            with mod.runtime_recovery_transaction():
                pytest.fail("fell back to legacy lock")
