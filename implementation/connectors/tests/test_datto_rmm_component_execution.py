from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.core.mutations import ApprovalGrant
from connectors.datto_rmm.component_execution import (
    ComponentAllowlistEntry,
    ComponentVariablePolicy,
    DattoRmmComponentExecutionPolicy,
    StaticComponentAllowlist,
)
from connectors.datto_rmm.mutations import DattoRmmMutationConnector


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, context, dict(details)))


class ApprovalStore:
    def __init__(self, grant):
        self.grant = grant

    def resolve(self, approval_id, context):
        assert approval_id == self.grant.approval_id
        return self.grant

    def consume(self, approval_id, context):
        raise AssertionError("live execution is not configured, so approval must not be consumed")


def approved_component(*, status="active", fingerprint="metadata-sha256-1"):
    return ComponentAllowlistEntry(
        allowlist_name="read-only-diagnostics",
        canonical_component_id="diagnostics.network.readonly",
        display_name="Diagnostics - Network Read Only",
        provider_component_uid="component-uid-1",
        provider_metadata_fingerprint=fingerprint,
        allowed_target_classes=frozenset({"workstation", "server"}),
        variable_policies=(
            ComponentVariablePolicy(
                name="IncludeRoutes",
                variable_type="boolean",
                required=True,
            ),
            ComponentVariablePolicy(
                name="Scope",
                variable_type="selection",
                allowed_values=("basic", "extended"),
            ),
            ComponentVariablePolicy(
                name="RequestedDate",
                variable_type="date",
            ),
        ),
        status=status,
    )


def policy(*, entry=None):
    return DattoRmmComponentExecutionPolicy(
        allowlist=StaticComponentAllowlist(
            entries=(entry or approved_component(),)
        )
    )


def context(*, mode="propose", client_id="client-1"):
    return ConnectorContext(
        correlation_id="corr-component-1",
        principal_id="person-al",
        organization_id="aot",
        client_id=client_id,
        capability="datto_rmm.component.run",
        mode=mode,
    )


def arguments(**overrides):
    values = {
        "device_uid": "device-uid-1",
        "device_class": "workstation",
        "component_uid": "component-uid-1",
        "allowlist_name": "read-only-diagnostics",
        "observed_component_name": "Diagnostics - Network Read Only",
        "observed_metadata_fingerprint": "metadata-sha256-1",
        "variables": {
            "IncludeRoutes": True,
            "Scope": "basic",
            "RequestedDate": "2026-09-14",
        },
        "job_name": "Jason - Read Only Diagnostics",
        "reason": "Collect read-only evidence for ticket investigation",
    }
    values.update(overrides)
    return values


def test_quick_job_builder_matches_documented_datto_request_shape() -> None:
    prepared = policy().prepare(
        allowlist_name="read-only-diagnostics",
        device_uid="device-uid-1",
        device_class="workstation",
        component_uid="component-uid-1",
        variables={
            "Scope": "extended",
            "IncludeRoutes": False,
        },
        job_name="Jason - Diagnostic",
        observed_component_name="Diagnostics - Network Read Only",
        observed_metadata_fingerprint="metadata-sha256-1",
    )

    assert prepared.provider_request.method == "PUT"
    assert prepared.provider_request.path == "/api/v2/device/device-uid-1/quickjob"
    assert prepared.provider_request.body == {
        "jobName": "Jason - Diagnostic",
        "jobComponent": {
            "componentUid": "component-uid-1",
            "variables": [
                {"name": "IncludeRoutes", "value": "false"},
                {"name": "Scope", "value": "extended"},
            ],
        },
    }


def test_policy_rejects_component_not_in_exact_allowlist() -> None:
    with pytest.raises(PermissionError, match="component identity"):
        policy().prepare(
            allowlist_name="read-only-diagnostics",
            device_uid="device-uid-1",
            device_class="workstation",
            component_uid="unapproved-component",
            variables={"IncludeRoutes": True},
            observed_component_name="Diagnostics - Network Read Only",
            observed_metadata_fingerprint="metadata-sha256-1",
        )


def test_policy_rejects_component_metadata_drift() -> None:
    with pytest.raises(PermissionError, match="metadata fingerprint"):
        policy().prepare(
            allowlist_name="read-only-diagnostics",
            device_uid="device-uid-1",
            device_class="workstation",
            component_uid="component-uid-1",
            variables={"IncludeRoutes": True},
            observed_component_name="Diagnostics - Network Read Only",
            observed_metadata_fingerprint="changed-fingerprint",
        )


def test_policy_rejects_suspended_component() -> None:
    with pytest.raises(PermissionError, match="not active"):
        policy(entry=approved_component(status="suspended")).prepare(
            allowlist_name="read-only-diagnostics",
            device_uid="device-uid-1",
            device_class="workstation",
            component_uid="component-uid-1",
            variables={"IncludeRoutes": True},
        )


def test_policy_rejects_target_class_outside_allowlist() -> None:
    with pytest.raises(PermissionError, match="target device class"):
        policy().prepare(
            allowlist_name="read-only-diagnostics",
            device_uid="device-uid-1",
            device_class="network-device",
            component_uid="component-uid-1",
            variables={"IncludeRoutes": True},
            observed_metadata_fingerprint="metadata-sha256-1",
        )


def test_policy_rejects_unknown_or_invalid_variables() -> None:
    with pytest.raises(PermissionError, match="variable is not approved"):
        policy().prepare(
            allowlist_name="read-only-diagnostics",
            device_uid="device-uid-1",
            device_class="workstation",
            component_uid="component-uid-1",
            variables={"IncludeRoutes": True, "ArbitraryCommand": "whoami"},
            observed_metadata_fingerprint="metadata-sha256-1",
        )

    with pytest.raises(ValueError, match="required component variables"):
        policy().prepare(
            allowlist_name="read-only-diagnostics",
            device_uid="device-uid-1",
            device_class="workstation",
            component_uid="component-uid-1",
            variables={"Scope": "basic"},
            observed_metadata_fingerprint="metadata-sha256-1",
        )

    with pytest.raises(PermissionError, match="value is not allowlisted"):
        policy().prepare(
            allowlist_name="read-only-diagnostics",
            device_uid="device-uid-1",
            device_class="workstation",
            component_uid="component-uid-1",
            variables={"IncludeRoutes": True, "Scope": "unbounded"},
            observed_metadata_fingerprint="metadata-sha256-1",
        )


def test_support_261_drive_folder_size_exact_variables_are_allowed() -> None:
    entry = ComponentAllowlistEntry(
        allowlist_name="read-only-diagnostics",
        canonical_component_id="diagnostics.disk.folder-size",
        display_name="Drive or Folder Size Report - AOT Ver 11142024",
        provider_component_uid="8b7f7b3d-6462-40ca-9415-71232aecdb1f",
        allowed_target_classes=frozenset({"workstation"}),
    )
    prepared = policy(entry=entry).prepare(
        allowlist_name="read-only-diagnostics",
        device_uid="device-uid-1",
        device_class="workstation",
        component_uid=entry.provider_component_uid,
        variables={"RootFolder": "C:\\"},
        observed_component_name=entry.display_name,
    )

    assert prepared.normalized_variables == {"RootFolder": "C:\\"}
    assert prepared.provider_request.body["jobComponent"]["variables"] == [
        {"name": "RootFolder", "value": "C:\\"}
    ]


def test_support_261_bitlocker_exact_variables_are_normalized() -> None:
    entry = ComponentAllowlistEntry(
        allowlist_name="read-only-diagnostics",
        canonical_component_id="diagnostics.security.bitlocker-tpm",
        display_name="BitLocker & TPM Audit [WIN]",
        provider_component_uid="d9fdca0f-8659-4512-8086-88d631323b56",
        allowed_target_classes=frozenset({"workstation"}),
    )
    prepared = policy(entry=entry).prepare(
        allowlist_name="read-only-diagnostics",
        device_uid="device-uid-1",
        device_class="workstation",
        component_uid=entry.provider_component_uid,
        variables={
            "usrGetRecovery": False,
            "usrAlert": False,
            "usrUDF": "",
        },
        observed_component_name=entry.display_name,
    )

    assert prepared.normalized_variables == {
        "usrGetRecovery": "false",
        "usrAlert": "false",
        "usrUDF": "",
    }


def test_support_261_variable_contracts_do_not_transfer_to_changed_uid() -> None:
    entry = ComponentAllowlistEntry(
        allowlist_name="read-only-diagnostics",
        canonical_component_id="diagnostics.disk.folder-size",
        display_name="Drive or Folder Size Report - AOT Ver 11142024",
        provider_component_uid="different-component-uid",
        allowed_target_classes=frozenset({"workstation"}),
    )

    with pytest.raises(PermissionError, match="variable is not approved"):
        policy(entry=entry).prepare(
            allowlist_name="read-only-diagnostics",
            device_uid="device-uid-1",
            device_class="workstation",
            component_uid=entry.provider_component_uid,
            variables={"RootFolder": "C:\\"},
            observed_component_name=entry.display_name,
        )


def test_mutation_proposal_requires_allowlist_policy_and_client_scope() -> None:
    with pytest.raises(RuntimeError, match="allowlist policy is not configured"):
        DattoRmmMutationConnector(audit=Audit()).execute(
            ConnectorRequest(context=context(), arguments=arguments())
        )

    connector = DattoRmmMutationConnector(
        audit=Audit(),
        component_execution_policy=policy(),
    )
    with pytest.raises(PermissionError, match="client scope"):
        connector.execute(
            ConnectorRequest(
                context=context(client_id=None),
                arguments=arguments(),
            )
        )


def test_mutation_proposal_is_bound_to_reason_and_exact_provider_request() -> None:
    audit = Audit()
    connector = DattoRmmMutationConnector(
        audit=audit,
        component_execution_policy=policy(),
    )

    result = connector.execute(
        ConnectorRequest(context=context(), arguments=arguments())
    )

    assert result.data["status"] == "proposed"
    changes = result.data["plan"]["proposed_changes"]
    assert changes["component_name"] == "Diagnostics - Network Read Only"
    assert changes["variables"] == {
        "IncludeRoutes": "true",
        "Scope": "basic",
        "RequestedDate": "2026-09-14",
    }
    assert changes["reason"] == "Collect read-only evidence for ticket investigation"
    assert len(changes["provider_request_digest"]) == 64
    assert any(event[0] == "connector.mutation.planned" for event in audit.events)


def test_exact_approval_can_reach_only_disabled_execution_boundary() -> None:
    audit = Audit()
    proposer = DattoRmmMutationConnector(
        audit=audit,
        component_execution_policy=policy(),
    )
    proposed = proposer.execute(
        ConnectorRequest(context=context(), arguments=arguments())
    )
    now = datetime.now(timezone.utc)
    grant = ApprovalGrant(
        approval_id="approval-1",
        capability="datto_rmm.component.run",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-1",
        approved_by="owner-1",
        approved_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=5),
        argument_digest=proposed.data["argument_digest"],
    )
    executor = DattoRmmMutationConnector(
        audit=audit,
        approvals=ApprovalStore(grant),
        component_execution_policy=policy(),
    )

    execute_arguments = arguments(
        approval_id="approval-1",
        idempotency_key="idem-1",
    )
    with pytest.raises(RuntimeError, match="live mutation executor is not configured"):
        executor.execute(
            ConnectorRequest(
                context=context(mode="execute"),
                arguments=execute_arguments,
            )
        )


def test_approval_cannot_be_reused_after_reason_or_variables_change() -> None:
    proposer = DattoRmmMutationConnector(
        audit=Audit(),
        component_execution_policy=policy(),
    )
    proposed = proposer.execute(
        ConnectorRequest(context=context(), arguments=arguments())
    )
    now = datetime.now(timezone.utc)
    grant = ApprovalGrant(
        approval_id="approval-1",
        capability="datto_rmm.component.run",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-1",
        approved_by="owner-1",
        approved_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=5),
        argument_digest=proposed.data["argument_digest"],
    )
    executor = DattoRmmMutationConnector(
        audit=Audit(),
        approvals=ApprovalStore(grant),
        component_execution_policy=policy(),
    )

    with pytest.raises(ConnectorAuthorizationError, match="does not match"):
        executor.execute(
            ConnectorRequest(
                context=context(mode="execute"),
                arguments=arguments(
                    reason="Different reason after approval",
                    approval_id="approval-1",
                    idempotency_key="idem-1",
                ),
            )
        )

    with pytest.raises(ConnectorAuthorizationError, match="does not match"):
        executor.execute(
            ConnectorRequest(
                context=context(mode="execute"),
                arguments=arguments(
                    variables={
                        "IncludeRoutes": True,
                        "Scope": "extended",
                        "RequestedDate": "2026-09-14",
                    },
                    approval_id="approval-1",
                    idempotency_key="idem-2",
                ),
            )
        )
