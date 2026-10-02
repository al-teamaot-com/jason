"""Deterministic interpreter for active JSON playbooks.

The interpreter emits instructions.  It never invokes providers directly and never
converts a playbook declaration into execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .playbook_document import PlaybookDocument


@dataclass(frozen=True, slots=True)
class PlaybookInstruction:
    playbook_id: str
    version: str
    step_id: str
    step_type: str
    capability: str | None
    arguments: Mapping[str, Any]
    approval_classification: str | None
    approval_required: bool
    terminal: bool = False


class JsonPlaybookInterpreter:
    def __init__(self, document: PlaybookDocument) -> None:
        self.document = document
        self._steps = {
            str(item["id"]): item
            for item in document.payload["steps"]
        }

    def instruction(
        self,
        *,
        step_id: str | None = None,
        facts: Mapping[str, Any] | None = None,
    ) -> PlaybookInstruction:
        current = str(step_id or self.document.entry_step)
        step = self._steps.get(current)
        if step is None:
            raise KeyError("PLAYBOOK_STEP_NOT_FOUND")
        step_type = str(step["type"]).strip().casefold()

        if step_type == "decision":
            target = self._decision_target(step, facts or {})
            return self.instruction(step_id=target, facts=facts)

        return PlaybookInstruction(
            playbook_id=self.document.playbook_id,
            version=self.document.version,
            step_id=current,
            step_type=step_type,
            capability=(str(step.get("capability") or "").strip() or None),
            arguments=dict(step.get("arguments") or {}),
            approval_classification=(
                str(step.get("approval_classification") or "").strip() or None
            ),
            approval_required=step.get("approval_required") is True,
            terminal=step_type in {"complete", "escalate", "human_review"},
        )

    def next_step(self, step_id: str, *, facts: Mapping[str, Any] | None = None) -> str | None:
        step = self._steps.get(str(step_id))
        if step is None:
            raise KeyError("PLAYBOOK_STEP_NOT_FOUND")
        kind = str(step["type"]).strip().casefold()
        if kind in {"complete", "escalate", "human_review"}:
            return None
        if kind == "decision":
            return self._decision_target(step, facts or {})
        if kind == "wait":
            return str(step["resume"])
        if kind == "remediation":
            return str(step["verification_step"])
        return str(step["next"])

    @staticmethod
    def _decision_target(step: Mapping[str, Any], facts: Mapping[str, Any]) -> str:
        for branch in step["branches"]:
            condition = branch["when"]
            fact_name = str(condition["fact"])
            operator = str(condition["operator"]).casefold()
            present = fact_name in facts
            actual = facts.get(fact_name)
            expected = condition.get("value")
            matched = False
            if operator == "eq":
                matched = actual == expected
            elif operator == "ne":
                matched = actual != expected
            elif operator == "in":
                matched = actual in (expected or ())
            elif operator == "not_in":
                matched = actual not in (expected or ())
            elif operator == "exists":
                matched = present
            elif operator == "truthy":
                matched = bool(actual)
            elif operator == "falsy":
                matched = not bool(actual)
            if matched:
                return str(branch["next"])
        return str(step["default"])
