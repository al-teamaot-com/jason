from dataclasses import dataclass

from connectors.core.contracts import ConnectorContext, ConnectorResult
from connectors.core.resource_gateway import ResourceOperation, ResourceQuery
from connectors.resource_convergence import GovernedResourceExecutor


@dataclass
class RecordingAutotaskConnector:
    provider_name: str = "autotask"
    capabilities = frozenset({"autotask.entity.get"})

    def __post_init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data={"item": {"id": 77}},
        )


def test_autotask_uses_same_generic_resource_executor_as_itglue_and_drmm() -> None:
    connector = RecordingAutotaskConnector()
    executor = GovernedResourceExecutor({"autotask": connector})
    query = ResourceQuery(
        provider="autotask",
        resource_type="entity",
        operation=ResourceOperation.GET,
        organization_id="aot",
        resource_id="77",
        filters={"entity": "ConfigurationItems"},
    )
    context = ConnectorContext(
        correlation_id="corr-cross-provider",
        principal_id="person-al",
        organization_id="aot",
        client_id="aot",
        capability="resource.convergence",
        mode="observe",
    )

    result = executor.execute(query, context)

    assert result.provider == "autotask"
    assert len(connector.requests) == 1
    request = connector.requests[0]
    assert request.context.correlation_id == "corr-cross-provider"
    assert request.context.principal_id == "person-al"
    assert request.context.organization_id == "aot"
    assert request.context.client_id == "aot"
    assert request.context.mode == "observe"
    assert request.context.capability == "autotask.entity.get"
    assert request.arguments == {
        "entity": "ConfigurationItems",
        "entity_id": "77",
    }
