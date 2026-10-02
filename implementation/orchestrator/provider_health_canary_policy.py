from __future__ import annotations

from typing import Any, Mapping
import os

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


PROVIDER_HEALTH_CANARY_ORGANIZATION_ENV = (
    "JASON_PROVIDER_HEALTH_CANARY_ORGANIZATION_ID"
)
PROVIDER_HEALTH_CANARY_PROVIDERS_ENV = (
    "JASON_PROVIDER_HEALTH_CANARY_PROVIDERS"
)


def provider_health_canary_organization_id(
    environment: Mapping[str, str] | None = None,
) -> str:
    env = os.environ if environment is None else environment
    value = str(
        env.get(PROVIDER_HEALTH_CANARY_ORGANIZATION_ENV, "")
    ).strip()
    if not value:
        raise ValueError(
            "provider health canary organization must be explicitly configured"
        )
    return value


def enabled_provider_health_canary_specs(
    environment: Mapping[str, str] | None = None,
) -> tuple[Mapping[str, Any], ...]:
    env = os.environ if environment is None else environment
    raw = str(env.get(PROVIDER_HEALTH_CANARY_PROVIDERS_ENV, "")).strip()
    if not raw:
        raise ValueError(
            "provider health canary provider set must be explicitly configured"
        )
    requested = {
        item.strip()
        for item in raw.split(",")
        if item.strip()
    }
    known = {str(item["provider_id"]) for item in PROVIDER_HEALTH_CANARY_SPECS}
    unknown = requested - known
    if unknown:
        raise ValueError(
            "provider health canary provider set contains unsupported providers: "
            + ",".join(sorted(unknown))
        )
    return tuple(
        item
        for item in PROVIDER_HEALTH_CANARY_SPECS
        if str(item["provider_id"]) in requested
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
        and request.organization_id
        == provider_health_canary_organization_id()
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
