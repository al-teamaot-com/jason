from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pytest

from orchestrator.contracts import ExecutionStage, OrchestrationResult, OrchestrationStatus
from orchestrator.dynamic_resource_response import (
    DynamicEvidenceReasoner,
    GovernedDynamicTeamsResourceResponseRenderer,
)
from orchestrator.teams_conversation_flow import ConversationIntent


@dataclass
class FakeClient:
    response: Mapping[str, Any]
    calls: list[Mapping[str, Any]]

    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def result(data: Any) -> OrchestrationResult:
    return OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="endpoint.device.read",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("completed",),
        resolution=None,
        output={"provider": "datto_rmm", "data": data},
        provider_id="datto_rmm",
        attempts=1,
    )


def intent(question: str) -> ConversationIntent:
    return ConversationIntent(
        capability_name="endpoint.device.read",
        arguments={"hostname": "AOT-50107", "requested_facts": [question]},
        permission_mode="observe",
    )


def test_renders_only_dereferenced_selected_provider_value() -> None:
    client = FakeClient(
        {"answer_type": "direct", "evidence_paths": ["/lastBoot"]}
    )
    renderer = GovernedDynamicTeamsResourceResponseRenderer(
        reasoner=DynamicEvidenceReasoner(client)
    )

    text = renderer.render(
        result({"hostname": "AOT-50107", "lastBoot": "2026-08-16T09:12:00Z"}),
        intent("When was AOT-50107 last rebooted?"),
    )

    assert text == "2026-08-16T09:12:00Z Source: datto_rmm."
    assert len(client.calls) == 1
    payload = client.calls[0]["user"]
    assert "When was AOT-50107 last rebooted?" in payload
    assert "/lastBoot" in payload


def test_evidence_prompt_omits_unselectable_object_scaffolding_and_bounds_previews() -> None:
    client = FakeClient(
        {"answer_type": "direct", "evidence_paths": ["/outer/inner/value"]}
    )
    renderer = GovernedDynamicTeamsResourceResponseRenderer(
        reasoner=DynamicEvidenceReasoner(client)
    )
    long_value = "x" * 300

    text = renderer.render(
        result({"outer": {"inner": {"value": long_value}}}),
        intent("Read the nested value."),
    )

    payload = client.calls[0]["user"]
    assert '"selectable":false' not in payload
    assert '"path":"/outer"' not in payload
    assert '"path":"/outer/inner"' not in payload
    assert '"path":"/outer/inner/value"' in payload
    assert "x" * 120 in payload
    assert "x" * 121 not in payload
    assert text.startswith(long_value)


def test_wrong_adjacent_value_is_not_hard_coded_or_substituted() -> None:
    client = FakeClient({"answer_type": "unavailable", "evidence_paths": []})
    renderer = GovernedDynamicTeamsResourceResponseRenderer(
        reasoner=DynamicEvidenceReasoner(client)
    )

    text = renderer.render(
        result({"hostname": "AOT-50107", "lastLoggedInUser": "AzureAD\\AlDavis"}),
        intent("When was AOT-50107 last rebooted?"),
    )

    assert "couldn't establish" in text
    assert "AlDavis" not in text


def test_model_cannot_return_unoffered_pointer() -> None:
    client = FakeClient(
        {"answer_type": "direct", "evidence_paths": ["/invented"]}
    )
    renderer = GovernedDynamicTeamsResourceResponseRenderer(
        reasoner=DynamicEvidenceReasoner(client)
    )

    with pytest.raises(PermissionError, match="unoffered path"):
        renderer.render(result({"hostname": "AOT-50107"}), intent("Who is logged in?"))


def test_redacted_secret_is_not_selectable() -> None:
    client = FakeClient({"answer_type": "unavailable", "evidence_paths": []})
    renderer = GovernedDynamicTeamsResourceResponseRenderer(
        reasoner=DynamicEvidenceReasoner(client)
    )

    text = renderer.render(
        result({"hostname": "AOT-50107", "api_token": "super-secret-token-value"}),
        intent("What token is configured?"),
    )

    catalog_payload = client.calls[0]["user"]
    assert "super-secret-token-value" not in catalog_payload
    assert "api_token" not in catalog_payload or "[REDACTED]" not in catalog_payload
    assert "couldn't establish" in text


def test_future_provider_field_requires_no_code_mapping() -> None:
    client = FakeClient(
        {"answer_type": "direct", "evidence_paths": ["/risk/events/0/severity"]}
    )
    renderer = GovernedDynamicTeamsResourceResponseRenderer(
        reasoner=DynamicEvidenceReasoner(client)
    )
    future = OrchestrationResult(
        execution_id="exec-2",
        correlation_id="corr-2",
        capability_name="identity.signin.risk.read",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("completed",),
        resolution=None,
        output={
            "provider": "future_identity_platform",
            "data": {"risk": {"events": [{"severity": "high"}]}},
        },
        provider_id="future_identity_platform",
        attempts=1,
    )
    future_intent = ConversationIntent(
        capability_name="identity.signin.risk.read",
        arguments={"requested_facts": ["Does that user have suspicious sign-ins?"]},
        permission_mode="observe",
    )

    text = renderer.render(future, future_intent)

    assert text == "high Source: future_identity_platform."


def test_provider_provenance_mismatch_fails_closed() -> None:
    bad = result({"hostname": "AOT-50107"})
    bad = OrchestrationResult(
        execution_id=bad.execution_id,
        correlation_id=bad.correlation_id,
        capability_name=bad.capability_name,
        status=bad.status,
        stage=bad.stage,
        reason_codes=bad.reason_codes,
        resolution=bad.resolution,
        output={"provider": "other", "data": {"hostname": "AOT-50107"}},
        provider_id="datto_rmm",
        attempts=1,
    )
    renderer = GovernedDynamicTeamsResourceResponseRenderer(
        reasoner=DynamicEvidenceReasoner(FakeClient({"answer_type": "unavailable", "evidence_paths": []}))
    )

    with pytest.raises(RuntimeError, match="provenance"):
        renderer.render(bad, intent("What is the hostname?"))
