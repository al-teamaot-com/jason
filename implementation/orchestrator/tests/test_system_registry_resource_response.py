from __future__ import annotations

from orchestrator.contracts import ExecutionStage, OrchestrationResult, OrchestrationStatus
from orchestrator.resource_evidence import (
    GovernedResourceEvidenceInterpreter,
    GovernedTeamsResourceResponseRenderer,
)
from orchestrator.teams_conversation_flow import ConversationIntent


class Reasoner:
    def __init__(self, proposals):
        self.proposals = proposals

    def locate(self, *, requested_facts, data):
        return self.proposals


def result(matches):
    return OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="system.registry.search",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("capability_completed",),
        resolution=None,
        output={
            "provider": "system_registry",
            "data": {"match_count": len(matches), "resource_matches": matches},
        },
        attempts=1,
        provider_id="system_registry",
    )


def intent(*, arguments):
    return ConversationIntent(
        capability_name="system.registry.search",
        arguments=arguments,
        execution_mode="deterministic",
        permission_mode="observe",
    )


def test_unique_registry_search_renders_structured_dependency_evidence():
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(
            Reasoner(
                [
                    {
                        "requested_fact": "dependencies",
                        "json_pointer": "/resource_matches/0/dependencies",
                    }
                ]
            )
        )
    )

    text = renderer.render(
        result(
            [
                {
                    "resource_id": "provider.datto-rmm",
                    "display_name": "Datto RMM Endpoint Provider",
                    "dependencies": [
                        "component.jason-runtime",
                        "credential.openbao.datto-rmm-readonly",
                    ],
                }
            ]
        ),
        intent(
            arguments={
                "name": "Datto RMM Endpoint Provider",
                "requested_facts": ("dependencies",),
            }
        ),
    )

    assert "component.jason-runtime" in text
    assert "credential.openbao.datto-rmm-readonly" in text
    assert "Source: system_registry" in text


def test_identity_like_registry_search_fails_closed_on_ambiguity():
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(Reasoner([]))
    )

    text = renderer.render(
        result(
            [
                {"resource_id": "provider.datto-rmm"},
                {"resource_id": "credential.openbao.datto-rmm-readonly"},
            ]
        ),
        intent(
            arguments={
                "query": "Datto RMM",
                "requested_facts": ("dependencies",),
            }
        ),
    )

    assert "ambiguous: 2 System Registry entities matched" in text
    assert "No entity was selected" in text
