from __future__ import annotations

from dataclasses import dataclass

from .contracts import OrchestrationResult, OrchestrationStatus
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
                return decision
            return ConversationRenderDecision(
                text=self.resource_renderer.render(result, intent),
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
