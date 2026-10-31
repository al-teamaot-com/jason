from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    name: str
    enabled: bool
    max_concurrency: int
    max_attempts: int
    retry_delay_seconds: int
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComponentConfig:
    name: str
    owner: str
    interval_seconds: int
    timeout_seconds: int
    max_attempts: int
    retry_delay_seconds: int
    blocked_recheck_seconds: int
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PMV2Config:
    schema_version: str
    instance_id: str
    poll_interval_seconds: int
    lease_seconds: int
    max_concurrent_jobs: int
    database_path: Path
    roadmap_path: Path
    support_path: Path
    legacy_spool: Path
    release_state: Path
    workers: tuple[WorkerConfig, ...]
    components: tuple[ComponentConfig, ...]
    max_concurrent_components: int
    required_status_fields: tuple[str, ...]
    approval_channel: str
    snapshot_directory: Path
    snapshot_interval_seconds: int
    owned_todo_ids: tuple[str, ...]
    status_snapshot_path: Path
    control_request_inbox: Path
    control_result_directory: Path


def _positive_int(value: Any, field: str, maximum: int | None = None) -> int:
    if type(value) is not int or value <= 0:
        raise ConfigError(f"{field} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{field} exceeds safe maximum {maximum}")
    return value


def load_config(path: Path, repo: Path) -> PMV2Config:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("configuration root must be an object")
    if raw.get("schema_version") != "1.0":
        raise ConfigError("unsupported PM V2 configuration schema")
    instance_id = str(raw.get("instance_id") or "").strip()
    if not instance_id:
        raise ConfigError("instance_id must be non-empty")

    poll = _positive_int(raw.get("poll_interval_seconds"), "poll_interval_seconds", 3600)
    lease = _positive_int(raw.get("lease_seconds"), "lease_seconds", 86400)
    max_jobs = _positive_int(raw.get("max_concurrent_jobs"), "max_concurrent_jobs", 64)

    state = raw.get("state")
    sources = raw.get("sources")
    paths = raw.get("paths")
    comms = raw.get("communications")
    worker_map = raw.get("workers")
    component_map = raw.get("components")
    recovery = raw.get("recovery")
    ownership = raw.get("ownership")
    control = raw.get("control")
    if not all(isinstance(x, dict) for x in (
        state, sources, paths, comms, worker_map, component_map,
        recovery, ownership, control
    )):
        raise ConfigError(
            "state, sources, paths, communications, workers, components, recovery, ownership and control must be objects"
        )

    db = Path(str(state.get("database_path") or ""))
    if not db.is_absolute():
        raise ConfigError("database_path must be absolute")
    roadmap = repo / str(sources.get("roadmap_path") or "")
    support = repo / str(sources.get("support_path") or "")
    legacy_spool = Path(str(paths.get("legacy_spool") or ""))
    release_state = Path(str(paths.get("release_state") or ""))
    if not legacy_spool.is_absolute() or not release_state.is_absolute():
        raise ConfigError("legacy_spool and release_state must be absolute")

    workers = []
    for name, item in sorted(worker_map.items()):
        if not isinstance(item, dict):
            raise ConfigError(f"worker {name} must be an object")
        command = item.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(v, str) and v for v in command):
            raise ConfigError(f"worker {name} command must be a non-empty string list")
        workers.append(WorkerConfig(
            name=str(name),
            enabled=bool(item.get("enabled")),
            max_concurrency=_positive_int(item.get("max_concurrency"), f"workers.{name}.max_concurrency", 32),
            max_attempts=_positive_int(item.get("max_attempts"), f"workers.{name}.max_attempts", 10),
            retry_delay_seconds=_positive_int(item.get("retry_delay_seconds"), f"workers.{name}.retry_delay_seconds", 86400),
            command=tuple(command),
        ))

    max_components = _positive_int(
        raw.get("max_concurrent_components"),
        "max_concurrent_components",
        32,
    )
    components = []
    for name, item in sorted(component_map.items()):
        if not isinstance(item, dict):
            raise ConfigError(f"component {name} must be an object")
        owner = str(item.get("owner") or "").strip().casefold()
        if owner not in {"v1", "pm_v2"}:
            raise ConfigError(f"component {name} owner must be v1 or pm_v2")
        command = item.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(v, str) and v for v in command
        ):
            raise ConfigError(f"component {name} command must be a non-empty string list")
        components.append(ComponentConfig(
            name=str(name),
            owner=owner,
            interval_seconds=_positive_int(
                item.get("interval_seconds"), f"components.{name}.interval_seconds", 86400
            ),
            timeout_seconds=_positive_int(
                item.get("timeout_seconds"), f"components.{name}.timeout_seconds", 86400
            ),
            max_attempts=_positive_int(
                item.get("max_attempts"), f"components.{name}.max_attempts", 10
            ),
            retry_delay_seconds=_positive_int(
                item.get("retry_delay_seconds"), f"components.{name}.retry_delay_seconds", 86400
            ),
            blocked_recheck_seconds=_positive_int(
                item.get("blocked_recheck_seconds"),
                f"components.{name}.blocked_recheck_seconds",
                86400,
            ),
            command=tuple(command),
        ))

    fields = comms.get("required_status_fields")
    if not isinstance(fields, list) or len(fields) != 5 or not all(isinstance(v, str) and v.strip() for v in fields):
        raise ConfigError("communications.required_status_fields must contain the five agreed fields")
    approval_channel = str(comms.get("approval_channel") or "")
    if approval_channel != "microsoft_teams":
        raise ConfigError("PM V2 approval_channel must be microsoft_teams")
    snapshot_directory = Path(str(recovery.get("snapshot_directory") or ""))
    if not snapshot_directory.is_absolute():
        raise ConfigError("recovery.snapshot_directory must be absolute")
    snapshot_interval_seconds = _positive_int(
        recovery.get("snapshot_interval_seconds"),
        "recovery.snapshot_interval_seconds",
        86400,
    )
    owned = ownership.get("owned_todo_ids")
    if not isinstance(owned, list) or any(
        not isinstance(value, str) or not value.startswith("TODO-") or not value.strip()
        for value in owned
    ) or len(set(owned)) != len(owned):
        raise ConfigError("ownership.owned_todo_ids must be a unique TODO ID list")

    status_snapshot_path = Path(str(control.get("status_snapshot_path") or ""))
    control_request_inbox = Path(str(control.get("request_inbox") or ""))
    control_result_directory = Path(str(control.get("result_directory") or ""))
    if not all(path.is_absolute() for path in (
        status_snapshot_path, control_request_inbox, control_result_directory
    )):
        raise ConfigError("PM V2 control paths must be absolute")

    return PMV2Config(
        schema_version="1.0",
        instance_id=instance_id,
        poll_interval_seconds=poll,
        lease_seconds=lease,
        max_concurrent_jobs=max_jobs,
        database_path=db,
        roadmap_path=roadmap,
        support_path=support,
        legacy_spool=legacy_spool,
        release_state=release_state,
        workers=tuple(workers),
        components=tuple(components),
        max_concurrent_components=max_components,
        required_status_fields=tuple(fields),
        approval_channel=approval_channel,
        snapshot_directory=snapshot_directory,
        snapshot_interval_seconds=snapshot_interval_seconds,
        owned_todo_ids=tuple(owned),
        status_snapshot_path=status_snapshot_path,
        control_request_inbox=control_request_inbox,
        control_result_directory=control_result_directory,
    )
