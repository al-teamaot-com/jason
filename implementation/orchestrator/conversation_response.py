from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .contracts import OrchestrationResult, OrchestrationStatus
from .semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER
from .teams_conversation_flow import ConversationIntent, ConversationRenderDecision


@dataclass(frozen=True, slots=True)
class GovernedTeamsConversationResponseRenderer:
    """Render action results directly and delegate read-only resource evidence."""

    resource_renderer: object

    def render_decision(
        self,
        result: OrchestrationResult,
        intent: ConversationIntent,
    ) -> ConversationRenderDecision:
        if intent.permission_mode == "observe":
            decision_renderer = getattr(self.resource_renderer, "render_decision", None)
            if callable(decision_renderer):
                decision = decision_renderer(result, intent)
                if not isinstance(decision, ConversationRenderDecision):
                    raise TypeError("resource render_decision returned an invalid decision")
                return ConversationRenderDecision(
                    text=_normalize_semantic_presentation(decision.text, intent),
                    satisfies_request=decision.satisfies_request,
                )
            return ConversationRenderDecision(
                text=_normalize_semantic_presentation(
                    self.resource_renderer.render(result, intent),
                    intent,
                ),
                satisfies_request=False,
            )

        return ConversationRenderDecision(
            text=self._render_action(result),
            satisfies_request=result.status is OrchestrationStatus.SUCCEEDED,
        )

    def render(self, result: OrchestrationResult, intent: ConversationIntent) -> str:
        return self.render_decision(result, intent).text

    @staticmethod
    def _render_action(result: OrchestrationResult) -> str:
        if result.status is OrchestrationStatus.SUCCEEDED:
            return "Done — the requested governed action completed successfully."
        if result.status is OrchestrationStatus.APPROVAL_REQUIRED:
            return "The requested action requires approval before Jason can execute it."
        if result.status is OrchestrationStatus.DENIED:
            return "Jason could not execute that action because the governed request was denied."
        if result.status is OrchestrationStatus.HUMAN_REQUIRED:
            return "Jason needs human input before that governed action can continue."
        if result.status is OrchestrationStatus.FAILED:
            return "Jason attempted the governed action, but it failed. No automatic retry was performed."
        return "Jason could not complete the governed action."


def _normalize_semantic_presentation(text: str, intent: ConversationIntent) -> str:
    """Apply provider-independent display semantics after evidence is verified.

    This boundary does not infer facts, select providers, or alter evidence. It only
    renders already-returned requested facts according to governed semantic shape.
    The semantic registry therefore controls presentation behavior without creating
    question-specific provider mappings.
    """

    raw_facts = intent.arguments.get("requested_facts", ())
    if not isinstance(raw_facts, (list, tuple)):
        return text

    rendered = text
    for raw_fact in raw_facts:
        fact = str(raw_fact).strip()
        if not fact:
            continue
        resolution = DEFAULT_SEMANTIC_FACT_RESOLVER.resolve(fact)
        if resolution is None or resolution.expected_shape != "timestamp":
            continue
        rendered = _normalize_timestamp_fact(rendered, fact)
    return rendered


def _normalize_timestamp_fact(text: str, requested_fact: str) -> str:
    """Render numeric Unix timestamps as bounded UTC text.

    Ten-digit values are treated as Unix seconds and thirteen-digit values as Unix
    milliseconds. Other numeric widths are left unchanged rather than guessed.
    """

    pattern = re.compile(
        rf"(?P<prefix>{re.escape(requested_fact)}:\s*)"
        r"(?P<value>-?\d{10}|-?\d{13})"
        r"(?P<suffix>(?=[.;]|$))",
        re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        raw = match.group("value")
        try:
            numeric = int(raw)
            seconds = numeric / 1000 if len(raw.lstrip("-")) == 13 else numeric
            value = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return match.group(0)
        return f"{match.group('prefix')}{value:%Y-%m-%d %H:%M:%S} UTC"

    return pattern.sub(replace, text)
