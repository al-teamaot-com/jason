from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from kernel.identity_authority import AuthorityOutcome
from jason_runtime import teams_billing_delivery as module
import jason_runtime.teams_gateway_transport as transport_module


class Binding:
    status = "active"
    jason_identity_id = "person-tech"
    microsoft_object_id = "aad-tech"
    microsoft_tenant_id = "tenant-aot"


class LoriBinding:
    status = "active"
    jason_identity_id = "person-lori"
    microsoft_object_id = "aad-lori"
    microsoft_tenant_id = "tenant-aot"


class Bindings:
    def find_active_by_jason_identity(self, *, jason_identity_id):
        if jason_identity_id == "person-tech":
            return Binding()
        if jason_identity_id == "person-lori":
            return LoriBinding()
        return None

    def find_active_by_email(self, *, email_address):
        if email_address.casefold() == "lori@teamaot.com":
            return LoriBinding()
        return None


def request(**overrides):
    arguments = {
        "notification_kind": "technician_disposition",
        "recipient_identity_id": "person-tech",
        "text": "Hardware billing disposition needed.",
        "card": {"type": "AdaptiveCard", "version": "1.4", "body": []},
        "evidence_key": "submission:proc-1:ticket:123:product:456",
    }
    arguments.update(overrides.pop("arguments", {}))
    values = {
        "capability_name": module.CAPABILITY,
        "principal_id": module.AUDIT_WORKER_ID,
        "organization_id": "aot",
        "client_id": None,
        "permission_mode": "execute",
        "arguments": arguments,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def resolution():
    return SimpleNamespace(selected_provider_id=module.PROVIDER)


def test_billing_notification_foundation_is_dormant_without_procurement_profiles():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop(module.AUTOTASK_PROCUREMENT_PROFILE_ENV, None)
        os.environ.pop(module.PROCUREMENT_WEB_READ_PROFILE_ENV, None)
        active = module.register_foundation(
            capabilities=capabilities,
            providers=providers,
            now=datetime.now(timezone.utc),
        )

    assert active is False
    assert (
        capabilities.get(
            capability_name=module.CAPABILITY,
            version="1.0",
        ).lifecycle_status.value
        == "building"
    )


def test_exact_procurement_profiles_activate_billing_notification():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    with patch.dict(
        os.environ,
        {
            module.AUTOTASK_PROCUREMENT_PROFILE_ENV: module.AUTOTASK_PROCUREMENT_PROFILE,
            module.PROCUREMENT_WEB_READ_PROFILE_ENV: module.PROCUREMENT_WEB_READ_PROFILE,
        },
    ):
        active = module.register_foundation(
            capabilities=capabilities,
            providers=providers,
            now=datetime.now(timezone.utc),
        )

    assert active is True
    assert (
        capabilities.get_current(
            capability_name=module.CAPABILITY
        ).lifecycle_status.value
        == "active"
    )


def test_invoker_binds_exact_recipient_kind_and_evidence_before_send(tmp_path, monkeypatch):
    token = tmp_path / "token"
    token.write_text("synthetic-token", encoding="utf-8")
    invoker = module.BillingNotificationTeamsInvoker(
        gateway_url="http://teams-gateway:3979",
        token_file=token,
        bindings=Bindings(),
    )
    calls = []
    monkeypatch.setattr(
        transport_module,
        "urlopen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    prepared = invoker.prepare_execution_plan(
        request=request(),
        resolution=resolution(),
    )

    assert calls == []
    assert prepared.plan.canonical_capability == module.CAPABILITY
    assert prepared.plan.resource_identifier == "tenant-aot:aad-tech"
    assert (
        prepared.plan.material_parameters["notification_kind"]
        == "technician_disposition"
    )
    assert (
        prepared.plan.material_parameters["evidence_key"]
        == "submission:proc-1:ticket:123:product:456"
    )
    assert (
        prepared.plan.symbolic_resolutions["recipient_jason_identity"]
        == "person-tech"
    )
    assert "synthetic-token" not in repr(prepared)


def test_wrong_workload_cannot_use_billing_notification(tmp_path):
    token = tmp_path / "token"
    token.write_text("synthetic-token", encoding="utf-8")
    invoker = module.BillingNotificationTeamsInvoker(
        gateway_url="http://teams-gateway:3979",
        token_file=token,
        bindings=Bindings(),
    )
    with pytest.raises(PermissionError, match="billing-audit workload"):
        invoker.prepare_execution_plan(
            request=request(principal_id="jason-autonomy-worker"),
            resolution=resolution(),
        )


def test_tampered_billing_notification_plan_is_rejected_before_send(
    tmp_path, monkeypatch
):
    token = tmp_path / "token"
    token.write_text("synthetic-token", encoding="utf-8")
    invoker = module.BillingNotificationTeamsInvoker(
        gateway_url="http://teams-gateway:3979",
        token_file=token,
        bindings=Bindings(),
    )
    send_calls = []
    monkeypatch.setattr(
        transport_module,
        "urlopen",
        lambda *args, **kwargs: send_calls.append((args, kwargs)),
    )
    prepared = invoker.prepare_execution_plan(
        request=request(),
        resolution=resolution(),
    )
    tampered = replace(
        prepared,
        plan=replace(
            prepared.plan,
            resource_identifier="tenant-aot:aad-other",
        ),
    )

    with pytest.raises(PermissionError, match="execution plan changed"):
        invoker.invoke_execution_plan(
            request=request(),
            resolution=resolution(),
            prepared=tampered,
        )
    assert send_calls == []


class FakeCapabilities:
    def get_current(self, *, capability_name, allow_pilot):
        assert capability_name == module.CAPABILITY
        assert allow_pilot is False
        return SimpleNamespace(
            version="1.0",
            risk_level=SimpleNamespace(value="medium"),
            approval=SimpleNamespace(required=False),
        )


class FakeAuthority:
    def __init__(self):
        self.requests = []

    def evaluate(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            outcome=AuthorityOutcome.ALLOWED,
            reason_codes=("allowed",),
            execution_context=SimpleNamespace(context_id="ctx-billing-notify"),
        )


class FakeOrchestrator:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            status=SimpleNamespace(value="succeeded"),
            error_code=None,
            reason_codes=("completed",),
            output={"message_id": "teams-1"},
        )


def test_governed_port_requests_canonical_capability_not_teams_transport():
    authority = FakeAuthority()
    orchestrator = FakeOrchestrator()
    port = module.GovernedBillingAuditNotificationPort(
        authority=authority,
        capabilities=FakeCapabilities(),
        orchestrator=orchestrator,
        bindings=Bindings(),
    )

    message_id = port.technician(
        jason_identity_id="person-tech",
        text="Hardware billing disposition needed.",
        card={"type": "AdaptiveCard", "version": "1.4", "body": []},
        evidence_key="submission:proc-1:ticket:123:product:456",
    )

    assert message_id == "teams-1"
    assert len(orchestrator.requests) == 1
    outgoing = orchestrator.requests[0]
    assert outgoing.capability_name == module.CAPABILITY
    assert outgoing.principal_id == module.AUDIT_WORKER_ID
    assert outgoing.permission_mode == "execute"
    assert outgoing.arguments["recipient_identity_id"] == "person-tech"
    assert (
        outgoing.arguments["evidence_key"]
        == "submission:proc-1:ticket:123:product:456"
    )
