#!/usr/bin/env python3
"""Fail-closed replacement of a live Docker container while preserving its runtime shape."""
from __future__ import annotations

import argparse
import json
import os
import re
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


def _optional_image_id(image: str) -> str | None:
    completed = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _snapshot_image_aliases(tags: list[str]) -> dict[str, str | None]:
    return {tag: _optional_image_id(tag) for tag in tags}


def _promote_image_aliases(
    *,
    candidate_id: str,
    previous_live_image_id: str,
    promote_tags: list[str],
    rollback_tag: str | None,
) -> None:
    if rollback_tag and previous_live_image_id != candidate_id:
        _run(["docker", "tag", previous_live_image_id, rollback_tag], quiet=True)
    for tag in promote_tags:
        _run(["docker", "tag", candidate_id, tag], quiet=True)

    for tag in promote_tags:
        if _image_id(tag) != candidate_id:
            raise RuntimeError(f"promoted image alias mismatch: {tag}")
    if rollback_tag and previous_live_image_id != candidate_id:
        if _image_id(rollback_tag) != previous_live_image_id:
            raise RuntimeError(f"rollback image alias mismatch: {rollback_tag}")


def _restore_image_aliases(snapshot: dict[str, str | None]) -> None:
    for tag, image_id in snapshot.items():
        if image_id:
            subprocess.run(
                ["docker", "tag", image_id, tag],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            subprocess.run(
                ["docker", "image", "rm", tag],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


def _container_exists(name: str) -> bool:
    return subprocess.run(
        ["docker", "inspect", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _parse_env_assignment(value: str) -> tuple[str, str]:
    key, separator, assigned = value.partition("=")
    if not separator or not _ENV_NAME.fullmatch(key):
        raise ValueError("set-env must use NAME=VALUE with an uppercase environment name")
    if key == "JASON_SOURCE_REVISION":
        raise ValueError("JASON_SOURCE_REVISION is controlled by --source-revision")
    return key, assigned


def _docker_bind_source_exists(*, source: str, image: str) -> bool:
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "0:0",
            "--entrypoint",
            "python",
            "--mount",
            f"type=bind,src={source},dst=/jason-bind-probe,readonly",
            image,
            "-c",
            "import os,sys; sys.exit(0 if os.path.exists('/jason-bind-probe') else 1)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _parse_readonly_bind(
    value: str,
    *,
    probe_image: str | None = None,
) -> tuple[str, str]:
    source, separator, destination = value.partition(":")
    if not separator or not os.path.isabs(source) or not os.path.isabs(destination):
        raise ValueError("add-readonly-bind must use absolute SOURCE:DESTINATION paths")
    if not os.path.exists(source):
        if probe_image is None or not _docker_bind_source_exists(
            source=source,
            image=probe_image,
        ):
            raise ValueError(f"read-only bind source does not exist: {source}")
    return source, destination


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


def _build_create_command(
    *,
    live: str,
    image: str,
    source_revision: str,
    harden: bool,
    set_env: tuple[str, ...] = (),
    additional_readonly_binds: tuple[str, ...] = (),
):
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

    for assignment in set_env:
        key, value = _parse_env_assignment(assignment)
        env_map[key] = value
        if key not in env_keys:
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

    existing_mounts: dict[str, tuple[str, bool]] = {}
    for mount in src.get("Mounts") or []:
        mount_type = mount.get("Type")
        if mount_type not in {"bind", "volume"}:
            raise RuntimeError(f"unsupported mount type for exact clone: {mount_type}")
        source = str(mount["Source"])
        destination = str(mount["Destination"])
        writable = bool(mount.get("RW", False))
        existing_mounts[destination] = (source, writable)
        spec = f"type={mount_type},src={source},dst={destination}"
        if not writable:
            spec += ",readonly"
        args += ["--mount", spec]

    additional_destinations: set[str] = set()
    for raw_bind in additional_readonly_binds:
        source, destination = _parse_readonly_bind(
            raw_bind,
            probe_image=image,
        )
        if destination in additional_destinations:
            raise ValueError(f"duplicate additional bind destination: {destination}")
        additional_destinations.add(destination)
        existing = existing_mounts.get(destination)
        if existing is not None:
            existing_source, existing_writable = existing
            if existing_source == source and existing_writable is False:
                continue
            raise ValueError(
                f"additional bind conflicts with existing mount destination: {destination}"
            )
        args += [
            "--mount",
            f"type=bind,src={source},dst={destination},readonly",
        ]

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
    parser.add_argument(
        "--set-env",
        action="append",
        default=[],
        help="Set or add one non-secret container environment entry as NAME=VALUE.",
    )
    parser.add_argument(
        "--add-readonly-bind",
        action="append",
        default=[],
        help="Add one read-only bind mount as absolute SOURCE:DESTINATION.",
    )
    parser.add_argument(
        "--promote-image-tag",
        action="append",
        default=[],
        help="Canonical image tag to retarget to the verified candidate after health checks. May be repeated.",
    )
    parser.add_argument(
        "--rollback-image-tag",
        help="Image tag to retarget to the actual pre-deployment live image after successful verification.",
    )
    args = parser.parse_args()

    promote_tags = list(dict.fromkeys(tag.strip() for tag in args.promote_image_tag if tag.strip()))
    rollback_image_tag = str(args.rollback_image_tag or "").strip() or None
    if rollback_image_tag and not promote_tags:
        parser.error("--rollback-image-tag requires at least one --promote-image-tag")
    if rollback_image_tag and rollback_image_tag in promote_tags:
        parser.error("rollback image tag must be distinct from promoted image tags")
    alias_tags = list(promote_tags)
    if rollback_image_tag:
        alias_tags.append(rollback_image_tag)
    alias_snapshot = _snapshot_image_aliases(alias_tags)

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
        set_env=tuple(args.set_env),
        additional_readonly_binds=tuple(args.add_readonly_bind),
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
    print(f"SET_ENV_COUNT={len(args.set_env)}")
    print(f"ADDITIONAL_READONLY_BIND_COUNT={len(args.add_readonly_bind)}")
    print(f"PROMOTE_IMAGE_TAG_COUNT={len(promote_tags)}")
    print(f"ROLLBACK_IMAGE_TAG={rollback_image_tag or ''}")
    if args.preflight:
        return 0

    old_renamed = False
    aliases_mutated = False
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
        if promote_tags:
            aliases_mutated = True
            _promote_image_aliases(
                candidate_id=candidate_id,
                previous_live_image_id=source["Image"],
                promote_tags=promote_tags,
                rollback_tag=rollback_image_tag,
            )
            print("IMAGE_ALIAS_PROMOTION=PASS")
        print("DEPLOYMENT=PASS")
        print(f"NEW_CONTAINER_ID={replacement['Id']}")
        print(f"NEW_IMAGE_ID={replacement['Image']}")
        print(f"SOURCE_REVISION={args.source_revision}")
        return 0
    except Exception as error:
        print(f"DEPLOYMENT=FAIL ERROR={type(error).__name__}")
        if aliases_mutated:
            _restore_image_aliases(alias_snapshot)
            print("IMAGE_ALIAS_ROLLBACK=ATTEMPTED")
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
