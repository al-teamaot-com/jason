#!/usr/bin/env python3
"""Root-installed host adapter for independent Compose release transactions.

Not installed in production by this source change. The trusted installer must
copy this module and all dependencies into a root-owned immutable tree, install
a root-owned host policy, and separately verify host locks, source/CI attestor,
and Owner signing trust before making the entrypoint available.

The adapter does NOT access shared runtime secrets or restart PMV3/PMv4.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Callable, Mapping

from tools.independent_component_release import (
    ComponentReleaseDenied, PROTECTED, PMV3_FREEZE, TRUSTED_SOURCE,
    digest, trusted_dir, trusted_file,
)

INSTALLED_ADAPTER = Path(
    "/opt/jason/independent-component-release/trusted/tools/independent_component_host_adapter.py"
)
HOST_POLICY = Path("/etc/jason/independent-component-release/host-profiles.json")
CI_EVIDENCE = Path("/var/lib/jason/independent-component-release/control/protected-ci.json")
ROLE_ROOT = Path("/var/lib/jason/runtime-secrets/openbao")
IMAGE_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
SHA = re.compile(r"^[a-f0-9]{40}$")
FINANCIAL_PATHS = {
    "JASON_FINANCIAL_IMAGE", "JASON_FINANCIAL_CONFIG",
    "JASON_FINANCIAL_BOUNDARY", "JASON_FINANCIAL_ROLE_ID",
    "JASON_FINANCIAL_SECRET_ID", "JASON_FINANCIAL_STATE",
    "JASON_FINANCIAL_NETWORK",
}


class IndependentComponentHost:
    def __init__(
        self, *, production: bool = True,
        runner: Callable[..., Any] = subprocess.run,
        host_guard: Any = None,
        profile_path: Path = HOST_POLICY,
        ci_path: Path = CI_EVIDENCE,
    ) -> None:
        if production and (
            os.geteuid() != 0
            or Path(__file__).resolve() != INSTALLED_ADAPTER
            or Path(profile_path) != HOST_POLICY
            or Path(ci_path) != CI_EVIDENCE
            or host_guard is not None
        ):
            raise ComponentReleaseDenied("COMPONENT_HOST_ROOT_INSTALL_REQUIRED")
        if host_guard is None and production:
            # This dependency must ALSO be installed/pinned as trusted root code.
            from tools.pmv4_host_release_guard import IndependentHostGuard
            host_guard = IndependentHostGuard(production=True)
        if host_guard is None:
            raise ComponentReleaseDenied("COMPONENT_HOST_RELEASE_GUARD_UNAVAILABLE")
        self.production = production
        self.runner = runner
        self.host_guard = host_guard
        self.profile_path = Path(profile_path)
        self.ci_path = Path(ci_path)
        self._profiles = self._load_profiles()

    def _load_profiles(self):
        raw = trusted_file(self.profile_path, production=self.production, max_bytes=32768)
        try:
            p = json.loads(raw)
        except ValueError as exc:
            raise ComponentReleaseDenied("COMPONENT_HOST_PROFILES_INVALID") from exc
        if not isinstance(p, dict) or set(p) != {"schema_version", "components"} or p["schema_version"] != "1.0":
            raise ComponentReleaseDenied("COMPONENT_HOST_PROFILES_INVALID")
        components = p["components"]
        if not isinstance(components, dict) or not components:
            raise ComponentReleaseDenied("COMPONENT_HOST_PROFILES_EMPTY")
        return components

    def _profile(self, component_id: str) -> dict[str, Any]:
        p = self._profiles.get(component_id)
        if not isinstance(p, dict) or set(p) != {
            "project", "service", "network", "role_id_path",
            "secret_id_path", "state_dir",
        }:
            raise ComponentReleaseDenied("COMPONENT_HOST_PROFILE_NOT_APPROVED")
        if component_id != "financial-statements":
            # Other components need a separately reviewed adapter profile.
            raise ComponentReleaseDenied("COMPONENT_HOST_PROFILE_NOT_YET_SUPPORTED")
        if (
            p["project"] != "jason-financial-statements"
            or p["service"] != "financial-statements"
            or p["network"] != "jason-core"
            or p["state_dir"] != "/var/lib/jason/financial-statements"
            or p["role_id_path"] != str(ROLE_ROOT / "microsoft-sharepoint-write-approle/role-id")
            or p["secret_id_path"] != str(ROLE_ROOT / "microsoft-sharepoint-write-approle/secret-id")
        ):
            raise ComponentReleaseDenied("COMPONENT_HOST_PROFILE_SCOPE_INVALID")
        if self.production:
            for key in ("role_id_path", "secret_id_path"):
                path = Path(p[key])
                if path.is_symlink() or not path.is_file():
                    raise ComponentReleaseDenied("COMPONENT_HOST_SECRET_FILE_UNAVAILABLE")
                meta = path.lstat()
                if meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) & 0o007:
                    raise ComponentReleaseDenied("COMPONENT_HOST_SECRET_FILE_UNTRUSTED")
        state = Path(p["state_dir"])
        if self.production:
            if state.is_symlink() or not state.is_dir():
                raise ComponentReleaseDenied("COMPONENT_HOST_STATE_DIRECTORY_MISSING")
            meta = state.lstat()
            if meta.st_uid != 1000 or stat.S_IMODE(meta.st_mode) != 0o700:
                raise ComponentReleaseDenied("COMPONENT_HOST_STATE_DIRECTORY_UNTRUSTED")
        return p

    def _run(self, args: list[str], *, env: Mapping[str, str] | None = None, timeout: int = 30) -> str:
        result = self.runner(
            args, cwd="/", env=dict(env or {"PATH": "/usr/bin:/bin"}),
            capture_output=True, text=True, check=False, timeout=timeout,
        )
        if result.returncode != 0:
            # Do not echo subprocess output: provider paths/credentials may be
            # present in Docker errors. Record failure code only.
            raise ComponentReleaseDenied("COMPONENT_HOST_COMMAND_FAILED:" + str(result.returncode))
        return str(result.stdout)

    def _env(self, bundle: Path, m: Mapping[str, Any]) -> dict[str, str]:
        p = self._profile(str(m["component_id"]))
        if p["project"] != m["compose_project"] or p["service"] != m["compose_service"]:
            raise ComponentReleaseDenied("COMPONENT_HOST_PROJECT_NOT_APPROVED")
        if not IMAGE_RE.fullmatch(str(m["image_digest"])):
            raise ComponentReleaseDenied("COMPONENT_HOST_IMAGE_NOT_IMMUTABLE")
        values = {
            "JASON_FINANCIAL_IMAGE": str(m["image_digest"]),
            "JASON_FINANCIAL_CONFIG": str(bundle / "config.json"),
            "JASON_FINANCIAL_BOUNDARY": str(bundle / "boundary.sqlite3"),
            "JASON_FINANCIAL_ROLE_ID": str(p["role_id_path"]),
            "JASON_FINANCIAL_SECRET_ID": str(p["secret_id_path"]),
            "JASON_FINANCIAL_STATE": str(p["state_dir"]),
            "JASON_FINANCIAL_NETWORK": str(p["network"]),
        }
        if set(values) != FINANCIAL_PATHS:
            raise ComponentReleaseDenied("COMPONENT_HOST_ENV_SCOPE_INVALID")
        return {"PATH": "/usr/bin:/bin", **values}

    def _compose(self, bundle: Path, m: Mapping[str, Any], *, apply: list[str] | None) -> dict[str, Any]:
        env = self._env(bundle, m)
        command = [
            "/usr/bin/docker", "compose", "--project-name", str(m["compose_project"]),
            "--file", str(bundle / "compose.yaml"),
        ]
        parsed = self._run(command + ["config", "--format", "json"], env=env)
        try:
            config = json.loads(parsed)
            services = config["services"]
            if set(services) != {m["compose_service"]}:
                raise ValueError("unexpected Compose services")
            service = services[m["compose_service"]]
            if (
                service.get("image") != m["image_digest"]
                or service.get("read_only") is not True
                or service.get("user") != "1000:1000"
                or service.get("privileged") is True
                or service.get("ports")
                or service.get("build")
                or service.get("depends_on")
            ):
                raise ValueError("unsafe resolved Compose")
            volumes = service["volumes"]
            profile = self._profile(str(m["component_id"]))
            expected = {
                "/etc/jason/financial-statements/config.json": (str(bundle / "config.json"), True),
                "/etc/jason/financial-statements/boundary.sqlite3": (str(bundle / "boundary.sqlite3"), True),
                "/run/jason-financial-secrets/role_id": (str(profile["role_id_path"]), True),
                "/run/jason-financial-secrets/secret_id": (str(profile["secret_id_path"]), True),
                "/var/lib/jason/financial-statements": (str(profile["state_dir"]), False),
            }
            actual = {
                v["target"]: (v["source"], v.get("read_only", False))
                for v in volumes
                if v.get("type") == "bind"
            }
            if actual != expected or len(volumes) != len(expected):
                raise ValueError("resolved mount mismatch")
            network = config.get("networks") or {}
            if len(network) != 1 or not any(
                x.get("external") is True and x.get("name") == "jason-core"
                for x in network.values()
            ):
                raise ValueError("unexpected network")
        except (KeyError, TypeError, ValueError) as exc:
            raise ComponentReleaseDenied("COMPONENT_HOST_COMPOSE_RESOLUTION_DENIED") from exc
        if apply:
            self._run(command + apply + [str(m["compose_service"])], env=env, timeout=120)
        return config

    @contextmanager
    def host_transaction(self):
        with self.host_guard.host_release_transaction():
            if self.host_guard.host_mutation_quiescent() is not True:
                raise ComponentReleaseDenied("COMPONENT_HOST_PROTECTED_GATE_NOT_CLOSED")
            yield

    @contextmanager
    def freeze_transaction(self, expected: str):
        # A signed exact-action Owner approval is the *sole* one-transaction
        # exception. Keep the legacy marker byte-identical, rather than
        # globally unfreezing or writing another standing approval marker.
        raw = trusted_file(
            PMV3_FREEZE if self.production else self.profile_path.parent / "production-deployment-freeze",
            production=self.production, max_bytes=4096,
            allow_owner_write=True, allowed_uid=(1000 if self.production else 0),
        )
        if digest(raw) != expected or json.loads(raw).get("status") != "active":
            raise ComponentReleaseDenied("COMPONENT_HOST_FREEZE_DRIFT")
        try:
            yield
        finally:
            target = PMV3_FREEZE if self.production else self.profile_path.parent / "production-deployment-freeze"
            current = trusted_file(target, production=self.production, max_bytes=4096, allow_owner_write=True, allowed_uid=(1000 if self.production else 0))
            if current != raw:
                raise ComponentReleaseDenied("COMPONENT_HOST_FREEZE_CHANGED")

    def protected(self):
        observed = {}
        for name in PROTECTED:
            raw = self._run(["/usr/bin/docker", "inspect", name])
            try:
                record = json.loads(raw)
                if not isinstance(record, list) or len(record) != 1:
                    raise ValueError("not single")
                c = record[0]
                state = c["State"]
                observed[name] = {
                    "id": c["Id"], "image": c["Image"],
                    "started_at": state["StartedAt"],
                    "running": state["Running"],
                    "health": (state.get("Health") or {}).get("Status", "none"),
                }
            except (ValueError, KeyError, TypeError) as exc:
                raise ComponentReleaseDenied("COMPONENT_HOST_PROTECTED_READBACK_FAILED") from exc
        return observed

    def source_and_ci(self, sha):
        raw = trusted_file(self.ci_path, production=self.production, max_bytes=32768)
        try:
            data = json.loads(raw)
            at = datetime.fromisoformat(data["verified_at"])
            fresh = at.tzinfo is not None and 0 <= (
                datetime.now(timezone.utc) - at
            ).total_seconds() <= 600
            return (
                data.get("candidate_sha") == sha
                and data.get("protected_main_ancestor") is True
                and data.get("required_ci_passed") is True
                and fresh
            )
        except (ValueError, TypeError, KeyError):
            return False

    def image(self, image_id, source_sha):
        raw = self._run(["/usr/bin/docker", "image", "inspect", image_id])
        try:
            data = json.loads(raw)
            image = data[0]
            return (
                len(data) == 1
                and image["Id"] == image_id
                and image["Config"]["Labels"]["com.aot.jason.source_revision"] == source_sha
            )
        except (KeyError, TypeError, IndexError, ValueError):
            return False

    def observe(self, project: str):
        raw = self._run([
            "/usr/bin/docker", "ps", "-a", "--filter",
            "label=com.docker.compose.project=" + project, "--format", "{{.ID}}",
        ])
        ids = [s for s in raw.splitlines() if s.strip()]
        if not ids:
            return None
        if len(ids) != 1:
            raise ComponentReleaseDenied("COMPONENT_HOST_MULTIPLE_CONTAINERS")
        row = json.loads(self._run(["/usr/bin/docker", "inspect", ids[0]]))[0]
        labels = row.get("Config", {}).get("Labels") or {}
        if labels.get("com.docker.compose.project") != project:
            raise ComponentReleaseDenied("COMPONENT_HOST_DOCKER_PROJECT_DRIFT")
        source = row.get("Image")
        if not row.get("State", {}).get("Running"):
            raise ComponentReleaseDenied("COMPONENT_HOST_NOT_RUNNING")
        image = json.loads(self._run(["/usr/bin/docker", "image", "inspect", source]))[0]
        revision = (image.get("Config", {}).get("Labels") or {}).get("com.aot.jason.source_revision")
        if not isinstance(revision, str) or not SHA.fullmatch(revision):
            raise ComponentReleaseDenied("COMPONENT_HOST_UNTRUSTED_IMAGE")
        return revision

    def activate(self, bundle, manifest):
        self._compose(
            bundle, manifest,
            apply=["up", "--detach", "--no-deps", "--no-build", "--force-recreate"],
        )

    def restore(self, previous, manifest):
        if previous is None:
            self._compose(
                Path("/var/lib/jason/independent-component-release/releases") /
                str(manifest["candidate_sha"]),
                manifest, apply=["rm", "--force", "--stop"],
            )
        else:
            old = json.loads(trusted_file(
                previous / "manifest.json", production=self.production,
            ))
            self._compose(
                previous, old,
                apply=["up", "--detach", "--no-deps", "--no-build", "--force-recreate"],
            )

    def verify_component(self, bundle, manifest):
        if bundle is None:
            return self.observe(str(manifest["compose_project"])) is None
        release = json.loads(trusted_file(bundle / "manifest.json", production=self.production))
        return self.observe(str(manifest["compose_project"])) == release["candidate_sha"]
