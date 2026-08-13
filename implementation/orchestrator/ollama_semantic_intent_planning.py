from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .ollama_reasoning import OllamaStructuredJsonClient
from .semantic_intent_planning_loop import (
    FulfillmentPlanCandidate,
    FulfillmentPlanStepCandidate,
    PlanningContextRequest,
    PlanningTraceEntry,
    PlanningTurn,
)


@dataclass(frozen=True, slots=True)
class OllamaSemanticIntentPlanningReasoner:
    """Bounded provider-neutral planning over governed context snapshots only."""

    client: OllamaStructuredJsonClient

    def next_turn(
        self,
        *,
        intent: Mapping[str, Any],
        context: Mapping[str, Any],
        history: Sequence[PlanningTraceEntry],
    ) -> PlanningTurn:
        governed_context_views = (
            "semantic_knowledge",
            "capability_registry",
            "system_registry",
            "evidence_catalog",
            "derivation_registry",
        )
        available_context_views = tuple(
            view for view in governed_context_views if view in context
        )
        requestable_context_views = tuple(
            view for view in governed_context_views if view not in context
        )
        allowed_statuses = ["propose_plan", "declare_gap"]
        if requestable_context_views:
            allowed_statuses.insert(0, "request_context")

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {
                    "type": "string",
                    "enum": allowed_statuses,
                },
                "context_view": {
                    "type": "string",
                    "enum": list(requestable_context_views) if requestable_context_views else [""],
                },
                "context_query": {"type": "string"},
                "context_purpose": {"type": "string"},
                "plan_steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "capability_name": {"type": "string"},
                            "purpose": {"type": "string"},
                            "required_facts": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "expected_evidence": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "capability_name",
                            "purpose",
                            "required_facts",
                            "expected_evidence",
                        ],
                    },
                },
                "rationale_summary": {"type": "string"},
                "unresolved_requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "gap_summary": {"type": "string"},
            },
            "required": [
                "status",
                "context_view",
                "context_query",
                "context_purpose",
                "plan_steps",
                "rationale_summary",
                "unresolved_requirements",
                "gap_summary",
            ],
        }

        result = self.client.complete(
            system=(
                "You are Jason's bounded semantic fulfillment planner. Determine how the supplied "
                "provider-neutral intent can be satisfied using only governed context already supplied "
                "or by requesting one approved context view. You have no authority to execute anything. "
                "Never name or choose providers, connectors, agents, tools, URLs, shell commands, "
                "credentials, or secrets. Never invent facts or evidence. Request additional context when "
                "needed. Never request the exact same context view and query twice. Treat a returned governed "
                "context snapshot as satisfied and progress to a different information need, a plan, or a gap. "
                "For a normal information request, prefer semantic knowledge and capability-registry context "
                "before system-state context unless system availability is specifically unresolved. A proposed "
                "plan may reference only capability names present in governed capability registry context. "
                "Prefer direct authoritative evidence; otherwise consider alternate governed capabilities or "
                "approved derivations represented in context. If plan_validation context is present, the prior "
                "plan was rejected as insufficient for the original intent: consume those issues, revise the "
                "plan, request different governed context, or declare a knowledge gap. Never repeat a rejected "
                "plan unchanged. The user payload explicitly lists available_context_views and "
                "requestable_context_views. A request_context response is permitted only for a view listed in "
                "requestable_context_views; never request a view already listed in available_context_views. "
                "If context_request_feedback is present, consume the existing snapshot and do not request that "
                "same view/query again. If no governed "
                "fulfillment path is established, declare a knowledge gap. Keep "
                "reasoning concise and structured."
            ),
            user=json.dumps(
                {
                    "intent": dict(intent),
                    "governed_context": dict(context),
                    "available_context_views": list(available_context_views),
                    "requestable_context_views": list(requestable_context_views),
                    "history": [
                        {
                            "iteration": item.iteration,
                            "status": item.status,
                            "context_view": item.context_view,
                        }
                        for item in history
                    ],
                },
                sort_keys=True,
            ),
            schema=schema,
            max_output_tokens=320,
        )

        status = str(result.get("status", "")).strip()
        if status == "request_context":
            view = str(result.get("context_view", "")).strip()
            if view not in requestable_context_views:
                raise PermissionError(
                    f"semantic planner requested context view that is not requestable this turn: {view}"
                )
            query = str(result.get("context_query", "")).strip()
            purpose = str(result.get("context_purpose", "")).strip()
            return PlanningTurn(
                status="request_context",
                context_request=PlanningContextRequest(
                    view=view,
                    query={"query": query} if query else {},
                    purpose=purpose,
                ),
            )

        if status == "propose_plan":
            steps = []
            raw_steps = result.get("plan_steps", [])
            if not isinstance(raw_steps, list):
                raise ValueError("Ollama semantic planning plan_steps must be a list")
            for raw_step in raw_steps:
                if not isinstance(raw_step, Mapping):
                    raise ValueError("Ollama semantic planning step must be an object")
                steps.append(
                    FulfillmentPlanStepCandidate(
                        capability_name=str(raw_step.get("capability_name", "")).strip(),
                        purpose=str(raw_step.get("purpose", "")).strip(),
                        required_facts=tuple(
                            str(item).strip()
                            for item in raw_step.get("required_facts", [])
                            if str(item).strip()
                        ),
                        expected_evidence=tuple(
                            str(item).strip()
                            for item in raw_step.get("expected_evidence", [])
                            if str(item).strip()
                        ),
                    )
                )
            unresolved = tuple(
                str(item).strip()
                for item in result.get("unresolved_requirements", [])
                if str(item).strip()
            )
            return PlanningTurn(
                status="propose_plan",
                plan=FulfillmentPlanCandidate(
                    steps=tuple(steps),
                    rationale_summary=str(result.get("rationale_summary", "")).strip(),
                    unresolved_requirements=unresolved,
                ),
            )

        if status != "declare_gap":
            raise ValueError("Ollama semantic planning returned invalid status")
        return PlanningTurn(
            status="declare_gap",
            gap_summary=str(result.get("gap_summary", "")).strip(),
        )
