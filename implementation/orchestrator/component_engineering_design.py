"""Bounded AI design review for DRMM component engineering requests.

The model may recommend reuse/improvement/new/native and draft a design/test plan.
It receives no provider tools and cannot create, modify, approve, promote, or run
DRMM components.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


class StructuredDesignClient(Protocol):
    def complete(self, *, system: str, user: str, schema: Mapping[str, Any], max_output_tokens: int = 1600) -> Mapping[str, Any]: ...


_SYSTEM_INSTRUCTIONS = """You are Jason's bounded Component Engineering design reviewer for an MSP. Prefer existing native Kaseya/Datto/Autotask capabilities and existing AOT components before proposing new code. Treat supplied satisfies_request flags as authoritative: never recommend use_existing unless at least one supplied existing component has satisfies_request=true, and never recommend prefer_native_capability unless at least one supplied native capability has satisfies_request=true. Evaluate only the supplied governed request, existing component metadata, provider capability metadata, and operational evidence summaries. Never invent live provider capabilities or claim a component was tested, created, promoted, or executed. Choose exactly one recommendation: use_existing, improve_existing, new_component, or prefer_native_capability. For improvements/new components, design for deterministic machine-readable output plus useful technician-readable details, bounded execution, no secret exposure, explicit inputs, clear exit/result semantics, and authoritative verification. Preserve existing Jason governance: read-only designs may be candidates for autonomous bounded testing on approved test devices; modifying designs require controlled testing and promotion approval; disruptive actions always require instance-specific approval. Output a concrete design and acceptance plan, not provider execution instructions. Do not authorize publication or promotion."""

_SCHEMA: Mapping[str, Any] = {
 "type":"object","additionalProperties":False,
 "required":["recommendation","rationale","proposed_name","purpose","inputs","result_fields","safety_class","implementation_requirements","test_plan","acceptance_criteria","promotion_requires_human_approval"],
 "properties":{
  "recommendation":{"type":"string","enum":["use_existing","improve_existing","new_component","prefer_native_capability"]},
  "rationale":{"type":"string","maxLength":1800},
  "proposed_name":{"type":"string","maxLength":240},
  "purpose":{"type":"string","maxLength":1200},
  "inputs":{"type":"array","items":{"type":"string","maxLength":300},"maxItems":24},
  "result_fields":{"type":"array","items":{"type":"string","maxLength":200},"maxItems":40},
  "safety_class":{"type":"string","enum":["read_only","non_destructive","modifying","disruptive"]},
  "implementation_requirements":{"type":"array","items":{"type":"string","maxLength":500},"maxItems":40},
  "test_plan":{"type":"array","items":{"type":"string","maxLength":500},"maxItems":30},
  "acceptance_criteria":{"type":"array","items":{"type":"string","maxLength":500},"maxItems":30},
  "promotion_requires_human_approval":{"type":"boolean"}
 }
}


@dataclass(frozen=True, slots=True)
class FallbackStructuredDesignClient:
    primary: StructuredDesignClient
    fallback: StructuredDesignClient

    def complete(self, *, system: str, user: str, schema: Mapping[str, Any], max_output_tokens: int = 1600) -> Mapping[str, Any]:
        try:
            return self.primary.complete(system=system,user=user,schema=schema,max_output_tokens=max_output_tokens)
        except Exception:
            return self.fallback.complete(system=system,user=user,schema=schema,max_output_tokens=max_output_tokens)


@dataclass(frozen=True, slots=True)
class ComponentDesignReview:
    recommendation: str
    rationale: str
    proposed_name: str
    purpose: str
    inputs: tuple[str,...]
    result_fields: tuple[str,...]
    safety_class: str
    implementation_requirements: tuple[str,...]
    test_plan: tuple[str,...]
    acceptance_criteria: tuple[str,...]
    promotion_requires_human_approval: bool


@dataclass(frozen=True, slots=True)
class ComponentEngineeringDesigner:
    client: StructuredDesignClient

    def design(self, *, request: Mapping[str, Any], existing_components: Sequence[Mapping[str, Any]], native_capabilities: Sequence[Mapping[str, Any]], evidence_summaries: Sequence[Mapping[str, Any]]) -> ComponentDesignReview:
        if not str(request.get("request_id","")).strip(): raise ValueError("component engineering request_id is required")
        raw=self.client.complete(system=_SYSTEM_INSTRUCTIONS,user=json.dumps({"request":dict(request),"existing_components":[dict(x) for x in existing_components],"native_capabilities":[dict(x) for x in native_capabilities],"evidence_summaries":[dict(x) for x in evidence_summaries]},ensure_ascii=False,separators=(",",":")),schema=_SCHEMA,max_output_tokens=1024)
        if not isinstance(raw,Mapping) or set(raw)!=set(_SCHEMA["required"]): raise ValueError("component design result shape is invalid")
        rec=str(raw["recommendation"]); safety=str(raw["safety_class"]); approval=raw["promotion_requires_human_approval"]
        if rec not in {"use_existing","improve_existing","new_component","prefer_native_capability"}: raise ValueError("invalid component design recommendation")
        if safety not in {"read_only","non_destructive","modifying","disruptive"}: raise ValueError("invalid component design safety class")
        if not isinstance(approval,bool): raise ValueError("promotion approval field must be boolean")
        if safety in {"modifying","disruptive"} and approval is not True: raise ValueError("modifying/disruptive design must require promotion approval")
        if rec == "use_existing" and not any(item.get("satisfies_request") is True for item in existing_components):
            raise ValueError("use_existing requires an explicitly sufficient existing component")
        if rec == "prefer_native_capability" and not any(item.get("satisfies_request") is True for item in native_capabilities):
            raise ValueError("prefer_native_capability requires an explicitly sufficient native capability")
        return ComponentDesignReview(rec,str(raw["rationale"]).strip(),str(raw["proposed_name"]).strip(),str(raw["purpose"]).strip(),tuple(map(str,raw["inputs"])),tuple(map(str,raw["result_fields"])),safety,tuple(map(str,raw["implementation_requirements"])),tuple(map(str,raw["test_plan"])),tuple(map(str,raw["acceptance_criteria"])),approval)
