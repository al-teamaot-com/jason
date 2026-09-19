"""Durable, provider-neutral Component Engineering request workflow.

Jason may autonomously create/strengthen engineering requests when operational
work reveals a tooling gap. This module creates no Datto components and grants
no provider mutation authority. Promotion/testing/execution remain governed by
existing Jason policies and Component Control.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EngineeringRequestKind(str, Enum):
    IMPROVE_EXISTING = "improve_existing"
    NEW_COMPONENT = "new_component"
    USE_EXISTING = "use_existing"
    PREFER_NATIVE = "prefer_native_capability"


class EngineeringLifecycle(str, Enum):
    OPEN = "open"
    DESIGNING = "designing"
    TESTING = "testing"
    PILOT = "pilot"
    AWAITING_PROMOTION = "awaiting_promotion"
    PRODUCTION = "production"
    DEFERRED = "deferred"
    RESOLVED = "resolved"
    RETIRED = "retired"


class EngineeringRisk(str, Enum):
    READ_ONLY = "read_only"
    NON_DESTRUCTIVE = "non_destructive"
    MODIFYING = "modifying"
    DISRUPTIVE = "disruptive"


@dataclass
class ComponentEngineeringRequest:
    request_id: str
    title: str
    problem_key: str
    kind: EngineeringRequestKind
    lifecycle: EngineeringLifecycle = EngineeringLifecycle.OPEN
    risk: EngineeringRisk = EngineeringRisk.READ_ONLY
    existing_component_uid: str = ""
    existing_component_name: str = ""
    desired_capability: str = ""
    gap_summary: str = ""
    proposed_change: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    dependent_playbooks: list[str] = field(default_factory=list)
    source_run_ids: list[str] = field(default_factory=list)
    source_ticket_ids: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    occurrence_count: int = 1
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    last_seen_at: str = field(default_factory=_now)
    owner: str = "Jason Architecture Authority"
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.title.strip() or not self.problem_key.strip():
            raise ValueError("component engineering request identity is required")
        if self.occurrence_count < 1:
            raise ValueError("component engineering occurrence count must be positive")
        if not isinstance(self.kind, EngineeringRequestKind):
            self.kind = EngineeringRequestKind(str(self.kind))
        if not isinstance(self.lifecycle, EngineeringLifecycle):
            self.lifecycle = EngineeringLifecycle(str(self.lifecycle))
        if not isinstance(self.risk, EngineeringRisk):
            self.risk = EngineeringRisk(str(self.risk))

    @property
    def terminal(self) -> bool:
        return self.lifecycle in {EngineeringLifecycle.RESOLVED, EngineeringLifecycle.RETIRED}

    def strengthen(
        self,
        *,
        playbook_id: str = "",
        run_id: str = "",
        ticket_id: str = "",
        evidence_refs: Iterable[str] = (),
        gap_summary: str = "",
        note: str = "",
    ) -> None:
        if self.terminal:
            raise ValueError("terminal component engineering request cannot be strengthened")
        self.occurrence_count += 1
        self.updated_at = _now()
        self.last_seen_at = self.updated_at
        _append_unique(self.dependent_playbooks, playbook_id)
        _append_unique(self.source_run_ids, run_id)
        _append_unique(self.source_ticket_ids, ticket_id)
        for ref in evidence_refs:
            _append_unique(self.evidence_refs, str(ref))
        if gap_summary.strip() and gap_summary.strip() != self.gap_summary:
            self.gap_summary = gap_summary.strip()
        if note.strip():
            self.notes.append(note.strip())

    def set_lifecycle(self, target: EngineeringLifecycle) -> None:
        if not isinstance(target, EngineeringLifecycle):
            target = EngineeringLifecycle(str(target))
        if self.terminal and target != self.lifecycle:
            raise ValueError("terminal component engineering request cannot transition")
        self.lifecycle = target
        self.updated_at = _now()


def _append_unique(values: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return value[:64] or "component-gap"


class FileComponentEngineeringStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or os.environ.get("JASON_COMPONENT_ENGINEERING_PATH", "/var/lib/jason/component-engineering/requests"))

    def _path(self, request_id: str) -> Path:
        if not request_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in request_id):
            raise ValueError("invalid component engineering request id")
        return self.root / f"{request_id}.json"

    def save(self, request: ComponentEngineeringRequest) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = asdict(request)
        payload["kind"] = request.kind.value
        payload["lifecycle"] = request.lifecycle.value
        payload["risk"] = request.risk.value
        fd, tmp = tempfile.mkstemp(prefix=f".{request.request_id}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as h:
                json.dump(payload, h, indent=2, sort_keys=True)
                h.write("\n"); h.flush(); os.fsync(h.fileno())
            os.replace(tmp, self._path(request.request_id))
        finally:
            try: os.unlink(tmp)
            except FileNotFoundError: pass

    def load(self, request_id: str) -> ComponentEngineeringRequest:
        payload = json.loads(self._path(request_id).read_text(encoding="utf-8"))
        return ComponentEngineeringRequest(**payload)

    def list(self) -> list[ComponentEngineeringRequest]:
        if not self.root.exists(): return []
        out=[]
        for path in sorted(self.root.glob("*.json")):
            try: out.append(self.load(path.stem))
            except (OSError, ValueError, TypeError, json.JSONDecodeError): continue
        return out

    def find_active_by_problem_key(self, problem_key: str) -> list[ComponentEngineeringRequest]:
        key=problem_key.strip().casefold()
        return [r for r in self.list() if not r.terminal and r.problem_key.casefold()==key]


@dataclass(frozen=True, slots=True)
class ComponentEngineeringService:
    store: FileComponentEngineeringStore

    def report_gap(
        self,
        *,
        problem_key: str,
        title: str,
        kind: EngineeringRequestKind,
        risk: EngineeringRisk,
        desired_capability: str,
        gap_summary: str,
        playbook_id: str = "",
        run_id: str = "",
        ticket_id: str = "",
        evidence_refs: Iterable[str] = (),
        existing_component_uid: str = "",
        existing_component_name: str = "",
        proposed_change: str = "",
        acceptance_criteria: Iterable[str] = (),
    ) -> tuple[ComponentEngineeringRequest, bool]:
        if not problem_key.strip() or not title.strip() or not gap_summary.strip():
            raise ValueError("problem key, title, and gap summary are required")
        matches=self.store.find_active_by_problem_key(problem_key)
        if len(matches)>1:
            raise ValueError("multiple active component engineering requests share one problem key")
        if matches:
            req=matches[0]
            req.strengthen(playbook_id=playbook_id,run_id=run_id,ticket_id=ticket_id,evidence_refs=evidence_refs,gap_summary=gap_summary,note="Repeated operational occurrence automatically attached by Jason.")
            self.store.save(req)
            return req, False
        request_id=f"CER-{_slug(problem_key)}"
        req=ComponentEngineeringRequest(
            request_id=request_id,title=title.strip(),problem_key=problem_key.strip(),kind=kind,risk=risk,
            existing_component_uid=existing_component_uid.strip(),existing_component_name=existing_component_name.strip(),
            desired_capability=desired_capability.strip(),gap_summary=gap_summary.strip(),proposed_change=proposed_change.strip(),
            acceptance_criteria=[str(x).strip() for x in acceptance_criteria if str(x).strip()],
        )
        _append_unique(req.dependent_playbooks,playbook_id); _append_unique(req.source_run_ids,run_id); _append_unique(req.source_ticket_ids,ticket_id)
        for ref in evidence_refs: _append_unique(req.evidence_refs,str(ref))
        self.store.save(req)
        return req, True
