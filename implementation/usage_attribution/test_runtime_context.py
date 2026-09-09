from usage_attribution.contracts import ActorType
from usage_attribution.factories import human_attribution, workload_attribution
from usage_attribution.runtime_context import (
    bind_attribution_context,
    current_attribution_context,
)
from usage_ledger.runtime_context import new_attempt_context


def test_human_attribution_projects_into_model_usage_context():
    context = human_attribution(
        organization_id="aot",
        correlation_id="corr-1",
        request_id="msg-1",
        principal_id="user-al",
        source_channel="teams",
        purpose="Resolve endpoint status",
        capability="conversation.reason",
        email_address="al@teamaot.com",
        workflow_id="conversation-1",
    )

    assert current_attribution_context() is None
    with bind_attribution_context(context):
        assert current_attribution_context() is context
        model = new_attempt_context()

    assert current_attribution_context() is None
    assert model.organization_id == "aot"
    assert model.request_id == "msg-1"
    assert model.workflow_id == "conversation-1"
    assert model.capability == "conversation.reason"
    assert model.routing_profile == "teams"
    assert model.metadata["correlation_id"] == "corr-1"
    assert model.metadata["actor_type"] == "human"
    assert model.metadata["actor_id"] == "user-al"
    assert model.metadata["email_address"] == "al@teamaot.com"
    assert model.metadata["purpose"] == "Resolve endpoint status"
    assert model.attempt_id


def test_workload_attribution_is_named_and_non_human():
    context = workload_attribution(
        organization_id="aot",
        correlation_id="corr-newman",
        request_id="run-1",
        workload_id="svc-newman",
        workload_name="Newman Email Monitor",
        source_channel="scheduler",
        purpose="Classify monitored email",
        capability="email.classification",
        actor_type=ActorType.SCHEDULED_PROCESS,
    )

    with bind_attribution_context(context):
        model = new_attempt_context()

    assert model.agent_name == "Newman Email Monitor"
    assert model.metadata["actor_type"] == "scheduled_process"
    assert model.metadata["workload_name"] == "Newman Email Monitor"
    assert model.metadata["source_channel"] == "scheduler"


def test_unbound_model_attempt_is_retained_as_attribution_gap(monkeypatch):
    monkeypatch.setenv("JASON_ORGANIZATION_ID", "aot")

    model = new_attempt_context()

    assert model.organization_id == "aot"
    assert model.workflow_id == "unattributed-runtime"
    assert model.capability == "unknown"
    assert model.routing_profile == "unattributed-runtime"
    assert model.metadata["actor_type"] == "unknown"
    assert model.metadata["actor_id"] == "unknown"
    assert model.metadata["attribution_quality"] == "unavailable"
    assert model.request_id.startswith("unattributed-")
    assert model.attempt_id
