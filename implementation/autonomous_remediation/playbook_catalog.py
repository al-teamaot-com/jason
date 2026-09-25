"""Durable playbook catalog and autonomy-promotion contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class AutonomyActivation(str, Enum):
    DISABLED = "disabled"
    SHADOW = "shadow"
    AUTONOMOUS = "autonomous"
    SUSPENDED = "suspended"


@dataclass(frozen=True)
class PlaybookCatalogEntry:
    playbook_id: str
    name: str
    version: str
    lifecycle: str
    enabled: bool
    source: str
    autonomy_activation: AutonomyActivation = AutonomyActivation.DISABLED
    required_gates: tuple[str, ...] = ()
    allowed_capabilities: tuple[str, ...] = ()
    autonomy_policy_id: str | None = None
    trigger_title_contains: tuple[str, ...] = ()
    trigger_api_vendor_ids: tuple[int, ...] = ()

    @property
    def standing_authority_active(self) -> bool:
        return (
            self.enabled
            and self.lifecycle in {"pilot", "production"}
            and self.autonomy_activation is AutonomyActivation.AUTONOMOUS
        )

    @property
    def investigation_enabled(self) -> bool:
        return self.enabled and self.autonomy_activation in {
            AutonomyActivation.SHADOW,
            AutonomyActivation.AUTONOMOUS,
        }

    def capability_allowed(self, capability: str) -> bool:
        return self.standing_authority_active and capability in self.allowed_capabilities


class PlaybookCatalog:
    def __init__(self, entries: tuple[PlaybookCatalogEntry, ...]) -> None:
        ids = [entry.playbook_id for entry in entries]
        if len(ids) != len(set(ids)):
            raise ValueError("playbook ids must be unique")
        self._entries = {entry.playbook_id: entry for entry in entries}

    def get(self, playbook_id: str) -> PlaybookCatalogEntry:
        try:
            return self._entries[playbook_id]
        except KeyError as exc:
            raise KeyError(f"unknown playbook: {playbook_id}") from exc

    def list_all(self) -> tuple[PlaybookCatalogEntry, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    @classmethod
    def load(cls, path: str | Path) -> "PlaybookCatalog":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("playbook registry root must be an object")
        schema_version = int(payload.get("schema_version", 1))
        if schema_version not in {1, 2}:
            raise ValueError(f"unsupported playbook registry schema: {schema_version}")
        raw_playbooks = payload.get("playbooks")
        if not isinstance(raw_playbooks, list):
            raise ValueError("playbook registry requires a playbooks array")
        return cls(tuple(cls._entry(item) for item in raw_playbooks))

    @staticmethod
    def _entry(raw: Any) -> PlaybookCatalogEntry:
        if not isinstance(raw, Mapping):
            raise ValueError("playbook entry must be an object")
        autonomy = raw.get("autonomy")
        if not isinstance(autonomy, Mapping):
            autonomy = {}
        trigger = raw.get("trigger")
        if not isinstance(trigger, Mapping):
            trigger = {}
        activation_text = str(autonomy.get("activation") or "disabled").strip().casefold()
        try:
            activation = AutonomyActivation(activation_text)
        except ValueError as exc:
            raise ValueError(f"invalid playbook autonomy activation: {activation_text}") from exc

        api_vendor_ids: list[int] = []
        for value in trigger.get("api_vendor_ids") or ():
            if isinstance(value, bool):
                raise ValueError("api vendor ids must be integers")
            parsed = int(value)
            if parsed < 1:
                raise ValueError("api vendor ids must be positive")
            api_vendor_ids.append(parsed)

        return PlaybookCatalogEntry(
            playbook_id=str(raw.get("id") or "").strip(),
            name=str(raw.get("name") or "").strip(),
            version=str(raw.get("version") or "").strip(),
            lifecycle=str(raw.get("lifecycle") or "").strip().casefold(),
            enabled=raw.get("enabled") is True,
            source=str(raw.get("source") or "").strip(),
            autonomy_activation=activation,
            required_gates=tuple(str(x).strip() for x in autonomy.get("required_gates") or () if str(x).strip()),
            allowed_capabilities=tuple(str(x).strip() for x in autonomy.get("allowed_capabilities") or () if str(x).strip()),
            autonomy_policy_id=(str(autonomy.get("policy_id") or "").strip() or None),
            trigger_title_contains=tuple(str(x).strip().casefold() for x in trigger.get("title_contains") or () if str(x).strip()),
            trigger_api_vendor_ids=tuple(api_vendor_ids),
        )
