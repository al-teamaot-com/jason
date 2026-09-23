#!/usr/bin/env python3
"""Fail-closed replacement of a live Docker container while preserving its runtime shape."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any


def _run(args: list[str], *, env: dict[str, str] | None = None, quiet: bool = False) -> None:
    kwargs: dict[str, Any] = {"check": True, "text": True}
    if env is not None:
        kwargs["env"] = env
    if quiet:
        kwargs["stdout"] = subprocess.DEVNULL
    subprocess.run(args, **kwargs)


def _output(args: list[str]) -> str:
    return subprocess.check_output(args, text=True).strip()


def _inspect(name: str) -> dict[str, Any]:
    return json.loads(_output(["docker", "inspect", name]))[0]


def _image_id(image: str) -> str:
    return _output(["docker", "image", "inspect", image, "--format", "{{.Id}}"])


def _container_exists(name: str) -> bool:
    return subprocess.run(
        ["docker", "inspect", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def _health(name: str, url: str, attempts: int, interval: float) -> None:
    script = (
        "import urllib.request; "
        f"r=urllib.request.urlopen({url!r}, timeout=3); "
        "assert r.status == 200, r.status"
    )
    for attempt in range(1, attempts + 1):
        completed = subprocess.run(
            ["docker", "exec", name, "python", "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        print(f"HEALTH_ATTEMPT={attempt} RESULT={'PASS' if completed.returncode == 0 else 'WAIT'}")
        if completed.returncode == 0:
            return
        time.sleep(interval)
    raise RuntimeError("replacement container did not pass health verification")


def _build_create_command(*, live: str, image: str, source_revision: str, harden: bool):
    src = _inspect(live)
    config = src["Config"]
    host = src["HostConfig"]

    env_map = os.environ.copy()
    env_keys: list[str] = []
    for item in config.get("Env") or []:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key == "JASON_SOURCE_REVISION":
            value = source_revision
        env_map[key] = value
        env_keys.append(key)

    args = ["docker", "create", "--name", live]
    if config.get("User"):
        args += ["--user", config["User"]]
    if config.get("WorkingDir"):
        args += ["--workdir", config["WorkingDir"]]
    restart = (host.get("RestartPolicy") or {}).get("Name")
    if restart:
        args += ["--restart", restart]
    if harden or host.get("ReadonlyRootfs"):
        args += ["--read-only"]
    if host.get("Privileged"):
        args += ["--privileged"]

    cap_drop = list(host.get("CapDrop") or [])
    if harden and "ALL" not in cap_drop:
        cap_drop.append("ALL")
    for capability in cap_drop:
        args += ["--cap-drop", capability]

    for capability in host.get("CapAdd") or []:
        args += ["--cap-add", capability]

    security_options = list(host.get("SecurityOpt") or [])
    if harden and "no-new-privileges:true" not in security_options:
        security_options.append("no-new-privileges:true")
    for option in security_options:
        args += ["--security-opt", option]

    tmpfs_entries = dict(host.get("Tmpfs") or {})
    if harden:
        tmpfs_entries["/tmp"] = "rw,nosuid,nodev,noexec,size=32m"
    for destination, options in tmpfs_entries.items():
        args += ["--tmpfs", f"{destination}:{options}"]
    for key in env_keys:
        args += ["--env", key]

    for mount in src.get("Mounts") or []:
        mount_type = mount.get("Type")
        if mount_type not in {"bind", "volume"}:
            raise RuntimeError(f"unsupported mount type for exact clone: {mount_type}")
        spec = f"type={mount_type},src={mount['Source']},dst={mount['Destination']}"
        if not mount.get("RW", False):
            spec += ",readonly"
        args += ["--mount", spec]

    for container_port, bindings in (host.get("PortBindings") or {}).items():
        for binding in bindings or []:
            host_ip = binding.get("HostIp") or ""
            host_port = binding.get("HostPort") or ""
            prefix = f"{host_ip}:" if host_ip else ""
            args += ["--publish", f"{prefix}{host_port}:{container_port}"]

    primary_network = host.get("NetworkMode")
    if primary_network and primary_network not in {"default", "bridge"}:
        args += ["--network", primary_network]

    labels = dict(config.get("Labels") or {})
    labels["org.opencontainers.image.revision"] = source_revision
    labels["com.teamaot.jason.source_revision"] = source_revision
    labels["com.teamaot.jason.deployment-purpose"] = "production"
    for key, value in sorted(labels.items()):
        args += ["--label", f"{key}={value}"]

    health = config.get("Healthcheck") or {}
    test = health.get("Test") or []
    if test:
        if test[0] == "CMD-SHELL":
            args += ["--health-cmd", test[1]]
        elif test[0] == "CMD":
            args += ["--health-cmd", " ".join(test[1:])]
        if health.get("Interval"):
            args += ["--health-interval", f"{health['Interval']}ns"]
        if health.get("Timeout"):
            args += ["--health-timeout", f"{health['Timeout']}ns"]
        if health.get("StartPeriod"):
            args += ["--health-start-period", f"{health['StartPeriod']}ns"]
        if health.get("Retries") is not None:
            args += ["--health-retries", str(health["Retries"])]

    log_config = host.get("LogConfig") or {}
    if log_config.get("Type"):
        args += ["--log-driver", log_config["Type"]]
        for key, value in sorted((log_config.get("Config") or {}).items()):
            args += ["--log-opt", f"{key}={value}"]

    args.append(image)
    secondary_networks = [
        network
        for network in sorted((src["NetworkSettings"].get("Networks") or {}))
        if network != primary_network
    ]
    return args, env_map, secondary_networks, src


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--rollback", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--health-url", required=True)
    parser.add_argument("--health-attempts", type=int, default=30)
    parser.add_argument("--health-interval", type=float, default=2.0)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--harden", action="store_true")
    args = parser.parse_args()

    if not _container_exists(args.live):
        raise SystemExit(f"live container not found: {args.live}")
    if _container_exists(args.rollback):
        raise SystemExit(f"rollback container already exists: {args.rollback}")
    candidate_id = _image_id(args.image)
    create_cmd, env_map, secondary_networks, source = _build_create_command(
        live=args.live,
        image=args.image,
        source_revision=args.source_revision,
        harden=args.harden,
    )

    print("PREFLIGHT=PASS")
    print(f"LIVE_CONTAINER={args.live}")
    print(f"SOURCE_CONTAINER_ID={source['Id']}")
    print(f"SOURCE_IMAGE_ID={source['Image']}")
    print(f"CANDIDATE_IMAGE={args.image}")
    print(f"CANDIDATE_IMAGE_ID={candidate_id}")
    print(f"ROLLBACK_CONTAINER={args.rollback}")
    print(f"SECONDARY_NETWORK_COUNT={len(secondary_networks)}")
    print(f"MOUNT_COUNT={len(source.get('Mounts') or [])}")
    print(f"ENV_COUNT={len(source['Config'].get('Env') or [])}")
    print(f"HARDENING_REQUESTED={args.harden}")
    if args.preflight:
        return 0

    old_renamed = False
    try:
        _run(["docker", "stop", args.live], quiet=True)
        _run(["docker", "rename", args.live, args.rollback], quiet=True)
        old_renamed = True
        _run(create_cmd, env=env_map, quiet=True)
        for network in secondary_networks:
            _run(["docker", "network", "connect", network, args.live], quiet=True)
        _run(["docker", "start", args.live], quiet=True)

        replacement = _inspect(args.live)
        if replacement["Image"] != candidate_id:
            raise RuntimeError("replacement container image does not match candidate image")
        label_revision = (replacement["Config"].get("Labels") or {}).get(
            "com.teamaot.jason.source_revision"
        )
        if label_revision != args.source_revision:
            raise RuntimeError("replacement source revision label mismatch")
        env_revision = None
        for item in replacement["Config"].get("Env") or []:
            if item.startswith("JASON_SOURCE_REVISION="):
                env_revision = item.split("=", 1)[1]
                break
        if env_revision is not None and env_revision != args.source_revision:
            raise RuntimeError("replacement JASON_SOURCE_REVISION mismatch")

        if args.harden:
            host_config = replacement["HostConfig"]
            if host_config.get("ReadonlyRootfs") is not True:
                raise RuntimeError("replacement root filesystem is not read-only")
            if "ALL" not in (host_config.get("CapDrop") or []):
                raise RuntimeError("replacement does not drop all Linux capabilities")
            if "no-new-privileges:true" not in (host_config.get("SecurityOpt") or []):
                raise RuntimeError("replacement does not enforce no-new-privileges")
            tmpfs = host_config.get("Tmpfs") or {}
            if "/tmp" not in tmpfs:
                raise RuntimeError("replacement does not provide hardened /tmp tmpfs")
            print("HARDENING_VERIFICATION=PASS")

        _health(args.live, args.health_url, args.health_attempts, args.health_interval)
        print("DEPLOYMENT=PASS")
        print(f"NEW_CONTAINER_ID={replacement['Id']}")
        print(f"NEW_IMAGE_ID={replacement['Image']}")
        print(f"SOURCE_REVISION={args.source_revision}")
        return 0
    except Exception as error:
        print(f"DEPLOYMENT=FAIL ERROR={type(error).__name__}")
        subprocess.run(
            ["docker", "rm", "-f", args.live],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if old_renamed:
            subprocess.run(
                ["docker", "rename", args.rollback, args.live],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ["docker", "start", args.live],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            print("ROLLBACK=ATTEMPTED")
        raise


if __name__ == "__main__":
    sys.exit(main())
