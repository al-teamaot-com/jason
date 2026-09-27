from __future__ import annotations

from typing import Any, Mapping

from .contracts import OrchestrationMode, OrchestrationRequest

PROVIDER_HEALTH_CANARY_PRINCIPAL = "jason-provider-canary"
PROVIDER_HEALTH_CANARY_POLICY_ID = "provider-health-canary-v1"
PROVIDER_HEALTH_CANARY_SENTINEL = "__jason_provider_canary_nonexistent__"

PROVIDER_HEALTH_CANARY_SPECS = (
    {
        "provider_id": "autotask",
        "capability_name": "service.company.search",
        "arguments": {
            "name": PROVIDER_HEALTH_CANARY_SENTINEL,
            "page_size": 1,
        },
    },
    {
        "provider_id": "it_glue",
        "capability_name": "documentation.organization.search",
        "arguments": {
            "name": PROVIDER_HEALTH_CANARY_SENTINEL,
            "page_size": 1,
        },
    },
    {
        "provider_id": "datto_rmm",
        "capability_name": "endpoint.device.search",
        "arguments": {
            "hostname": PROVIDER_HEALTH_CANARY_SENTINEL,
            "max": 2,
        },
    },
    {
        "provider_id": "microsoft_graph",
        "capability_name": "identity.user.search",
        "arguments": {
            "display_name": PROVIDER_HEALTH_CANARY_SENTINEL,
            "page_size": 1,
        },
    },
)

PROVIDER_HEALTH_CANARY_CAPABILITIES = frozenset(
    item["capability_name"] for item in PROVIDER_HEALTH_CANARY_SPECS
)


def expected_canary_arguments(capability_name: str) -> Mapping[str, Any] | None:
    for item in PROVIDER_HEALTH_CANARY_SPECS:
        if item["capability_name"] == capability_name:
            return item["arguments"]
    return None


def is_provider_health_canary_request(
    *,
    request: OrchestrationRequest,
    capability_name: str,
) -> bool:
    expected = expected_canary_arguments(capability_name)
    return bool(
        expected is not None
        and request.principal_id == PROVIDER_HEALTH_CANARY_PRINCIPAL
        and request.organization_id == "aot"
        and request.client_id is None
        and request.requester_kind == "service"
        and request.permission_mode == "observe"
        and request.authority_allowed
        and request.authority_context_id
        and request.orchestration_mode is OrchestrationMode.EXECUTE
        and PROVIDER_HEALTH_CANARY_POLICY_ID in request.policy_ids
        and dict(request.arguments) == dict(expected)
    )


def provider_health_canary_output_is_empty(
    *,
    output: Mapping[str, Any],
) -> bool:
    data = output.get("data")
    if isinstance(data, list):
        return len(data) == 0
    if not isinstance(data, Mapping):
        return False

    for key in ("items", "data", "results", "value", "devices"):
        value = data.get(key)
        if isinstance(value, list):
            return len(value) == 0

    return False
