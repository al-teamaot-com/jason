from dataclasses import dataclass

from orchestrator.governed_query import (
    GovernedQueryResult,
)
from orchestrator.semantic_query_planning import (
    UniversalSemanticQueryResolution,
)
from orchestrator.teams_conversation_experience import (
    TeamsConversationExperienceResult,
)
from orchestrator.universal_teams_query_flow import (
    UniversalTeamsQueryFlow,
    render_governed_query_result,
)


class FakeResolver:
    def __init__(self, resolution):
        self.resolution = resolution
        self.calls = []

    def resolve(
        self,
        *,
        human_text,
        universe,
    ):
        self.calls.append(
            (
                human_text,
                universe,
            )
        )
        return self.resolution


class FakeUniverse:
    def build(self):
        return "synthetic-universe"


class FakeFallback:
    def __init__(self):
        self.calls = []

    def handle(self, request):
        self.calls.append(request)

        return TeamsConversationExperienceResult(
            response_text="fallback",
            transport_message_id="m-1",
            correlation_id="c-1",
            orchestrations=(),
        )


@dataclass
class Request:
    text: str
    identity: object = None


def test_non_information_turn_falls_through_without_query_execution():
    fallback = FakeFallback()

    flow = UniversalTeamsQueryFlow(
        fallback=fallback,
        resolver=FakeResolver(
            UniversalSemanticQueryResolution(
                is_information_query=False,
                plan=None,
            )
        ),
        universe_builder=FakeUniverse(),
        coordinator=object(),
    )

    result = flow.handle(
        Request(
            text="unseen synthetic text"
        )
    )

    assert result.response_text == "fallback"
    assert len(fallback.calls) == 1


def test_scalar_result_rendering_is_deterministic():
    result = GovernedQueryResult(
        columns=("value",),
        rows=(
            {
                "value": 17,
            },
        ),
        source_aliases=("r",),
        evidence_references=(
            "evidence:1",
        ),
    )

    assert (
        render_governed_query_result(
            result=result,
            answer_mode="scalar",
        )
        == "17"
    )


def test_boolean_result_rendering_is_deterministic():
    result = GovernedQueryResult(
        columns=("matched",),
        rows=(
            {
                "matched": True,
            },
        ),
        source_aliases=("r",),
        evidence_references=(
            "evidence:1",
        ),
    )

    assert (
        render_governed_query_result(
            result=result,
            answer_mode="boolean",
        )
        == "Yes."
    )


def test_multirow_rendering_requires_no_language_model():
    result = GovernedQueryResult(
        columns=(
            "name",
            "metric",
        ),
        rows=(
            {
                "name": "alpha",
                "metric": 9,
            },
            {
                "name": "beta",
                "metric": 5,
            },
        ),
        source_aliases=("r",),
        evidence_references=(
            "evidence:1",
            "evidence:2",
        ),
    )

    rendered = (
        render_governed_query_result(
            result=result,
            answer_mode="table",
        )
    )

    assert "alpha" in rendered
    assert "beta" in rendered
    assert "9" in rendered
    assert "5" in rendered
