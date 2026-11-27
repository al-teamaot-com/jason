#!/usr/bin/env python3
"""Root-published, exact component LKG readback for the existing PMV4 controls.

The legacy host LKG is NOT replaced with a fabricated common source SHA.
This read-only module validates independently root-owned component state and
actual Docker observations. It never grants deployment or provider authority.
"""
from __future__ import annotations
import hashlib
import sys
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping

READBACK = Path("/etc/jason-owner-release/coordinated-component-readback.json")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
NORMAL_POLICY = Path("/etc/jason-owner-release/normal-release-policy/production-freeze-retirement.json")
HOST_CURRENT = Path("/opt/jason/current")
COMPONENTS = ("jason-runtime", "jason-mcp-pilot", "jason-teams-gateway")
SHA = re.compile(r"[0-9a-f]{40}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
FIELDS = frozenset(("schema_version", "status", "host_revision", "release_id",
                    "manifest_sha256", "scope_sha256", "freeze_sha256", "components"))
NORMAL_FIELDS = (FIELDS - {"freeze_sha256"}) | {"release_policy_sha256"}
ROW = frozenset(("revision", "image_id", "container_id"))


class ComponentReadbackDenied(PermissionError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ComponentReadbackDenied("COORDINATED_READBACK_" + code)


def digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def valid(value: Any, expression: re.Pattern) -> bool:
    return isinstance(value, str) and expression.fullmatch(value) is not None


def validate(value: Mapping[str, Any]) -> dict[str, Any]:
    normal = isinstance(value, dict) and value.get("schema_version") == "3.0"
    need(isinstance(value, dict) and set(value) == (NORMAL_FIELDS if normal else FIELDS), "SCHEMA")
    field = "release_policy_sha256" if normal else "freeze_sha256"
    need(value["schema_version"] in ("2.0", "3.0")
         and value["status"] == "verified_component_release"
         and valid(value["host_revision"], SHA)
         and isinstance(value["release_id"], str)
         and re.fullmatch(r"release-[0-9a-f]{16}", value["release_id"]) is not None
         and all(valid(value[k], HEX) for k in
                 ("manifest_sha256", "scope_sha256", field)), "FIELDS")
    components = value["components"]
    need(isinstance(components, dict) and set(components) == set(COMPONENTS), "COMPONENT_SET")
    for row in components.values():
        need(isinstance(row, dict) and set(row) == ROW, "COMPONENT_SCHEMA")
        need(valid(row["revision"], SHA) and valid(row["image_id"], IMAGE)
             and valid(row["container_id"], HEX), "COMPONENT_IDENTITY")
    return dict(value)


def _root_read(path: Path) -> bytes:
    # Reject non-root or writable directories, symlinked paths, foreign files
    # and truncated content. This is root-origin readback, not an operator
    # assertion, and is not a signed approval or a root command interface.
    for ancestor in (path.parent, *path.parent.parents):
        meta = ancestor.lstat()
        need(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0
             and not (meta.st_mode & 0o022), "PARENT_CUSTODY")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(fd)
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0
             and stat.S_IMODE(meta.st_mode) in (0o444, 0o644)
             and meta.st_nlink == 1 and 0 < meta.st_size <= 65536, "FILE_CUSTODY")
        raw = os.read(fd, 65537)
        need(len(raw) == meta.st_size, "FILE_CHANGED")
        return raw
    finally:
        os.close(fd)


def read() -> dict[str, Any] | None:
    # A missing file means legacy operation, not permission to accept mixed
    # live revisions. Any present malformed/untrusted file is a denial.
    if not os.path.lexists(READBACK):
        return None
    try:
        return validate(json.loads(_root_read(READBACK)))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ComponentReadbackDenied("COORDINATED_READBACK_UNTRUSTED") from exc


def observed(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """Reduce inspect evidence to non-secret, exact component identity."""
    result = {}
    need(isinstance(rows, list) and len(rows) == len(COMPONENTS), "INSPECT_COUNT")
    for row in rows:
        name = str(row.get("Name", "")).lstrip("/")
        need(name in COMPONENTS and name not in result, "INSPECT_NAME")
        config, state = row.get("Config") or {}, row.get("State") or {}
        labels = config.get("Labels") or {}
        revision = labels.get("com.teamaot.jason.source_revision")
        need(valid(revision, SHA) and valid(row.get("Id"), HEX)
             and valid(row.get("Image"), IMAGE)
             and state.get("Running") is True and state.get("Status") == "running",
             "LIVE_IDENTITY_OR_STATE")
        health = (state.get("Health") or {}).get("Status", "none")
        need(health in ("none", "healthy")
             and (name != "jason-runtime" or health == "healthy"), "LIVE_HEALTH")
        result[name] = {"revision": revision, "image_id": row["Image"], "container_id": row["Id"]}
    need(set(result) == set(COMPONENTS), "INSPECT_INCOMPLETE")
    return result


def inspect_components() -> dict[str, dict[str, str]]:
    result = subprocess.run(
        ["/usr/bin/docker", "inspect", "--type", "container", *COMPONENTS],
        capture_output=True, check=False, timeout=25,
    )
    need(result.returncode == 0 and len(result.stdout) <= 4 * 1024 * 1024, "INSPECT_FAILED")
    return observed(json.loads(result.stdout))


def verify(value: Mapping[str, Any], actual: Mapping[str, Any], *,
           host_revision: str, freeze_sha256: str | None = None,
           release_policy_sha256: str | None = None) -> dict[str, Any]:
    state = validate(value)
    need(state["host_revision"] == host_revision, "HOST_REVISION_DRIFT")
    if state["schema_version"] == "3.0":
        need(freeze_sha256 is None and valid(release_policy_sha256, HEX)
             and state["release_policy_sha256"] == release_policy_sha256, "NORMAL_POLICY_DRIFT")
    else:
        need(release_policy_sha256 is None and valid(freeze_sha256, HEX)
             and state["freeze_sha256"] == freeze_sha256, "FREEZE_DRIFT")
    need(state["components"] == actual, "COMPONENT_IDENTITY_DRIFT")
    return state


def verify_live() -> dict[str, Any] | None:
    state = read()
    if state is None:
        return None
    need(HOST_CURRENT.is_symlink(), "HOST_POINTER")
    host = HOST_CURRENT.resolve(strict=True)
    need(host.parent == Path("/opt/jason/releases"), "HOST_SOURCE_CUSTODY")
    if state["schema_version"] == "3.0":
        try:
            FREEZE.lstat()
        except FileNotFoundError:
            pass
        else:
            need(False, "NORMAL_POLICY_ACTIVE_FREEZE_CONFLICT")
        raw = _root_read(NORMAL_POLICY)
        return verify(state, inspect_components(), host_revision=host.name,
                      release_policy_sha256=hashlib.sha256(raw).hexdigest())
    try:
        NORMAL_POLICY.lstat()
    except FileNotFoundError:
        pass
    else:
        need(False, "LEGACY_READBACK_AFTER_RETIREMENT")
    fd = os.open(FREEZE, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(fd)
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid == 1000
             and stat.S_IMODE(meta.st_mode) == 0o600 and meta.st_nlink == 1
             and 0 < meta.st_size <= 4096, "FREEZE_CUSTODY")
        raw = os.read(fd, 4097)
        need(len(raw) == meta.st_size, "FREEZE_CHANGED")
    finally:
        os.close(fd)
    return verify(state, inspect_components(), host_revision=host.name,
                  freeze_sha256=hashlib.sha256(raw).hexdigest())


def verify_legacy_anchor(state: Mapping[str, Any], baseline: Mapping[str, Any]) -> None:
    validate(state)
    need(baseline.get("complete") is True
         and baseline.get("revision") == state["host_revision"]
         and baseline.get("host_revision") == state["host_revision"]
         and baseline.get("runtime_revision") == state["host_revision"]
         and baseline.get("mcp_revision") == state["host_revision"],
         "LEGACY_ANCHOR_DRIFT")


def verify_host_fingerprint(legacy: Mapping[str, Any],
                            current: Mapping[str, Any],
                            state: Mapping[str, Any]) -> None:
    """Revalidate the legacy host separately from effective component images.

    The old LKG remains the immutable legacy host rollback anchor. A scoped
    release must not cause root revalidation to pretend the components still
    run that image, or let ordinary legacy promotion consume mixed revisions.
    """
    verify_legacy_anchor(state, legacy)
    need(current.get("complete") is True, "OBSERVATION_INCOMPLETE")
    for key in ("revision", "host_revision", "host_release",
                "release_manager_source_revision", "desired_state_policy_digest",
                "mobile_release_approval_policy_digest", "mobile_release_approval_mode",
                "scheduled_control_units"):
        need(legacy.get(key) is not None and current.get(key) == legacy[key],
             "HOST_FINGERPRINT_DRIFT")
    for component, prefix in (("jason-runtime", "runtime"), ("jason-mcp-pilot", "mcp")):
        row = state["components"][component]
        need(current.get(prefix+"_revision") == row["revision"]
             and current.get(prefix+"_image_id") == row["image_id"], "OBSERVED_IMAGE_DRIFT")
    need(current.get("coordinated_readback_sha256") == digest(state), "OBSERVED_SCOPE_DRIFT")


def capture_native_host() -> dict[str, Any]:
    """Run as the existing unprivileged host observer, never import its code as root."""
    need(os.geteuid() == 1000, "HOST_OBSERVER_IDENTITY")
    state = verify_live()
    need(state is not None, "ACTIVE_SCOPE_MISSING")
    sys.path.insert(0, "/home/al/.local/lib/jason")
    import release_manager_host_runner as runner
    runtime, mcp = runner.live_runtime(), runner.live_mcp()
    revision = state["host_revision"]
    current = HOST_CURRENT.resolve(strict=True)
    manager = Path("/home/al/.local/lib/jason/release-manager-source").resolve(strict=True)
    need(current.name == revision and manager == current, "HOST_MANAGER_ALIGNMENT")
    need(runtime["revision"] == state["components"]["jason-runtime"]["revision"]
         and runtime["image_id"] == state["components"]["jason-runtime"]["image_id"]
         and mcp["revision"] == state["components"]["jason-mcp-pilot"]["revision"]
         and mcp["image_id"] == state["components"]["jason-mcp-pilot"]["image_id"],
         "HOST_OBSERVER_COMPONENT_DRIFT")
    return {
        "schema_version":"1.0", "revision":revision,
        "runtime_revision":runtime["revision"], "runtime_image_id":runtime["image_id"],
        "mcp_revision":mcp["revision"], "mcp_image_id":mcp["image_id"],
        "host_revision":revision, "host_release":str(current),
        "release_manager_source_revision":manager.name,
        "scheduled_control_units":runner.scheduled_control_alignment(),
        "desired_state_policy_digest":runner.file_digest(current/"config/production-desired-state.json"),
        "mobile_release_approval_policy_digest":runner.file_digest(runner.MOBILE_APPROVAL_POLICY),
        "mobile_release_approval_mode":runner.live_release_mobile_approval_mode(runtime),
        "coordinated_readback_sha256":digest(state),
        "drift_evidence_path":"/var/lib/jason/openclaw/release-manager/production-drift.json",
        "complete":True, "observed_at":runner.now(),
    }


def main() -> int:
    """Read-only installed helper; no caller-selected targets or file paths."""
    try:
        need(sys.argv[1:] in ([], ["--capture-native-health"]), "CLI_SCOPE")
        if sys.argv[1:]:
            print(json.dumps(capture_native_host(), sort_keys=True))
        else:
            state = verify_live()
            print(json.dumps({"status": "legacy" if state is None else "verified",
                              "state": state}, sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError):
        print(json.dumps({"status": "denied", "state": None}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
