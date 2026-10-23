"""P0 #1974: exact legacy systemd job / fast-health replacement proof.

No test starts or stops real systemd services or contacts a provider.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import pwd
import stat
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "release_authority_fast_health_handoff.py"
spec = importlib.util.spec_from_file_location("jason_fast_handoff", SOURCE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
OLD = "aca94fdc0bfa551162f6ea99d7ddded311786414"


def report(*, mode=None):
    return {
        "status": "pass",
        "check_mode": mode or gate.CHECK_MODE,
        "full_proof_status": "pass",
        "full_proof_age_seconds": 4700,
        "snapshot_source_exit_code": 0,
        "provider_contacted": False,
        "provider_credentials_used": False,
        "failures": [],
    }


@pytest.fixture
def snapshot(monkeypatch, tmp_path):
    output = tmp_path / "operational-health.json"
    monkeypatch.setattr(gate, "OUTPUT", output)
    monkeypatch.setattr(gate, "FULL", tmp_path / "operational-full-health.json")
    def publish(data=None):
        output.write_text(json.dumps(report() if data is None else data))
        output.chmod(0o600)
    return output, publish


def test_fresh_real_fast_snapshot_passes_and_legacy_result_is_rejected(snapshot):
    output, publish = snapshot
    publish()
    gate._verify_snapshot(not_before_ns=0)
    publish(report(mode="legacy_full_scan"))
    with pytest.raises(gate.HandoffRefused, match="independent PASS"):
        gate._verify_snapshot(not_before_ns=0)


@pytest.mark.parametrize("field,value", [
    ("status", "fail"),
    ("check_mode", "legacy_full_scan"),
    ("full_proof_status", "missing_or_invalid"),
    ("full_proof_age_seconds", 30*60*60+1),
    ("full_proof_age_seconds", None),
    ("snapshot_source_exit_code", 124),
    ("provider_contacted", True),
    ("provider_credentials_used", True),
    ("failures", ["full_integrity_proof_missing_stale_or_invalid"]),
])
def test_fast_probe_never_masks_missing_integrity_or_failed_execution(snapshot, field, value):
    _, publish = snapshot
    r = report()
    r[field] = value
    publish(r)
    with pytest.raises(gate.HandoffRefused):
        gate._verify_snapshot(not_before_ns=0)


def test_stale_or_world_readable_snapshot_is_denied(snapshot):
    output, publish = snapshot
    publish()
    with pytest.raises(gate.HandoffRefused, match="stale"):
        gate._verify_snapshot(not_before_ns=output.stat().st_mtime_ns + 2_000_000_000)
    output.chmod(0o644)
    with pytest.raises(gate.HandoffRefused):
        gate._verify_snapshot(not_before_ns=0)


def test_symlinked_fast_health_evidence_is_denied(snapshot):
    output, publish = snapshot
    publish()
    backup = output.with_name("trusted-snapshot.json")
    output.rename(backup)
    output.symlink_to(backup)
    with pytest.raises(gate.HandoffRefused):
        gate._verify_snapshot(not_before_ns=0)


def _fake_legacy_process(tmp_path, *, argv=None):
    proc_root = tmp_path / "proc"
    pid_dir = proc_root / "4242"
    pid_dir.mkdir(parents=True)
    script = argv or gate.LEGACY.encode("ascii")
    (pid_dir / "cmdline").write_bytes(b"/usr/bin/python3\0" + script + b"\0--output\0")
    return proc_root


def test_real_legacy_job_requires_exact_command_uid_and_queued_start(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "PROC_ROOT", _fake_legacy_process(tmp_path))
    props = {
        "ActiveState": "activating", "SubState": "start",
        "Job": "27869044", "ExecMainPID": "4242",
    }
    monkeypatch.setattr(gate, "_show", lambda key: props[key])
    assert gate._legacy_job_is_exact() is True
    props["Job"] = ""
    assert gate._legacy_job_is_exact() is False
    props["Job"] = "27869044"
    (gate.PROC_ROOT / "4242" / "cmdline").write_bytes(
        b"/usr/bin/python3\0/opt/jason/current/tools/unknown_check.py\0"
    )
    assert gate._legacy_job_is_exact() is False
    monkeypatch.setattr(gate.pwd, "getpwnam", lambda _: SimpleNamespace(pw_uid=0))
    assert gate._legacy_job_is_exact() is False


def _reconcile_fixture(monkeypatch, tmp_path, *, active="inactive", sub="dead", job=""):
    # Only the systemd interface is mocked. Root/source identity and the
    # security-critical snapshot validator execute unchanged in these tests.
    source = tmp_path / OLD
    source.mkdir()
    monkeypatch.setattr(gate.os, "geteuid", lambda: 0)
    monkeypatch.setattr(gate, "_installed_is_exact", lambda _: None)
    # Use immutable current SHA, the only source-root field used by reconcile.
    original_current = gate.Path
    class CurrentPath:
        def __init__(self, path):
            self.path = path
        def resolve(self):
            return SimpleNamespace(name=source.name)
    monkeypatch.setattr(gate, "Path", lambda path: CurrentPath(path)
                        if path == "/opt/jason/current" else original_current(path))
    props = {"ActiveState": active, "SubState": sub, "Job": job}
    monkeypatch.setattr(gate, "_show", lambda key: props[key])
    return source


def test_idle_new_service_runs_systemd_full_fast_health_success(monkeypatch, tmp_path, snapshot):
    source = _reconcile_fixture(monkeypatch, tmp_path)
    output, publish = snapshot
    calls = []
    def call(args, *, timeout=12):
        calls.append((args, timeout))
        publish()
        return ""
    monkeypatch.setattr(gate, "_call", call)
    assert gate.reconcile(source) == "SYSTEMD_FAST_HEALTH_VERIFIED"
    assert len(calls) == 1
    assert calls[0][0] == ["/usr/bin/systemctl", "start", gate.UNIT]
    assert calls[0][1] == 40


def test_inflight_old_sqlite_scan_is_not_stopped_and_direct_fast_probe_is_required(
    monkeypatch, tmp_path, snapshot,
):
    source = _reconcile_fixture(
        monkeypatch, tmp_path, active="activating", sub="start", job="27869044"
    )
    monkeypatch.setattr(gate, "_legacy_job_is_exact", lambda: True)
    seen = []
    monkeypatch.setattr(gate, "_run_direct_probe", lambda s: seen.append(s))
    assert gate.reconcile(source) == "INFLIGHT_LEGACY_SCAN_FAST_HEALTH_VERIFIED"
    assert seen == [source]


def test_unknown_or_queued_nonlegacy_unit_fails_closed(monkeypatch, tmp_path):
    source = _reconcile_fixture(
        monkeypatch, tmp_path, active="activating", sub="start", job="27869044"
    )
    monkeypatch.setattr(gate, "_legacy_job_is_exact", lambda: False)
    with pytest.raises(gate.HandoffRefused, match="not safely eligible"):
        gate.reconcile(source)


def test_missing_canonical_new_unit_or_timer_fails_without_invoking_health(monkeypatch, tmp_path):
    source = tmp_path / "release"
    unit_file = source / gate.UNIT_IN_RELEASE
    unit_file.parent.mkdir(parents=True)
    unit_file.write_text(gate.EXPECTED_FAST)
    installed = tmp_path / gate.UNIT
    installed.write_text(gate.EXPECTED_FAST)
    monkeypatch.setattr(gate, "INSTALLED", installed)
    called = []
    monkeypatch.setattr(gate, "_call", lambda *args, **kw: called.append(args) or "active")
    with pytest.raises(gate.HandoffRefused, match="root-owned"):
        gate._installed_is_exact(source)
    assert called == []


def test_final_readback_fails_when_legacy_scan_overwrites_fast_snapshot(snapshot):
    _, publish = snapshot
    publish()
    gate._verify_snapshot(not_before_ns=0)
    publish(report(mode="legacy_full_scan"))
    with pytest.raises(gate.HandoffRefused):
        gate._verify_snapshot(not_before_ns=0)


def test_real_host_shell_calls_fast_verifier_twice_but_never_kills_health_job():
    script = (SOURCE.parent / "reconcile_production_host_services.sh").read_text()
    assert 'AUTHORITY_HANDOFF="$RELEASE_DIR/tools/release_authority_fast_health_handoff.py"' in script
    assert '/usr/bin/python3 "$AUTHORITY_HANDOFF" --release-dir "$RELEASE_DIR"' in script
    assert '/usr/bin/python3 "$AUTHORITY_HANDOFF" --release-dir "$RELEASE_DIR" --verify-only' in script
    assert 'timeout --signal=TERM --kill-after=5s 45s systemctl start "$unit"' not in script
    assert script.index("systemctl daemon-reload") < script.index(
        '/usr/bin/python3 "$AUTHORITY_HANDOFF" --release-dir "$RELEASE_DIR"')
    assert script.index('AUTHORITY_HANDOFF="$RELEASE_DIR/tools/') < script.index(
        'JASON_HOST_SERVICE_RECONCILIATION=PASS')



@pytest.mark.parametrize("owner,group,mode,allowed", [
    (0, 0, 0o644, True),
    (0, 0, 0o664, True),
    (0, 1000, 0o644, True),
    (0, 1000, 0o664, False),
    (1000, 0, 0o644, False),
    (0, 0, 0o666, False),
])
def test_exact_root_unit_policy_rejects_untrusted_writable_users(owner, group, mode, allowed):
    record = SimpleNamespace(
        st_mode=stat.S_IFREG | mode, st_uid=owner, st_gid=group
    )
    assert gate._trusted_root_regular(record) is allowed


def test_exact_canonical_fast_systemd_unit_and_timer_verification(monkeypatch, tmp_path):
    source = tmp_path / OLD
    source_unit = source / gate.UNIT_IN_RELEASE
    source_unit.parent.mkdir(parents=True)
    contents = (
        "[Unit]\nDescription=Frequent Fast Probe\n"
        "[Service]\nType=oneshot\n"
        "ExecStart=/usr/bin/python3 " + gate.EXPECTED_FAST
    )
    source_unit.write_text(contents)
    installed = tmp_path / gate.UNIT
    installed.write_text(contents)
    monkeypatch.setattr(gate, "INSTALLED", installed)
    # Tested root metadata separately; this fixture runs as non-root.
    monkeypatch.setattr(gate, "_trusted_root_regular", lambda _: True)
    props = {
        "FragmentPath": str(installed), "DropInPaths": "",
        "ExecStart": ("{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 "
                      + gate.EXPECTED_FAST + " --output /var/lib/jason/openclaw/operational-health.json }"),
    }
    monkeypatch.setattr(gate, "_show", lambda key: props[key])
    monkeypatch.setattr(gate, "_call", lambda cmd, **kwargs:
                        "active" if cmd == ["/usr/bin/systemctl", "is-active", gate.TIMER]
                        else (_ for _ in ()).throw(AssertionError("unexpected systemd call")))
    gate._installed_is_exact(source)
    props["DropInPaths"] = "/etc/systemd/system/unreviewed-override.conf"
    with pytest.raises(gate.HandoffRefused, match="override"):
        gate._installed_is_exact(source)
    props["DropInPaths"] = ""
    props["ExecStart"] = "legacy checker"
    with pytest.raises(gate.HandoffRefused, match="not new fast checker"):
        gate._installed_is_exact(source)
    props["ExecStart"] = gate.EXPECTED_FAST
    installed.write_text(contents + "\n# changed")
    with pytest.raises(gate.HandoffRefused, match="differs"):
        gate._installed_is_exact(source)


def test_actual_fallback_command_is_unprivileged_and_result_still_verified(
    monkeypatch, tmp_path, snapshot
):
    source = tmp_path / OLD
    program = source / "tools/openclaw_authority_fast_health.py"
    program.parent.mkdir(parents=True)
    program.write_text("# only a synthetic fixture, never executed")
    output, publish = snapshot
    monkeypatch.setattr(gate, "_trusted_root_regular", lambda _: True)
    commands = []
    def real_snapshot_fake_process(argv, *, timeout=12):
        commands.append((argv, timeout))
        publish()
        return '{"status":"pass"}'
    monkeypatch.setattr(gate, "_call", real_snapshot_fake_process)
    gate._run_direct_probe(source)
    assert len(commands) == 1
    assert commands[0][0][:7] == [
        "/usr/sbin/runuser", "-u", "al", "--",
        "/usr/bin/python3", str(program), "--output",
    ]
    assert commands[0][1] == 35
    # Legacy health process was never stopped or restarted.
    assert all("systemctl" not in str(command) for command, _ in commands)
    # Even a successful process return code with an invalid proof must deny.
    monkeypatch.setattr(gate, "_call", lambda argv, **kw: '{"status":"pass"}')
    publish(report(mode="legacy_full_scan"))
    with pytest.raises(gate.HandoffRefused):
        gate._run_direct_probe(source)



@pytest.mark.parametrize("failure", ["timeout", "nonzero", "oserror"])
def test_bounded_systemd_or_fast_probe_command_failure_never_becomes_pass(
    monkeypatch, failure
):
    import subprocess
    def failing_run(argv, **kwargs):
        assert kwargs.get("check") is True
        assert kwargs.get("timeout") == 35
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 35)
        if failure == "nonzero":
            raise subprocess.CalledProcessError(2, argv)
        raise OSError("command unavailable")
    monkeypatch.setattr(gate.subprocess, "run", failing_run)
    with pytest.raises(gate.HandoffRefused, match="bounded systemd or health command failed"):
        gate._call(["/usr/bin/true"], timeout=35)


def test_successful_systemd_exit_without_fresh_fast_json_is_still_denied(
    monkeypatch, tmp_path, snapshot
):
    source = _reconcile_fixture(monkeypatch, tmp_path)
    output, publish = snapshot
    publish(report(mode="legacy_full_scan"))
    monkeypatch.setattr(gate, "_call", lambda argv, **kw: "")
    with pytest.raises(gate.HandoffRefused, match="stale"):
        gate.reconcile(source)
