"""Approved communication catalog and durable template-gap requests for Jason.

Proposed templates are never approved merely because they were generated. Jason may
use only catalog entries explicitly marked approved. Missing coverage creates or
strengthens a durable request containing a finished subject and deterministic AOT
HTML proposal for human review.
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


AOT_LOGO_URL = "https://atlanticofficetechnologies.com/wp-content/uploads/2020/07/AOT-logo-300w.png"
AOT_REPLY_LINE = "*** Please enter replies above this line ***"


def render_aot_html(*, title: str, intro: str, paragraphs: Iterable[str] = (), bullets: Iterable[str] = (), closing: str = "Thank you,", signature: str = "Atlantic Office Technologies") -> str:
    """Render the approved AOT HTML shell around already-reviewed content slots."""
    def esc(value: str) -> str:
        return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
    para_html = "".join(f'<p style="margin:0 0 12px 0;">{esc(p)}</p>' for p in paragraphs if str(p).strip())
    bullet_items = "".join(f'<li style="margin:0 0 6px 0;">{esc(x)}</li>' for x in bullets if str(x).strip())
    bullet_html = f'<ul style="margin:0 0 12px 20px;padding:0;">{bullet_items}</ul>' if bullet_items else ""
    return f'''<!doctype html>
<html>
<body style="margin:0;padding:0;background:#e5e5e5;font-family:Tahoma,Arial,sans-serif;font-size:10pt;color:#4d4d4d;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#e5e5e5;width:100%;">
<tr><td align="center" style="padding:18px 10px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:630px;width:100%;">
<tr><td align="center" style="padding:0 0 10px 0;color:#777777;font-size:10px;">{esc(AOT_REPLY_LINE)}</td></tr>
<tr><td align="center" style="padding:0 0 14px 0;"><img src="{AOT_LOGO_URL}" width="150" alt="Atlantic Office Technologies Logo" style="display:block;border:0;max-width:150px;height:auto;"></td></tr>
<tr><td style="background:#ffffff;border:1px solid #cccccc;padding:24px;">
<div style="font-size:20px;line-height:24px;font-weight:bold;text-transform:uppercase;margin:0 0 18px 0;color:#4d4d4d;">{esc(title)}</div>
<p style="margin:0 0 12px 0;">{esc(intro)}</p>
{para_html}{bullet_html}
<p style="margin:18px 0 0 0;">{esc(closing)}<br>{esc(signature)}</p>
</td></tr>
<tr><td align="center" style="padding:14px 8px 0 8px;color:#999999;font-size:10px;line-height:14px;">Atlantic Office Technologies</td></tr>
</table>
</td></tr>
</table>
</body>
</html>'''


class TemplateRequestLifecycle(str, Enum):
    OPEN = "open"
    DRAFTED = "drafted"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    PUBLISHED = "published"
    DEFERRED = "deferred"
    RESOLVED = "resolved"


@dataclass
class ApprovedCommunicationTemplate:
    template_id: str
    name: str
    purpose_key: str
    audience: str
    subject: str
    html_body: str
    approved: bool
    source: str
    last_reviewed_at: str = ""
    owner: str = "AOT Service Management"
    notes: list[str] = field(default_factory=list)


@dataclass
class CommunicationTemplateRequest:
    request_id: str
    purpose_key: str
    audience: str
    scenario: str
    reason_no_fit: str
    proposed_name: str
    proposed_subject: str
    proposed_html_body: str
    lifecycle: TemplateRequestLifecycle = TemplateRequestLifecycle.DRAFTED
    required_variables: list[str] = field(default_factory=list)
    source_playbooks: list[str] = field(default_factory=list)
    source_run_ids: list[str] = field(default_factory=list)
    source_ticket_ids: list[str] = field(default_factory=list)
    occurrence_count: int = 1
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    owner: str = "AOT Service Management"
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not all(str(x).strip() for x in (self.request_id,self.purpose_key,self.audience,self.proposed_name,self.proposed_subject,self.proposed_html_body)):
            raise ValueError("communication template request identity/proposal fields are required")
        if not isinstance(self.lifecycle, TemplateRequestLifecycle):
            self.lifecycle = TemplateRequestLifecycle(str(self.lifecycle))
        if self.occurrence_count < 1:
            raise ValueError("occurrence_count must be positive")

    def strengthen(self, *, playbook_id: str="", run_id: str="", ticket_id: str="", note: str="") -> None:
        if self.lifecycle in {TemplateRequestLifecycle.PUBLISHED,TemplateRequestLifecycle.RESOLVED}:
            raise ValueError("terminal communication template request cannot be strengthened")
        self.occurrence_count += 1
        self.updated_at = _now()
        _append_unique(self.source_playbooks,playbook_id); _append_unique(self.source_run_ids,run_id); _append_unique(self.source_ticket_ids,ticket_id)
        if note.strip(): self.notes.append(note.strip())


def _append_unique(values: list[str], value: str) -> None:
    text=str(value or "").strip()
    if text and text not in values: values.append(text)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+","-",text.casefold()).strip("-")[:72] or "template-gap"


class FileCommunicationTemplateCatalog:
    def __init__(self, path: Path|str|None=None) -> None:
        self.path=Path(path or os.environ.get("JASON_COMMUNICATION_TEMPLATE_CATALOG","/var/lib/jason/communications/approved-templates.json"))

    def list(self) -> list[ApprovedCommunicationTemplate]:
        if not self.path.exists(): return []
        data=json.loads(self.path.read_text(encoding="utf-8"))
        return [ApprovedCommunicationTemplate(**x) for x in data.get("templates",[]) if isinstance(x,dict)]

    def find_approved(self, *, purpose_key: str, audience: str) -> list[ApprovedCommunicationTemplate]:
        p=purpose_key.strip().casefold(); a=audience.strip().casefold()
        return [x for x in self.list() if x.approved and x.purpose_key.casefold()==p and x.audience.casefold()==a]


class FileCommunicationTemplateRequestStore:
    def __init__(self, root: Path|str|None=None) -> None:
        self.root=Path(root or os.environ.get("JASON_COMMUNICATION_TEMPLATE_REQUESTS_PATH","/var/lib/jason/communications/template-requests"))

    def _path(self, request_id: str) -> Path:
        if not request_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in request_id): raise ValueError("invalid communication template request id")
        return self.root/f"{request_id}.json"

    def save(self, req: CommunicationTemplateRequest) -> None:
        self.root.mkdir(parents=True,exist_ok=True); payload=asdict(req); payload['lifecycle']=req.lifecycle.value
        fd,tmp=tempfile.mkstemp(prefix=f".{req.request_id}.",suffix=".tmp",dir=self.root)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as h:
                json.dump(payload,h,indent=2,sort_keys=True); h.write("\n"); h.flush(); os.fsync(h.fileno())
            os.replace(tmp,self._path(req.request_id))
        finally:
            try: os.unlink(tmp)
            except FileNotFoundError: pass

    def load(self, request_id: str) -> CommunicationTemplateRequest:
        return CommunicationTemplateRequest(**json.loads(self._path(request_id).read_text(encoding="utf-8")))

    def list(self) -> list[CommunicationTemplateRequest]:
        if not self.root.exists(): return []
        out=[]
        for p in sorted(self.root.glob("*.json")):
            try: out.append(self.load(p.stem))
            except (OSError,ValueError,TypeError,json.JSONDecodeError): continue
        return out


@dataclass(frozen=True,slots=True)
class CommunicationTemplateService:
    catalog: FileCommunicationTemplateCatalog
    requests: FileCommunicationTemplateRequestStore

    def find_or_request(self, *, purpose_key: str, audience: str, scenario: str, reason_no_fit: str, proposed_name: str, proposed_subject: str, proposed_html_body: str, required_variables: Iterable[str]=(), playbook_id: str="", run_id: str="", ticket_id: str=""):
        matches=self.catalog.find_approved(purpose_key=purpose_key,audience=audience)
        if matches: return matches[0], None, False
        request_id=f"CTR-{_slug(purpose_key)}-{_slug(audience)}"
        try:
            req=self.requests.load(request_id); req.strengthen(playbook_id=playbook_id,run_id=run_id,ticket_id=ticket_id,note="Repeated no-fit occurrence automatically attached by Jason."); self.requests.save(req); return None,req,False
        except FileNotFoundError:
            req=CommunicationTemplateRequest(request_id=request_id,purpose_key=purpose_key.strip(),audience=audience.strip(),scenario=scenario.strip(),reason_no_fit=reason_no_fit.strip(),proposed_name=proposed_name.strip(),proposed_subject=proposed_subject.strip(),proposed_html_body=proposed_html_body,lifecycle=TemplateRequestLifecycle.DRAFTED,required_variables=[str(x).strip() for x in required_variables if str(x).strip()])
            _append_unique(req.source_playbooks,playbook_id); _append_unique(req.source_run_ids,run_id); _append_unique(req.source_ticket_ids,ticket_id); self.requests.save(req); return None,req,True
