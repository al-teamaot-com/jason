from types import SimpleNamespace

from orchestrator.contracts import OrchestrationMode
from orchestrator.provider_health_canary_policy import (
    PROVIDER_HEALTH_CANARY_POLICY_ID,
    PROVIDER_HEALTH_CANARY_PRINCIPAL,
    PROVIDER_HEALTH_CANARY_SENTINEL,
    is_provider_health_canary_request,
    provider_health_canary_output_is_empty,
)


def request(**overrides):
    values = {
        "principal_id": PROVIDER_HEALTH_CANARY_PRINCIPAL,
        "organization_id": "org-test",
        "client_id": None,
        "requester_kind": "service",
        "permission_mode": "observe",
        "authority_allowed": True,
        "authority_context_id": "ctx-canary",
        "orchestration_mode": OrchestrationMode.EXECUTE,
        "policy_ids": (PROVIDER_HEALTH_CANARY_POLICY_ID,),
        "arguments": {
            "name": PROVIDER_HEALTH_CANARY_SENTINEL,
            "page_size": 1,
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_exact_autotask_canary_request_is_allowed(monkeypatch):
    monkeypatch.setenv(
        "JASON_PROVIDER_HEALTH_CANARY_ORGANIZATION_ID",
        "org-test",
    )
    assert is_provider_health_canary_request(
        request=request(),
        capability_name="service.company.search",
    )


def test_real_selector_cannot_use_canary_policy(monkeypatch):
    monkeypatch.setenv(
        "JASON_PROVIDER_HEALTH_CANARY_ORGANIZATION_ID",
        "org-test",
    )
    assert not is_provider_health_canary_request(
        request=request(
            arguments={"name": "Real Customer", "page_size": 1},
        ),
        capability_name="service.company.search",
    )


def test_wrong_principal_cannot_use_canary_policy(monkeypatch):
    monkeypatch.setenv(
        "JASON_PROVIDER_HEALTH_CANARY_ORGANIZATION_ID",
        "org-test",
    )
    assert not is_provider_health_canary_request(
        request=request(principal_id="person-owner"),
        capability_name="service.company.search",
    )


def test_only_empty_provider_output_is_canary_releasable():
    assert provider_health_canary_output_is_empty(
        output={"data": {"items": []}}
    )
    assert provider_health_canary_output_is_empty(
        output={"data": {"data": []}}
    )
    assert not provider_health_canary_output_is_empty(
        output={"data": {"items": [{"id": 1}]}}
    )
    assert not provider_health_canary_output_is_empty(
        output={"data": {"unexpected": "shape"}}
    )


def test_wrong_organization_cannot_use_canary_policy(monkeypatch):
    monkeypatch.setenv(
        "JASON_PROVIDER_HEALTH_CANARY_ORGANIZATION_ID",
        "org-test",
    )
    assert not is_provider_health_canary_request(
        request=request(organization_id="other-org"),
        capability_name="service.company.search",
    )
