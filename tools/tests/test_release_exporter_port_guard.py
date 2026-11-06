"""Regression tests for exporter port ownership and bounded host convergence."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import socket
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_exporter_port_guard", ROOT / "tools/release_exporter_port_guard.py"
)
assert SPEC and SPEC.loader
port_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(port_guard)
UNIT = "jason-resolution-memory-exporter.service"
PORT = port_guard.UNIT_PORTS[UNIT]


def test_allowlist_has_unique_known_exporter_ports():
    assert len(port_guard.UNIT_PORTS) == 10
    assert len(set(port_guard.UNIT_PORTS.values())) == 10
    assert port_guard.UNIT_PORTS["jason-client-posture-exporter.service"] == 9472
    assert port_guard.UNIT_PORTS["jason-playbook-exporter.service"] == 9468


def test_free_listener_rejected_without_terminating_process():
    with patch.object(port_guard, "listeners", return_value=[("0.0.0.0:9470", (7777,))]):
        with pytest.raises(RuntimeError, match="still occupied"):
            port_guard.verify("free", UNIT, 0)


def test_free_listener_check_succeeds_only_when_empty():
    with patch.object(port_guard, "listeners", side_effect=[
        [("0.0.0.0:9470", (7777,))], [],
    ]), patch.object(port_guard.time, "sleep", return_value=None):
        port_guard.verify("free", UNIT, 0.1)


def test_after_start_pid_must_match_systemd_unit_main_pid():
    with patch.object(port_guard, "listeners", return_value=[("0.0.0.0:9470", (4711,))]):
        with patch.object(port_guard, "main_pid", return_value=4711):
            port_guard.verify("owned", UNIT, 0)
        with patch.object(port_guard, "main_pid", return_value=4712):
            with pytest.raises(RuntimeError, match="different process"):
                port_guard.verify("owned", UNIT, 0)


def test_unattributed_socket_is_not_accepted_as_healthy():
    with patch.object(port_guard, "listeners", return_value=[("0.0.0.0:9470", ())]):
        with patch.object(port_guard, "main_pid", return_value=4711):
            with pytest.raises(RuntimeError, match="unattributed listener"):
                port_guard.verify("owned", UNIT, 0)


def test_unattributed_first_socket_sample_then_exact_pid_is_accepted():
    # A newly started service can bind before ss prints a PID. It cannot pass
    # until the next sample contains the exact systemd MainPID.
    with patch.object(port_guard, "listeners", side_effect=[
        [("0.0.0.0:9470", ())], [("0.0.0.0:9470", (4711,))],
    ]) as read, patch.object(port_guard, "main_pid", return_value=4711), \
            patch.object(port_guard.time, "sleep", return_value=None):
        port_guard.verify("owned", UNIT, 0.1)
        assert read.call_count == 2


def test_unattributed_first_socket_does_not_mask_followup_foreign_pid():
    with patch.object(port_guard, "listeners", side_effect=[
        [("0.0.0.0:9470", ())], [("0.0.0.0:9470", (9911,))],
    ]) as read, patch.object(port_guard, "main_pid", return_value=4711), \
            patch.object(port_guard.time, "sleep", return_value=None):
        with pytest.raises(RuntimeError, match="different process"):
            port_guard.verify("owned", UNIT, 0.1)
        assert read.call_count == 2


def test_multiple_listeners_require_every_pid_to_be_attributed():
    with patch.object(port_guard, "listeners", side_effect=[
        [("0.0.0.0:9470", (4711,)), ("[::]:9470", ())],
        [("0.0.0.0:9470", (4711,)), ("[::]:9470", (4711,))],
    ]) as read, patch.object(port_guard, "main_pid", return_value=4711), \
            patch.object(port_guard.time, "sleep", return_value=None):
        port_guard.verify("owned", UNIT, 0.1)
        assert read.call_count == 2


def test_mixed_unknown_and_foreign_pid_fails_without_retry():
    with patch.object(port_guard, "listeners", return_value=[
        ("0.0.0.0:9470", ()), ("[::]:9470", (9999,)),
    ]) as read, patch.object(port_guard, "main_pid", return_value=4711), \
            patch.object(port_guard.time, "sleep") as sleep:
        with pytest.raises(RuntimeError, match="different process"):
            port_guard.verify("owned", UNIT, 30)
        assert read.call_count == 1
        sleep.assert_not_called()


def test_persistently_unattributed_socket_fails_after_bounded_wait():
    # Never report PASS if ss PID attribution never becomes observable.
    with patch.object(port_guard, "listeners", return_value=[("0.0.0.0:9470", ())]) as read, \
            patch.object(port_guard, "main_pid", return_value=4711), \
            patch.object(port_guard.time, "monotonic", side_effect=[0.0, 0.0, 0.2]), \
            patch.object(port_guard.time, "sleep") as sleep:
        with pytest.raises(RuntimeError, match="bounded exporter owned check failed.*unattributed"):
            port_guard.verify("owned", UNIT, 0.1)
        assert read.call_count == 2
        sleep.assert_called_once_with(0.25)


def test_down_unit_does_not_claim_occupied_socket():
    with patch.object(port_guard, "listeners", return_value=[("0.0.0.0:9470", (999,))]):
        with patch.object(port_guard, "main_pid", return_value=0):
            with pytest.raises(RuntimeError, match="no valid MainPID"):
                port_guard.verify("owned", UNIT, 0)


def test_after_start_waits_for_own_listener():
    with patch.object(port_guard, "listeners", side_effect=[[], [("0.0.0.0:9470", (4711,))]]):
        with patch.object(port_guard, "main_pid", return_value=4711):
            with patch.object(port_guard.time, "sleep", return_value=None):
                port_guard.verify("owned", UNIT, 0.1)


def test_unknown_unit_is_rejected():
    with pytest.raises(RuntimeError, match="allowlist"):
        port_guard.verify("owned", "some-unrelated-service.service", 0)


def test_tcp_listener_discovery_checks_kernel_socket_table():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        observed = port_guard.listeners(port)
        assert observed
        assert any(os.getpid() in owners for _, owners in observed)
    assert port_guard.listeners(port) == []


def test_ss_reports_listening_port_even_when_process_pid_is_unavailable():
    class SocketOutput:
        returncode = 0
        stdout = "LISTEN 0 5 0.0.0.0:9470 0.0.0.0:*\n"
        stderr = ""
    with patch.object(port_guard.subprocess, "run", return_value=SocketOutput()):
        assert port_guard.listeners(PORT) == [("0.0.0.0:9470", ())]


def test_failed_socket_query_is_not_mistaken_for_free():
    class Status:
        returncode = 1
        stdout = ""
        stderr = "permission unavailable"

    with patch.object(port_guard.subprocess, "run", return_value=Status()):
        with pytest.raises(RuntimeError, match="ss failed"):
            port_guard.listeners(PORT)


def test_host_script_releases_all_ports_before_restarting_any_exporter():
    script = (ROOT / "tools/reconcile_production_host_services.sh").read_text()
    assert script.index('for unit in "${EXPORTER_UNITS[@]}"; do\n  CURRENT_UNIT="$unit"\n  timeout') < script.index('--mode free --unit "$unit"')
    assert script.index('--mode free --unit "$unit"') < script.index('--mode owned --unit "$unit"')
    assert 'pgrep -u al -f' not in script
    assert 'HOST_RECONCILE_FAILURE step=' in script
    assert 'systemctl show "$CURRENT_UNIT" -p ActiveState -p SubState -p Result -p ExecMainStatus' in script
