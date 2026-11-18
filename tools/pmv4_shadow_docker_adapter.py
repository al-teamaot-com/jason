#!/usr/bin/env python3
"""Explicitly scoped Docker adapter for a separately governed PMv4 shadow host.

This module is never started by the development PR. Only an exact-Owner-signed
ShadowController may call it, and only after source, digest, CI and root policy
verification. It cannot manage ordinary Jason production containers.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from typing import Any, Callable, Mapping

if __package__:
    from .pmv4_shadow_release import (
        EMPTY_BASELINE, ShadowReleaseDenied, PRODUCTION_ROOT, read_json,
    )
else:
    from pmv4_shadow_release import (
        EMPTY_BASELINE, ShadowReleaseDenied, PRODUCTION_ROOT, read_json,
    )

IMAGE = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
SHADOW_NAME = "jason-pmv4-shadow-gateway"
SHADOW_PROJECT = "jason-pmv4-shadow"
SERVICE = "pmv4-shadow-gateway"


class DockerShadowAdapter:
    def __init__(
        self, *,
        root: Path = PRODUCTION_ROOT,
        core_continuity_probe: Callable[[], bool],
        runner: Callable[..., Any] = subprocess.run,
        production: bool = True,
        health_wait_seconds: float = 210,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.root = Path(root)
        if production and self.root != PRODUCTION_ROOT:
            raise ShadowReleaseDenied("SHADOW_ADAPTER_ROOT_NOT_PINNED")
        self.compose_file = self.root / "control" / "docker-compose.yml"
        self.token_file = self.root / "control" / "gateway-token"
        self.core_continuity_probe = core_continuity_probe
        self.runner = runner
        self.production = production
        if (not isinstance(health_wait_seconds, (int, float))
            or isinstance(health_wait_seconds, bool)
            or not 0 <= health_wait_seconds <= 300
            or not callable(clock) or not callable(sleeper)):
            raise ShadowReleaseDenied("SHADOW_HEALTH_WAIT_INVALID")
        self.health_wait_seconds = float(health_wait_seconds)
        self.clock = clock
        self.sleeper = sleeper
        if not callable(core_continuity_probe):
            raise ShadowReleaseDenied("SHADOW_CORE_CONTINUITY_PROBE_REQUIRED")

    def _exec(self, args: list[str], *, env: Mapping[str, str] | None = None) -> Any:
        if not args or args[0] != "/usr/bin/docker":
            raise ShadowReleaseDenied("SHADOW_DOCKER_EXECUTION_SCOPE_INVALID")
        try:
            result = self.runner(args, shell=False, check=False,
                                 capture_output=True, text=True,
                                 timeout=60, env=dict(env) if env else None)
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as exc:
            raise ShadowReleaseDenied("SHADOW_DOCKER_COMMAND_UNAVAILABLE") from exc
        if result.returncode != 0:
            # Do not leak CLI stderr, which can contain environment metadata.
            raise ShadowReleaseDenied("SHADOW_DOCKER_COMMAND_FAILED")
        return result

    def _inspect(self) -> dict[str, Any] | None:
        # A missing container is valid only before first bootstrap.
        cmd = ["/usr/bin/docker", "inspect", SHADOW_NAME]
        try:
            result = self.runner(cmd, shell=False, check=False,
                                 capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as exc:
            raise ShadowReleaseDenied("SHADOW_INSPECT_UNAVAILABLE") from exc
        if result.returncode != 0:
            # Docker 29.6 emits lowercase "error: no such object: ..." and
            # sometimes stdout="[]". Older Docker emits the capitalized form.
            # Accept ONLY an exact missing *this* named container diagnostic:
            # daemon outage, permission failure and arbitrary CLI errors still
            # fail closed, never masquerading as an empty release baseline.
            absent = {"Error: No such object: " + SHADOW_NAME,
                      "error: no such object: " + SHADOW_NAME}
            if (result.returncode == 1
                and isinstance(result.stderr, str)
                and result.stderr.rstrip("\n") in absent
                and result.stderr in (result.stderr.rstrip("\n"),
                                      result.stderr.rstrip("\n") + "\n")
                and result.stdout in ("", "[]", "[]\n")):
                return None
            raise ShadowReleaseDenied("SHADOW_INSPECT_UNAVAILABLE")
        try:
            data = json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise ShadowReleaseDenied("SHADOW_INSPECT_INVALID") from exc
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise ShadowReleaseDenied("SHADOW_INSPECT_INVALID")
        return data[0]

    @staticmethod
    def _check_container_ownership(data: Mapping[str, Any]) -> None:
        config = data.get("Config")
        host = data.get("HostConfig")
        if not isinstance(config, dict) or not isinstance(host, dict):
            raise ShadowReleaseDenied("SHADOW_CONTAINER_CONFIG_MISSING")
        labels = config.get("Labels")
        ports = host.get("PortBindings")
        if (not isinstance(labels, dict)
            or labels.get("com.aot.jason.component") != "pmv4-shadow"
            or labels.get("com.docker.compose.project") != SHADOW_PROJECT
            or labels.get("com.docker.compose.service") != SERVICE
            or host.get("NetworkMode") != "none"
            or host.get("ReadonlyRootfs") is not True
            or host.get("Privileged") is not False
            or (ports is not None and ports != {})):
            raise ShadowReleaseDenied("SHADOW_CONTAINER_OWNERSHIP_OR_ISOLATION_INVALID")
        mounts = data.get("Mounts")
        if not isinstance(mounts, list):
            raise ShadowReleaseDenied("SHADOW_MOUNTS_UNKNOWN")
        # Docker Compose source review is necessary but cannot prove the
        # *actual* running container has the same isolation. Independently
        # read back the immutable container security boundaries after start,
        # including restrictions previously checked only in the YAML file.
        caps = host.get("CapDrop")
        additions = host.get("CapAdd")
        security = host.get("SecurityOpt")
        restart = host.get("RestartPolicy")
        user = config.get("User")
        if (
            user != "1000:1000"
            or not isinstance(caps, list) or "ALL" not in caps
            or additions not in (None, [])
            or not isinstance(security, list)
            or "no-new-privileges:true" not in security
            or host.get("Init") is not True
            or not isinstance(restart, dict)
            or restart.get("Name") not in ("no", "")
            or host.get("PidsLimit") != 256
            or host.get("Memory") != 2 * 1024 * 1024 * 1024
            or host.get("NanoCpus") != 1_000_000_000
            or host.get("PublishAllPorts") not in (None, False)
            or host.get("Devices") not in (None, [])
            # Docker 29/Compose represents an approved named volume in
            # HostConfig.Binds as well as in Mounts. Permit ONLY that exact
            # reserved volume syntax, never arbitrary host-path binds.
            or host.get("Binds") not in (
                None, [], ["jason-pmv4-shadow-state:/home/node/.openclaw:rw"],
            )
        ):
            raise ShadowReleaseDenied("SHADOW_RUNTIME_SECURITY_PROFILE_DRIFT")
        # The reserved volume is the only persistent mount; a private tmpfs
        # at /tmp is optional (Docker inspect may represent it separately).
        actual_volumes = 0
        for mount in mounts:
            if not isinstance(mount, dict):
                raise ShadowReleaseDenied("SHADOW_UNAPPROVED_HOST_MOUNT")
            if mount.get("Destination") == "/home/node/.openclaw":
                if (mount.get("Type") != "volume"
                    or mount.get("Name") != "jason-pmv4-shadow-state"):
                    raise ShadowReleaseDenied("SHADOW_UNAPPROVED_HOST_MOUNT")
                actual_volumes += 1
            elif mount.get("Destination") == "/tmp":
                if mount.get("Type") != "tmpfs":
                    raise ShadowReleaseDenied("SHADOW_UNAPPROVED_HOST_MOUNT")
            else:
                raise ShadowReleaseDenied("SHADOW_UNAPPROVED_HOST_MOUNT")
        if actual_volumes != 1:
            raise ShadowReleaseDenied("SHADOW_UNAPPROVED_HOST_MOUNT")
        # The isolated shadow must never inherit separately billed AI keys
        # or production provider credentials through the image environment.
        env = config.get("Env")
        if not isinstance(env, list):
            raise ShadowReleaseDenied("SHADOW_CONTAINER_ENV_UNVERIFIED")
        denied_keys = (
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY",
            "GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            "DATTO_API_KEY", "AUTOTASK_API_KEY",
        )
        if any(
            not isinstance(entry, str)
            or any(entry.startswith(key + "=") for key in denied_keys)
            for entry in env
        ):
            raise ShadowReleaseDenied("SHADOW_PROHIBITED_PROVIDER_CREDENTIAL_ENV")

    def _owned_or_absent(self) -> dict[str, Any] | None:
        existing = self._inspect()
        if existing is not None:
            self._check_container_ownership(existing)
        return existing

    def _token(self) -> str:
        if self.compose_file.is_symlink() or not self.compose_file.is_file():
            raise ShadowReleaseDenied("SHADOW_COMPOSE_NOT_PROVISIONED")
        if self.token_file.is_symlink() or not self.token_file.is_file():
            raise ShadowReleaseDenied("SHADOW_TOKEN_NOT_PROVISIONED")
        if self.production:
            for item in (self.compose_file, self.token_file):
                metadata = item.lstat()
                if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
                    raise ShadowReleaseDenied("SHADOW_CONTROL_FILE_UNTRUSTED")
        mode = stat.S_IMODE(self.token_file.stat().st_mode)
        if mode != 0o400 and mode != 0o600:
            raise ShadowReleaseDenied("SHADOW_TOKEN_FILE_PERMISSIONS_INVALID")
        token = self.token_file.read_text().strip()
        if len(token) < 32 or len(token) > 128:
            raise ShadowReleaseDenied("SHADOW_TOKEN_INVALID")
        return token

    def _candidate_compose(self, release_dir: Path) -> Path:
        """Select only the exact SHA-bound, root-staged immutable Compose.

        Root A0 control Compose is an older protected baseline and must not
        silently override a newly reviewed A1 resource profile. Never edit
        or substitute that A0 file as an engineering shortcut.
        """
        manifest = read_json(release_dir / "release-manifest.json")
        expected = manifest.get("compose_sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ShadowReleaseDenied("SHADOW_COMPOSE_SOURCE_HASH_NOT_PINNED")
        candidate = release_dir / "bundle" / "config" / "pmv4-shadow" / "docker-compose.yml"
        if (release_dir.is_symlink() or candidate.is_symlink()
            or not candidate.is_file()):
            raise ShadowReleaseDenied("SHADOW_IMMUTABLE_COMPOSE_UNAVAILABLE")
        meta = candidate.lstat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
            raise ShadowReleaseDenied("SHADOW_IMMUTABLE_COMPOSE_INODE_UNTRUSTED")
        if self.production and (meta.st_uid != 0 or meta.st_gid != 0
                                or stat.S_IMODE(meta.st_mode) != 0o400):
            raise ShadowReleaseDenied("SHADOW_IMMUTABLE_COMPOSE_ROOT_TRUST_MISSING")
        blob = candidate.read_bytes()
        if len(blob) > 128000 or sha256(blob).hexdigest() != expected:
            raise ShadowReleaseDenied("SHADOW_IMMUTABLE_COMPOSE_HASH_MISMATCH")
        return candidate

    def _manifest_image(self, release_dir: Path) -> str:
        doc = read_json(release_dir / "release-manifest.json")
        image = doc.get("image_digest")
        if not isinstance(image, str) or not IMAGE.fullmatch(image):
            raise ShadowReleaseDenied("SHADOW_IMAGE_NOT_PINNED")
        return image

    def _up(self, release_dir: Path) -> None:
        image = self._manifest_image(release_dir)
        compose = self._candidate_compose(release_dir)
        token = self._token()
        self._owned_or_absent()
        # Digest is a local OCI image ID and --pull never prohibits egress.
        self._exec(["/usr/bin/docker", "image", "inspect", image])
        env = {"PATH": "/usr/bin:/bin", "PMV4_SHADOW_IMAGE_SHA": image,
               "PMV4_SHADOW_GATEWAY_TOKEN": token}
        self._exec(
            ["/usr/bin/docker", "compose", "--project-name", SHADOW_PROJECT,
             "-f", str(compose),
             "up", "--detach", "--no-build", "--no-deps", "--pull", "never"],
            env=env,
        )
        self._owned_or_absent()

    def activate_shadow(self, release_dir: Path) -> None:
        self._up(release_dir)

    def restore_shadow(self, previous_dir: Path) -> None:
        if previous_dir.name == EMPTY_BASELINE:
            if read_json(previous_dir / "baseline.json") != {
                "schema_version": "1.0", "service": "jason-pmv4-shadow",
                "baseline": "no_prior_shadow_runtime",
            }:
                raise ShadowReleaseDenied("SHADOW_EMPTY_BASELINE_INVALID")
            if self._owned_or_absent() is not None:
                # No "--volumes", no host network, no other project touched.
                self._exec([
                    "/usr/bin/docker", "compose", "--project-name", SHADOW_PROJECT,
                    "-f", str(self.compose_file), "down",
                ], env={"PATH": "/usr/bin:/bin",
                        "PMV4_SHADOW_IMAGE_SHA": "sha256:" + "0"*64,
                        "PMV4_SHADOW_GATEWAY_TOKEN": self._token()})
            return
        self._up(previous_dir)

    def verify_shadow_and_core(self, candidate_dir: Path) -> bool:
        # Compose up --detach completes *before* a healthy probe. Wait only for
        # the isolated shadow, for a bounded period, and never restart or
        # change any service to make the test pass. Wrong identity fails fast.
        image = self._manifest_image(candidate_dir)
        deadline = self.clock() + self.health_wait_seconds
        while True:
            info = self._owned_or_absent()
            if info is None or info.get("Image") != image:
                return False
            state = info.get("State")
            if not isinstance(state, dict) or state.get("Running") is not True:
                return False
            health = state.get("Health")
            if not isinstance(health, dict):
                return False
            status = health.get("Status")
            if status == "healthy":
                # No fallback to self-reported PASS. Trusted installer must
                # connect independent fresh ticket Core verification.
                return self.core_continuity_probe() is True
            if status != "starting":
                return False
            if self.clock() >= deadline:
                return False
            self.sleeper(min(2.0, max(0, deadline - self.clock())))


if __name__ == "__main__":
    raise SystemExit("Library only: production installation and authorization required.")
