"""Bounded AI proposal generation for missing AOT client communication templates.

The model drafts structured content only. HTML is rendered deterministically by the
approved AOT shell in autonomous_remediation.communication_templates.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


class StructuredCommunicationClient(Protocol):
    def complete(self, *, system: str, user: str, schema: Mapping[str, Any], max_output_tokens: int = 1024) -> Mapping[str, Any]: ...


_SYSTEM_INSTRUCTIONS = """You are Jason's bounded AOT client-communication template designer. Draft a reusable proposed template only when the caller has already established that no approved template fits the communication purpose. Preserve Atlantic Office Technologies' professional MSP tone: concise, clear, action-oriented, non-alarmist, and suitable for an owner, office manager, or end user as specified. Do not invent incident facts, client promises, SLAs, pricing, legal statements, security conclusions, or actions already taken. Do not generate HTML. Return structured content slots only; Jason will render them into the approved AOT HTML shell. Separate reusable wording from ticket-specific facts using named required_variables rather than hard-coded client/device/user values. Proposed templates are drafts and must never be described as approved or published. Avoid exposing internal-only diagnostics, secrets, provider IDs, or technician-only notes. If the communication asks the user to act, make the requested action explicit and explain why it is needed in plain language. Keep subject/title reusable across clients. Return only the required structured object."""

_SCHEMA: Mapping[str, Any] = {
 "type":"object","additionalProperties":False,
 "required":["proposed_name","subject","title","intro","paragraphs","bullets","closing","required_variables","rationale"],
 "properties":{
  "proposed_name":{"type":"string","maxLength":220},
  "subject":{"type":"string","maxLength":240},
  "title":{"type":"string","maxLength":100},
  "intro":{"type":"string","maxLength":600},
  "paragraphs":{"type":"array","items":{"type":"string","maxLength":900},"maxItems":8},
  "bullets":{"type":"array","items":{"type":"string","maxLength":500},"maxItems":10},
  "closing":{"type":"string","maxLength":200},
  "required_variables":{"type":"array","items":{"type":"string","maxLength":100},"maxItems":20},
  "rationale":{"type":"string","maxLength":1200}
 }
}


@dataclass(frozen=True,slots=True)
class CommunicationTemplateDesign:
    proposed_name: str
    subject: str
    title: str
    intro: str
    paragraphs: tuple[str,...]
    bullets: tuple[str,...]
    closing: str
    required_variables: tuple[str,...]
    rationale: str


@dataclass(frozen=True,slots=True)
class CommunicationTemplateDesigner:
    client: StructuredCommunicationClient

    def design(self, *, purpose_key: str, audience: str, scenario: str, approved_style_examples: Sequence[Mapping[str,Any]] = ()) -> CommunicationTemplateDesign:
        if not purpose_key.strip() or not audience.strip() or not scenario.strip():
            raise ValueError("purpose, audience, and scenario are required")
        raw=self.client.complete(system=_SYSTEM_INSTRUCTIONS,user=json.dumps({"purpose_key":purpose_key.strip(),"audience":audience.strip(),"scenario":scenario.strip(),"approved_style_examples":[dict(x) for x in approved_style_examples]},ensure_ascii=False,separators=(",",":")),schema=_SCHEMA,max_output_tokens=1024)
        if not isinstance(raw,Mapping) or set(raw)!=set(_SCHEMA["required"]):
            raise ValueError("communication template design result shape is invalid")
        values={k:str(raw[k]).strip() for k in ("proposed_name","subject","title","intro","closing","rationale")}
        if not all(values.values()): raise ValueError("communication template core fields may not be empty")
        paragraphs=tuple(str(x).strip() for x in raw["paragraphs"] if str(x).strip())
        bullets=tuple(str(x).strip() for x in raw["bullets"] if str(x).strip())
        variables=tuple(str(x).strip() for x in raw["required_variables"] if str(x).strip())
        if len(set(variables)) != len(variables): raise ValueError("required_variables must be unique")
        return CommunicationTemplateDesign(values["proposed_name"],values["subject"],values["title"],values["intro"],paragraphs,bullets,values["closing"],variables,values["rationale"])
