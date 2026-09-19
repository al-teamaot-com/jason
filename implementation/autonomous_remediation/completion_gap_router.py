"""Generic completion-gap routing for Jason PlaybookRun workflows.

A gap route is workflow metadata, never execution authority. The router can create
or strengthen durable improvement records, mark a run awaiting a human decision,
or schedule a bounded recheck. It does not call providers or perform remediation.
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

try:
    from .playbook_runtime import FilePlaybookRunStore, PlaybookRunRecord, RunState
except ImportError:
    from playbook_runtime import FilePlaybookRunStore, PlaybookRunRecord, RunState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


class GapClass(str, Enum):
    COMPONENT_TOOLING = 'component_tooling'
    COMMUNICATION_TEMPLATE = 'communication_template'
    PROVIDER_CAPABILITY = 'provider_capability'
    DOCUMENTATION = 'documentation'
    HUMAN_DECISION = 'human_decision'
    TEMPORARY_CONDITION = 'temporary_condition'


_REASON_CLASS_MAP = {
    "component_output_inadequate": GapClass.COMPONENT_TOOLING,
    "component_missing": GapClass.COMPONENT_TOOLING,
    "component_repeated_failure": GapClass.COMPONENT_TOOLING,
    "approved_template_missing": GapClass.COMMUNICATION_TEMPLATE,
    "communication_template_missing": GapClass.COMMUNICATION_TEMPLATE,
    "capability_unavailable": GapClass.PROVIDER_CAPABILITY,
    "provider_capability_missing": GapClass.PROVIDER_CAPABILITY,
    "provider_write_unavailable": GapClass.PROVIDER_CAPABILITY,
    "documentation_missing": GapClass.DOCUMENTATION,
    "documentation_stale": GapClass.DOCUMENTATION,
    "documentation_conflict": GapClass.DOCUMENTATION,
    "human_decision_required": GapClass.HUMAN_DECISION,
    "approval_required": GapClass.HUMAN_DECISION,
    "authority_or_human_required": GapClass.HUMAN_DECISION,
    "endpoint_offline": GapClass.TEMPORARY_CONDITION,
    "provider_temporarily_unavailable": GapClass.TEMPORARY_CONDITION,
    "temporary_evidence_unavailable": GapClass.TEMPORARY_CONDITION,
}


def classify_reason_class(reason_class: str) -> GapClass:
    key=str(reason_class or "").strip().casefold()
    try:
        return _REASON_CLASS_MAP[key]
    except KeyError as exc:
        raise ValueError("unrecognized completion-gap reason class") from exc


class GapLifecycle(str, Enum):
    OPEN = 'open'
    ROUTED = 'routed'
    WAITING = 'waiting'
    RESOLVED = 'resolved'
    DEFERRED = 'deferred'


@dataclass
class CompletionGapRecord:
    gap_id: str
    problem_key: str
    gap_class: GapClass
    title: str
    summary: str
    route_target: str
    lifecycle: GapLifecycle = GapLifecycle.OPEN
    occurrence_count: int = 1
    playbook_ids: list[str] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    ticket_ids: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    linked_request_ids: list[str] = field(default_factory=list)
    first_seen_at: str = field(default_factory=_now)
    last_seen_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    next_recheck_at: str = ''
    notes: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not all(str(x).strip() for x in (self.gap_id,self.problem_key,self.title,self.summary,self.route_target)):
            raise ValueError('completion gap identity is required')
        if not isinstance(self.gap_class,GapClass): self.gap_class=GapClass(str(self.gap_class))
        if not isinstance(self.lifecycle,GapLifecycle): self.lifecycle=GapLifecycle(str(self.lifecycle))
        if self.occurrence_count < 1: raise ValueError('occurrence_count must be positive')

    def strengthen(self, *, playbook_id='', run_id='', ticket_id='', evidence_refs: Iterable[str]=(), linked_request_id='', note=''):
        if self.lifecycle == GapLifecycle.RESOLVED: raise ValueError('resolved completion gap cannot be strengthened')
        self.occurrence_count += 1; self.last_seen_at=_now(); self.updated_at=self.last_seen_at
        for values,value in ((self.playbook_ids,playbook_id),(self.run_ids,run_id),(self.ticket_ids,ticket_id),(self.linked_request_ids,linked_request_id)):
            _append_unique(values,value)
        for ref in evidence_refs: _append_unique(self.evidence_refs,str(ref))
        if note.strip(): self.notes.append(note.strip())


def _append_unique(values:list[str], value:str):
    v=str(value or '').strip()
    if v and v not in values: values.append(v)


def _slug(text:str)->str:
    return re.sub(r'[^a-z0-9]+','-',text.casefold()).strip('-')[:72] or 'gap'


class FileCompletionGapStore:
    def __init__(self, root: Path|str|None=None):
        self.root=Path(root or os.environ.get('JASON_COMPLETION_GAPS_PATH','/var/lib/jason/openclaw/completion-gaps'))
    def _path(self,gap_id:str)->Path:
        if not gap_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-' for c in gap_id): raise ValueError('invalid completion gap id')
        return self.root/f'{gap_id}.json'
    def save(self,g:CompletionGapRecord):
        self.root.mkdir(parents=True,exist_ok=True); p=asdict(g); p['gap_class']=g.gap_class.value; p['lifecycle']=g.lifecycle.value
        fd,tmp=tempfile.mkstemp(prefix=f'.{g.gap_id}.',suffix='.tmp',dir=self.root)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as h: json.dump(p,h,indent=2,sort_keys=True); h.write('\n'); h.flush(); os.fsync(h.fileno())
            os.replace(tmp,self._path(g.gap_id))
        finally:
            try: os.unlink(tmp)
            except FileNotFoundError: pass
    def load(self,gap_id:str)->CompletionGapRecord:
        return CompletionGapRecord(**json.loads(self._path(gap_id).read_text(encoding='utf-8')))
    def list(self)->list[CompletionGapRecord]:
        if not self.root.exists(): return []
        out=[]
        for p in sorted(self.root.glob('*.json')):
            try: out.append(self.load(p.stem))
            except (OSError,ValueError,TypeError,json.JSONDecodeError): continue
        return out
    def find_active(self,problem_key:str)->list[CompletionGapRecord]:
        key=problem_key.strip().casefold(); return [g for g in self.list() if g.lifecycle!=GapLifecycle.RESOLVED and g.problem_key.casefold()==key]


@dataclass(frozen=True,slots=True)
class CompletionGapRouter:
    gaps: FileCompletionGapStore
    runs: FilePlaybookRunStore

    def route_reason(self, run:PlaybookRunRecord, *, problem_key:str, reason_class:str, title:str, summary:str, evidence_refs:Iterable[str]=(), linked_request_id:str='', recheck_at:str='') -> tuple[CompletionGapRecord,bool]:
        return self.route(run, problem_key=problem_key, gap_class=classify_reason_class(reason_class), title=title, summary=summary, evidence_refs=evidence_refs, linked_request_id=linked_request_id, recheck_at=recheck_at)

    def route(self, run:PlaybookRunRecord, *, problem_key:str, gap_class:GapClass, title:str, summary:str, evidence_refs:Iterable[str]=(), linked_request_id:str='', recheck_at:str='') -> tuple[CompletionGapRecord,bool]:
        if run.terminal: raise ValueError('terminal playbook run cannot route a new completion gap')
        if not isinstance(gap_class,GapClass): gap_class=GapClass(str(gap_class))
        route_target={
            GapClass.COMPONENT_TOOLING:'component_engineering',
            GapClass.COMMUNICATION_TEMPLATE:'communication_template_engineering',
            GapClass.PROVIDER_CAPABILITY:'capability_backlog',
            GapClass.DOCUMENTATION:'documentation_assurance',
            GapClass.HUMAN_DECISION:'human_approval_or_escalation',
            GapClass.TEMPORARY_CONDITION:'bounded_recheck',
        }[gap_class]
        matches=self.gaps.find_active(problem_key)
        if len(matches)>1: raise ValueError('multiple active completion gaps share one problem key')
        created=False
        if matches:
            gap=matches[0]; gap.strengthen(playbook_id=run.playbook_id,run_id=run.run_id,ticket_id=run.ticket_id,evidence_refs=evidence_refs,linked_request_id=linked_request_id,note='Repeated blocker occurrence automatically attached by Jason.')
        else:
            gap=CompletionGapRecord(gap_id=f'GAP-{_slug(problem_key)}',problem_key=problem_key.strip(),gap_class=gap_class,title=title.strip(),summary=summary.strip(),route_target=route_target,lifecycle=GapLifecycle.ROUTED)
            _append_unique(gap.playbook_ids,run.playbook_id); _append_unique(gap.run_ids,run.run_id); _append_unique(gap.ticket_ids,run.ticket_id); _append_unique(gap.linked_request_ids,linked_request_id)
            for ref in evidence_refs: _append_unique(gap.evidence_refs,str(ref))
            created=True
        if gap_class == GapClass.TEMPORARY_CONDITION:
            if not recheck_at.strip(): raise ValueError('temporary condition requires bounded recheck timestamp')
            gap.lifecycle=GapLifecycle.WAITING; gap.next_recheck_at=recheck_at.strip(); run.recheck_at=recheck_at.strip(); run.transition(RunState.RECHECK_PENDING)
        elif gap_class == GapClass.HUMAN_DECISION:
            gap.lifecycle=GapLifecycle.WAITING
            if run.state != RunState.BLOCKED: run.transition(RunState.BLOCKED,reason_class='human_decision_required')
        else:
            if run.state != RunState.BLOCKED: run.transition(RunState.BLOCKED,reason_class=gap_class.value)
        run.metadata['completion_gap_id']=gap.gap_id; run.metadata['completion_gap_route']=route_target
        run.record_step('completion_gap_routed','created' if created else 'strengthened',evidence_refs=tuple(evidence_refs),summary=f'{gap.gap_id} -> {route_target}')
        self.gaps.save(gap); self.runs.save(run); return gap,created
