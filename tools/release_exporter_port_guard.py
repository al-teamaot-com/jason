#!/usr/bin/env python3
"""Fail-closed bounded exporter listener ownership check for host reconciliation.

Never terminates processes, changes a unit, or treats an HTTP response from a
different process as evidence that the expected systemd service owns the port.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time

UNIT_PORTS = {
    "jason-client-posture-exporter.service": 9472,
    "jason-playbook-exporter.service": 9468,
    "jason-production-health-exporter.service": 9467,
    "jason-operations-configuration-exporter.service": 9477,
    "jason-resolution-memory-exporter.service": 9470,
    "jason-reflection-exporter.service": 9476,
    "jason-security-control-exporter.service": 9471,
    "jason-status-exporter.service": 9464,
    "jason-usage-attribution-exporter.service": 9466,
    "jason-usage-exporter.service": 9465,
}
PID_PATTERN = re.compile(r"\bpid=(\d+)\b")


def listeners(port: int) -> list[tuple[str, tuple[int, ...]]]:
    """Inspect *listening* TCP sockets, not client connections."""
    proc = subprocess.run(
        ["ss", "-H", "-l", "-t", "-n", "-p", f"sport = :{port}"],
        capture_output=True, text=True, timeout=5, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ss failed for exporter port {port}: {proc.stderr[:180]}")
    result = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] != "LISTEN":
            raise RuntimeError(f"unrecognized socket record for {port}")
        actual = parts[3].rsplit(":", 1)[-1]
        if actual != str(port):
            raise RuntimeError(f"socket filter returned unrelated port {actual}")
        pids = tuple(sorted({int(v) for v in PID_PATTERN.findall(line)}))
        # A listener with no inspectable owner is NEVER considered healthy.
        result.append((parts[3], pids))
    return result


def main_pid(unit: str) -> int:
    result = subprocess.run(
        ["systemctl", "show", unit, "--property=MainPID", "--value"],
        capture_output=True, text=True, timeout=5, check=False,
    )
    if result.returncode or not result.stdout.strip().isdigit():
        raise RuntimeError(f"could not read systemd MainPID for {unit}")
    return int(result.stdout.strip())


def verify(mode: str, unit: str, timeout_seconds: float = 12.0) -> None:
    if unit not in UNIT_PORTS:
        raise RuntimeError(f"unit not in approved exporter allowlist: {unit}")
    port = UNIT_PORTS[unit]
    end = time.monotonic() + timeout_seconds
    last = ""
    while True:
        observed = listeners(port)
        if mode == "free":
            if not observed:
                return
            last = f"{unit} port {port} still occupied: {observed!r}"
        else:
            pid = main_pid(unit)
            if observed and pid > 0:
                # The kernel's ss PID attribution can briefly lag a newly
                # activated listener even while systemd has its real MainPID.
                # A *known foreign* owner is a hard failure. An uninspectable
                # socket is never accepted as owned; bound an additional
                # read until ALL listener PID sets equal the systemd MainPID.
                # This keeps fail-closed ownership without a false first-
                # sample failure at the exact systemd/socket startup race.
                if any(owners and set(owners) != {pid} for _, owners in observed):
                    raise RuntimeError(
                        f"{unit} port {port} is owned by a different process: "
                        f"systemd MainPID={pid}; sockets={observed!r}"
                    )
                if not any(not owners for _, owners in observed):
                    return
                last = (
                    f"{unit} port {port} still has unattributed listener(s): "
                    f"systemd MainPID={pid}; sockets={observed!r}"
                )
            elif observed:
                raise RuntimeError(
                    f"{unit} port {port} is occupied but systemd has no "
                    f"valid MainPID: {observed!r}"
                )
            else:
                last = f"{unit} port {port} has no listening owner (MainPID={pid})"
        if time.monotonic() >= end:
            raise RuntimeError(f"bounded exporter {mode} check failed: {last}")
        time.sleep(0.25)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("free", "owned"), required=True)
    parser.add_argument("--unit", choices=sorted(UNIT_PORTS), required=True)
    parser.add_argument("--timeout-seconds", type=float, default=12.0)
    args = parser.parse_args()
    if not 0 <= args.timeout_seconds <= 30:
        parser.error("exporter check timeout must be between 0 and 30 seconds")
    try:
        verify(args.mode, args.unit, args.timeout_seconds)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"EXPORTER_PORT_GUARD=FAIL unit={args.unit} check={args.mode} detail={exc}", file=sys.stderr)
        return 1
    print(f"EXPORTER_PORT_GUARD=PASS unit={args.unit} check={args.mode} port={UNIT_PORTS[args.unit]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
