"""Universal governed information-query front door for Teams.

Information questions are resolved before the legacy Conversation Kernel.

Pipeline:
    human text
      -> provider-neutral semantic resolver
      -> runtime-derived query universe
      -> governed cross-provider execution coordinator
      -> deterministic query result
      -> deterministic human-facing rendering

Non-information turns fall through to the existing Conversation Experience unchanged.

There are no provider names, connector names, operational fact mappings, human phrase
rules, or question-specific branches in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .governed_query import (
    GovernedQueryResult,
)
from .governed_query_execution import (
    GovernedQueryExecutionCoordinator,
)
from .query_source_discovery import (
    RuntimeSemanticQueryUniverseBuilder,
)
from .semantic_query_planning import (
    UniversalSemanticQueryResolver,
)
from .teams_conversation_experience import (
    BoundTeamsConversationIntentExecutor,
    TeamsConversationExperienceResult,
)
from .teams_conversation_flow import (
    TeamsConversationRequest,
)


@dataclass(frozen=True, slots=True)
class UniversalTeamsQueryFlow:
    """Route governed information queries through the generic query architecture."""

    fallback: Any
    resolver: UniversalSemanticQueryResolver
    universe_builder: RuntimeSemanticQueryUniverseBuilder
    coordinator: GovernedQueryExecutionCoordinator

    def handle(
        self,
        request: TeamsConversationRequest,
    ) -> TeamsConversationExperienceResult:
        question = request.text.strip()

        if not question:
            return self.fallback.handle(
                request
            )

        universe = (
            self.universe_builder.build()
        )

        semantic = self.resolver.resolve(
            human_text=question,
            universe=universe,
        )

        if not semantic.is_information_query:
            return self.fallback.handle(
                request
            )

        if semantic.plan is None:
            raise RuntimeError(
                "information resolution produced no semantic query plan"
            )

        principal = (
            self.fallback.identity_binder.bind(
                request.identity
            )
        )

        if principal is None:
            raise PermissionError(
                "Teams identity is not bound to "
                "a governed Jason principal"
            )

        correlation_id = (
            self.fallback.request_factory
            .new_correlation_id()
        )

        executor = (
            BoundTeamsConversationIntentExecutor(
                request_factory=(
                    self.fallback.request_factory
                ),
                orchestrator=(
                    self.fallback.orchestrator
                ),
                principal=principal,
                identity=request.identity,
                correlation_id=correlation_id,
            )
        )

        execution = (
            self.coordinator.execute(
                human_text=question,
                plan=semantic.plan,
                executor=executor,
            )
        )

        response_text = (
            render_governed_query_result(
                result=execution.query_result,
                answer_mode=(
                    semantic.plan.answer_mode
                ),
            )
        )

        if not response_text.strip():
            raise RuntimeError(
                "universal query produced "
                "empty human-facing text"
            )

        transport_message_id = (
            self.fallback.transport.send(
                conversation_id=(
                    request.identity.conversation_id
                ),
                text=response_text,
                correlation_id=(
                    correlation_id
                ),
            )
        )

        if not str(
            transport_message_id
        ).strip():
            raise RuntimeError(
                "Teams transport did not return "
                "a message identifier"
            )

        orchestrations = tuple(
            executor.results
        )

        if not orchestrations:
            raise RuntimeError(
                "information query produced no "
                "Central Orchestrator evidence"
            )

        return TeamsConversationExperienceResult(
            response_text=response_text,
            transport_message_id=str(
                transport_message_id
            ).strip(),
            correlation_id=correlation_id,
            orchestrations=orchestrations,
        )


def render_governed_query_result(
    *,
    result: GovernedQueryResult,
    answer_mode: str,
) -> str:
    """Render verified deterministic query output without another model call."""

    rows = tuple(
        result.rows
    )

    if answer_mode == "boolean":
        return _render_boolean(
            rows
        )

    if answer_mode == "scalar":
        return _render_scalar(
            rows
        )

    if not rows:
        return (
            "No matching governed evidence was found."
        )

    if answer_mode in {
        "table",
        "summary",
    }:
        return _render_rows(
            rows
        )

    raise ValueError(
        "unsupported governed query answer mode"
    )


def _render_boolean(
    rows: tuple[
        Mapping[str, Any],
        ...,
    ],
) -> str:
    if not rows:
        return "No."

    if (
        len(rows) == 1
        and len(rows[0]) == 1
    ):
        value = next(
            iter(
                rows[0].values()
            )
        )

        if isinstance(
            value,
            bool,
        ):
            return (
                "Yes."
                if value
                else "No."
            )

        if isinstance(
            value,
            (int, float),
        ):
            return (
                "Yes."
                if value != 0
                else "No."
            )

    return (
        "Yes."
        if bool(rows)
        else "No."
    )


def _render_scalar(
    rows: tuple[
        Mapping[str, Any],
        ...,
    ],
) -> str:
    if not rows:
        return "No matching governed evidence was found."

    if (
        len(rows) == 1
        and len(rows[0]) == 1
    ):
        value = next(
            iter(
                rows[0].values()
            )
        )
        return _display_value(
            value
        )

    return _render_rows(
        rows
    )


def _render_rows(
    rows: tuple[
        Mapping[str, Any],
        ...,
    ],
) -> str:
    if not rows:
        return "No matching governed evidence was found."

    if len(rows) == 1:
        row = rows[0]

        return "; ".join(
            f"{_display_name(name)}: "
            f"{_display_value(value)}"
            for name, value
            in row.items()
        )

    lines = []

    for index, row in enumerate(
        rows,
        start=1,
    ):
        rendered = "; ".join(
            f"{_display_name(name)}: "
            f"{_display_value(value)}"
            for name, value
            in row.items()
        )

        lines.append(
            f"{index}. {rendered}"
        )

    return "\n".join(
        lines
    )


def _display_name(
    value: str,
) -> str:
    return (
        value.replace(
            "_",
            " ",
        )
        .replace(
            ".",
            " ",
        )
        .strip()
    )


def _display_value(
    value: Any,
) -> str:
    if value is None:
        return "unavailable"

    if isinstance(
        value,
        bool,
    ):
        return (
            "yes"
            if value
            else "no"
        )

    return str(
        value
    )
