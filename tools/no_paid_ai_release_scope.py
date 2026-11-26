"""Pure no-paid-AI configuration projection for existing release controls.

This module has no Docker invocation, authentication, file mutation, or
production authority. The first policy transition requires an exact governed
transaction whose rollback is also non-metered.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import PurePosixPath
from typing import Any, Mapping

TARGETS = frozenset(("jason-runtime", "jason-mcp-pilot", "jason-pmv4-ticket-core"))
FLAGS = ("JASON_HOSTED_CONVERSATION_ENABLED", "JASON_HOSTED_SEMANTICS_ENABLED")
CREDENTIAL_MOUNTS = frozenset((
    "/run/jason-secrets/openbao/openai/role_id",
    "/run/jason-secrets/openbao/openai/secret_id",
))
ROLE_PATHS = {
    "JASON_OPENAI_OPENBAO_ROLE_ID_PATH": "/run/jason-secrets/openbao/openai/role_id",
    "JASON_OPENAI_OPENBAO_SECRET_ID_PATH": "/run/jason-secrets/openbao/openai/secret_id",
}
RAW_CREDENTIALS = frozenset(("OPENAI_API_KEY", "JASON_OPENAI_API_KEY",
                             "OPENAI_API_TOKEN", "JASON_OPENAI_API_TOKEN"))


class NoPaidAIDenied(PermissionError):
    pass


def _need(value: bool, reason: str) -> None:
    if not value:
        raise NoPaidAIDenied("NO_PAID_AI_" + reason)


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _hash(value: Any) -> str:
    return sha256(_canon(value)).hexdigest()


def environment(container: Mapping[str, Any]) -> dict[str, str]:
    config = container.get("Config")
    _need(isinstance(config, Mapping) and isinstance(config.get("Env"), list),
          "CONTAINER_CONFIG_INVALID")
    env = {}
    for item in config["Env"]:
        _need(isinstance(item, str) and "=" in item, "ENV_INVALID")
        key, value = item.split("=", 1)
        _need(bool(key) and key not in env, "ENV_DUPLICATE_OR_INVALID")
        env[key] = value
    return env


def project_environment(env: Mapping[str, str]) -> dict[str, str]:
    _need(not any(env.get(k) for k in RAW_CREDENTIALS), "RAW_CREDENTIAL_PRESENT")
    result = dict(env)
    for key in FLAGS:
        result[key] = "false"
    # Do not inherit an alternate credential path from old configuration.
    # The fixed paths are deliberately absent from the successor mounts.
    result.update(ROLE_PATHS)
    return result


def _intersects_paid_path(destination: str) -> bool:
    _need(isinstance(destination, str) and destination.startswith("/")
          and str(PurePosixPath(destination)) == destination
          and ".." not in PurePosixPath(destination).parts, "MOUNT_DESTINATION_INVALID")
    d = PurePosixPath(destination)
    return any(d == PurePosixPath(p) or d in PurePosixPath(p).parents
               or PurePosixPath(p) in d.parents for p in CREDENTIAL_MOUNTS)


def project_mounts(mounts: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    _need(isinstance(mounts, list), "MOUNTS_INVALID")
    result = []
    seen = set()
    for row in mounts:
        _need(isinstance(row, Mapping), "MOUNT_INVALID")
        dest = row.get("Destination")
        _need(isinstance(dest, str) and dest not in seen, "MOUNT_DUPLICATE_OR_INVALID")
        seen.add(dest)
        if _intersects_paid_path(dest):
            _need(dest in CREDENTIAL_MOUNTS and row.get("Type") == "bind"
                  and row.get("RW") is False, "PAID_CREDENTIAL_MOUNT_SCOPE_INVALID")
            continue
        result.append(dict(row))
    return result


def project_host_config(host: Mapping[str, Any], effective_mounts: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Project both Docker's configured and effective mount inventories.

    A host config containing the old credential mount must never be mistaken
    for a safe rollback spec. Current native services use structured Mounts;
    ambiguous legacy Binds and VolumesFrom are denied, not reinterpreted.
    """
    from copy import deepcopy
    _need(isinstance(host, Mapping), "HOST_CONFIG_INVALID")
    _need(not host.get("Binds") and not host.get("VolumesFrom"), "LEGACY_MOUNT_SHAPE_DENIED")
    result = deepcopy(dict(host))
    configured = host.get("Mounts")
    _need(isinstance(configured, list), "CONFIGURED_MOUNTS_REQUIRED")
    effective_paid = {x["Destination"] for x in effective_mounts
                      if _intersects_paid_path(x["Destination"])}
    removed = set()
    remaining = []
    seen = set()
    for mount in configured:
        _need(isinstance(mount, Mapping), "CONFIGURED_MOUNT_INVALID")
        target = mount.get("Target")
        _need(isinstance(target, str) and target not in seen, "CONFIGURED_MOUNT_DUPLICATE")
        seen.add(target)
        if _intersects_paid_path(target):
            _need(target in CREDENTIAL_MOUNTS and mount.get("Type") == "bind"
                  and mount.get("ReadOnly") is True, "CONFIGURED_PAID_MOUNT_INVALID")
            removed.add(target)
        else:
            remaining.append(deepcopy(dict(mount)))
    _need(removed == effective_paid, "CONFIGURED_EFFECTIVE_PAID_MOUNT_MISMATCH")
    result["Mounts"] = remaining
    return result


def validate_no_paid_container(container: Mapping[str, Any]) -> None:
    env = environment(container)
    _need(all(env.get(k) == "false" for k in FLAGS), "HOSTED_FLAGS_ENABLED_OR_MISSING")
    _need(all(env.get(k, v) == v for k, v in ROLE_PATHS.items()), "ALTERNATE_CREDENTIAL_PATH")
    _need(not any(env.get(k) for k in RAW_CREDENTIALS), "RAW_CREDENTIAL_PRESENT")
    mounts = container.get("Mounts")
    projected = project_mounts(mounts)
    _need(len(projected) == len(mounts), "PAID_CREDENTIAL_MOUNT_PRESENT")
    _need(project_host_config(container.get("HostConfig"), mounts) == container["HostConfig"],
          "CONFIGURED_PAID_MOUNT_PRESENT")


def project_container(container: Mapping[str, Any]) -> dict[str, Any]:
    """Exact metadata projection, preserving all unrelated inspected fields."""
    from copy import deepcopy
    _need(container.get("Name", "").removeprefix("/") in TARGETS, "TARGET_DENIED")
    result = deepcopy(dict(container))
    result["Config"]["Env"] = [k + "=" + v for k, v in
                               project_environment(environment(container)).items()]
    result["Mounts"] = project_mounts(container.get("Mounts"))
    result["HostConfig"] = project_host_config(container.get("HostConfig"), container["Mounts"])
    validate_no_paid_container(result)
    return result


def release_evidence(container: Mapping[str, Any]) -> dict[str, Any]:
    """No raw environment values, mount sources, or credentials in evidence."""
    projected = project_container(container)
    env = environment(container)
    after = environment(projected)
    removed = sorted(set(x["Destination"] for x in container["Mounts"])
                     - set(x["Destination"] for x in projected["Mounts"]))
    _need(set(removed).issubset(CREDENTIAL_MOUNTS), "REMOVAL_SCOPE_EXPANDED")
    changed_keys = sorted(k for k in set(env) | set(after) if env.get(k) != after.get(k))
    _need(set(changed_keys).issubset(set(FLAGS) | set(ROLE_PATHS)), "ENV_SCOPE_EXPANDED")
    return {
        "component": container["Name"].removeprefix("/"),
        "container_id": container["Id"],
        "image_id": container["Image"],
        "source_revision": env.get("JASON_SOURCE_REVISION"),
        "started_at": container.get("State", {}).get("StartedAt"),
        "changed_environment_keys": changed_keys,
        "removed_credential_destinations": removed,
        "before_environment_sha256": _hash(env),
        "after_environment_sha256": _hash(after),
        "before_mounts_sha256": _hash(container["Mounts"]),
        "after_mounts_sha256": _hash(projected["Mounts"]),
        "before_host_config_sha256": _hash(container["HostConfig"]),
        "after_host_config_sha256": _hash(projected["HostConfig"]),
        "unchanged_non_mount_host_config_sha256": _hash({
            k:v for k,v in container["HostConfig"].items() if k != "Mounts"}),
        "unrelated_host_config_preserved": all(
            v == projected["HostConfig"].get(k)
            for k,v in container["HostConfig"].items() if k != "Mounts"),
        "unchanged_command_sha256": _hash(container["Config"].get("Cmd")),
        "candidate_no_paid_flags": {k: after[k] for k in FLAGS},
        "rollback_requires_same_no_paid_projection": True,
        "production_mutations": False,
    }
