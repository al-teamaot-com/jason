"""Owner-approved component contracts: no provider mutations or standing grant here."""

from __future__ import annotations

import pytest

from connectors.datto_rmm.component_execution import (
    ComponentAllowlistEntry,
    DattoRmmComponentExecutionPolicy,
    StaticComponentAllowlist,
)


RENAME = ("479d1a75-8f98-42b7-b6fb-408242bcc17e", "Change Hostname [WIN]")
BACKUP_LOGS = (
    "3770a86b-26d4-414f-a87c-87a0835f4278",
    "Datto Endpoint Backup: Retrieve Errors and Warnings from Logs [WIN]",
)
EVENT_LOGS = ("6725d709-f3b4-415f-b6f7-4185ebde71df", "AOT Event log search Ver09192024")


def prepare(identity: tuple[str, str], variables: dict):
    uid, name = identity
    entry = ComponentAllowlistEntry(
        allowlist_name="reviewed-per-run",
        canonical_component_id="reviewed-per-run",
        provider_component_uid=uid,
        display_name=name,
        allowed_target_classes=frozenset({"workstation"}),
        requires_per_run_approval=True,
    )
    policy = DattoRmmComponentExecutionPolicy(
        allowlist=StaticComponentAllowlist(entries=(entry,))
    )
    return policy.prepare(
        allowlist_name="reviewed-per-run",
        device_uid="device-123",
        device_class="workstation",
        component_uid=uid,
        variables=variables,
        observed_component_name=name,
    )


def test_no_reboot_hostname_is_normalized_into_only_one_quickjob_plan():
    p = prepare(RENAME, {"usrNewName": "AOT-50282", "usrReboot": False})
    assert p.normalized_variables == {"usrNewName": "AOT-50282", "usrReboot": "false"}
    assert p.provider_request.body["jobComponent"] == {
        "componentUid": RENAME[0],
        "variables": [
            {"name": "usrNewName", "value": "AOT-50282"},
            {"name": "usrReboot", "value": "false"},
        ],
    }


@pytest.mark.parametrize("enabled", [True, "true", "TRUE"])
def test_reboot_true_is_denied_even_with_exact_component_identity(enabled):
    with pytest.raises(PermissionError, match="value is not allowlisted"):
        prepare(RENAME, {"usrNewName": "AOT-50282", "usrReboot": enabled})


@pytest.mark.parametrize(
    "hostname",
    ["", "12345678", "-HOST", "HOST-", "HOST_NAME", "x" * 16, "PC;Restart-Computer"],
)
def test_unsafe_or_invalid_hostname_fails_closed(hostname):
    with pytest.raises(ValueError, match="hostname component variable is invalid"):
        prepare(RENAME, {"usrNewName": hostname, "usrReboot": False})


@pytest.mark.parametrize(
    "vars",
    [
        {"usrNewName": "AOT-50282"},
        {"usrReboot": False},
        {"usrNewName": "AOT-50282", "usrReboot": False, "force": "true"},
    ],
)
def test_no_reboot_rename_requires_both_inputs_and_rejects_unknown(vars):
    with pytest.raises((ValueError, PermissionError)):
        prepare(RENAME, vars)


def test_unapproved_component_uid_does_not_inherit_hostname_variable_contract():
    changed_uid = ("12345678-0000-0000-0000-000000000001", RENAME[1])
    with pytest.raises(PermissionError, match="source-locked component identity mismatch"):
        prepare(changed_uid, {"usrNewName": "AOT-50282", "usrReboot": False})


def test_unapproved_component_name_does_not_inherit_hostname_variable_contract():
    changed_name = (RENAME[0], "Change Hostname [WIN] renamed")
    with pytest.raises(PermissionError, match="source-locked component identity mismatch"):
        prepare(changed_name, {"usrNewName": "AOT-50282", "usrReboot": False})


def test_backup_log_diagnostic_fixes_bounds_and_prevents_support_detail():
    p = prepare(BACKUP_LOGS, {"usrMaxResults": "50", "usrAdditionalInfo": False})
    assert p.normalized_variables == {"usrMaxResults": "50", "usrAdditionalInfo": "false"}


@pytest.mark.parametrize("vars", [
    {"usrMaxResults": "50", "usrAdditionalInfo": True},
    {"usrMaxResults": "300", "usrAdditionalInfo": False},
    {"usrMaxResults": "999", "usrAdditionalInfo": False},
    {"usrMaxResults": "50"},
])
def test_backup_log_diagnostic_rejects_expanded_or_missing_inputs(vars):
    with pytest.raises((PermissionError, ValueError)):
        prepare(BACKUP_LOGS, vars)


def test_event_log_diagnostic_accepts_bounded_literal_term_and_days():
    p = prepare(EVENT_LOGS, {"SearchTerm": "VSS 1001", "DaysBack": "7"})
    assert p.normalized_variables == {"SearchTerm": "VSS 1001", "DaysBack": "7"}


@pytest.mark.parametrize("vars", [
    {"SearchTerm": "VSS", "DaysBack": "365"},
    {"SearchTerm": "VSS; whoami", "DaysBack": "7"},
    {"SearchTerm": "'; Remove-Item", "DaysBack": "7"},
    {"SearchTerm": "VSS", "DaysBack": "0"},
    {"SearchTerm": "VSS"},
])
def test_event_log_diagnostic_rejects_unbounded_windows_or_expression_syntax(vars):
    with pytest.raises((PermissionError, ValueError)):
        prepare(EVENT_LOGS, vars)



def test_runtime_variable_policy_cannot_override_source_locked_no_reboot():
    from connectors.datto_rmm.component_execution import ComponentVariablePolicy

    entry = ComponentAllowlistEntry(
        allowlist_name="reviewed-per-run",
        canonical_component_id="owner-approved-rename",
        provider_component_uid=RENAME[0],
        display_name=RENAME[1],
        allowed_target_classes=frozenset({"workstation"}),
        variable_policies=(
            ComponentVariablePolicy(name="usrNewName", variable_type="string"),
            ComponentVariablePolicy(name="usrReboot", variable_type="boolean"),
        ),
    )
    policy = DattoRmmComponentExecutionPolicy(
        allowlist=StaticComponentAllowlist(entries=(entry,))
    )
    with pytest.raises(PermissionError, match="value is not allowlisted"):
        policy.prepare(
            allowlist_name="reviewed-per-run",
            device_uid="device-123",
            device_class="workstation",
            component_uid=RENAME[0],
            variables={"usrNewName": "AOT-50282", "usrReboot": True},
            observed_component_name=RENAME[1],
        )


@pytest.mark.parametrize("identity", [BACKUP_LOGS, EVENT_LOGS])
def test_source_locked_diagnostics_reject_runtime_variable_policy_override(identity):
    from connectors.datto_rmm.component_execution import ComponentVariablePolicy

    entry = ComponentAllowlistEntry(
        allowlist_name="reviewed-per-run",
        canonical_component_id="reviewed-logs",
        provider_component_uid=identity[0],
        display_name=identity[1],
        allowed_target_classes=frozenset({"workstation"}),
        variable_policies=(
            ComponentVariablePolicy(name="usrAdditionalInfo", variable_type="boolean"),
            ComponentVariablePolicy(name="DaysBack", variable_type="string"),
            ComponentVariablePolicy(name="SearchTerm", variable_type="string"),
            ComponentVariablePolicy(name="usrMaxResults", variable_type="string"),
        ),
    )
    policy = DattoRmmComponentExecutionPolicy(
        allowlist=StaticComponentAllowlist(entries=(entry,))
    )
    with pytest.raises(PermissionError, match="value is not allowlisted"):
        policy.prepare(
            allowlist_name="reviewed-per-run",
            device_uid="device-123",
            device_class="workstation",
            component_uid=identity[0],
            variables=(
                {"usrAdditionalInfo": True, "usrMaxResults": "50"}
                if identity == BACKUP_LOGS
                else {"SearchTerm": "VSS", "DaysBack": "365"}
            ),
            observed_component_name=identity[1],
        )


def test_source_locked_resolution_rejects_any_partial_identity_collision():
    from connectors.datto_rmm.source_component_contracts import (
        resolve_source_component_contract,
    )

    assert resolve_source_component_contract(*RENAME) is not None
    assert resolve_source_component_contract("unrelated-uid", "Unrelated component") is None
    with pytest.raises(PermissionError, match="source-locked component identity mismatch"):
        resolve_source_component_contract(RENAME[0], "Different component")
    with pytest.raises(PermissionError, match="source-locked component identity mismatch"):
        resolve_source_component_contract("different-uid", RENAME[1])


def test_source_locked_contract_pattern_is_reusable_for_unrelated_component():
    from connectors.datto_rmm.source_component_contracts import (
        SourceComponentContract,
        resolve_source_component_contract,
    )
    from connectors.datto_rmm.component_execution import ComponentVariablePolicy

    arbitrary_diagnostic = SourceComponentContract(
        uid="vendor-opaque-uid-new",
        name="Future Safe Diagnostic",
        variables=({"name": "IncludeSecrets", "variable_type": "boolean",
                    "required": True, "allowed_values": ("false",)},),
    )
    matched = resolve_source_component_contract(
        arbitrary_diagnostic.uid, arbitrary_diagnostic.name,
        contracts=(arbitrary_diagnostic,),
    )
    assert matched is arbitrary_diagnostic
    field = ComponentVariablePolicy(**matched.variables[0])
    assert DattoRmmComponentExecutionPolicy._normalize_variable_value(field, False) == "false"
    with pytest.raises(PermissionError, match="value is not allowlisted"):
        DattoRmmComponentExecutionPolicy._normalize_variable_value(field, True)




ZERO_INPUT_DIAGNOSTICS = (
    ("c97df7f4-ae3d-4b8c-aae3-68accc68144f",
     "Comprehensive Disk & Storage Diagnostic [WIN] AOT Ver 07232026"),
    ("44f11fd8-2d3c-4afb-8f7d-571afb9c602e",
     "Proactive Event Log Health Diagnostic [WIN] AOT Ver 05082026-1"),
    ("197aeab0-4baa-4b69-aa86-adf98e99f5c9",
     "Check Shadow Copy Health & Configuration AOT Ver 12112025-1"),
    ("426b9194-16c4-47a1-87f7-14035a097e3b",
     "Check Unexpected Shutdown Automated Diagnostic Collector AOT Ver 12122025-1"),
    ("d118f181-5234-444a-b3fb-823a76660352",
     "Check RDP Status [WIN] AOT Ver 05062026-1"),
    ("98051f7d-b8e8-41ca-8fa1-5cc64a199375",
     "Check Boot Time [WIN] AOT Ver 11152025-1"),
    ("e68e5a4c-1b7d-4e20-9d72-4090d5f10244",
     "OneDrive Comprehensive Diagnostic [WIN] AOT Ver 10082026-1"),
    ("f866e3b9-57af-4a94-b9cc-53811a08e1e1",
     "Get-VulScan Discovery Agent Service Status AOT"),
)


@pytest.mark.parametrize("identity", ZERO_INPUT_DIAGNOSTICS)
def test_zero_input_diagnostics_accept_empty_variables_only(identity):
    prepared = prepare(identity, {})
    assert prepared.normalized_variables == {}
    assert prepared.provider_request.body["jobComponent"]["variables"] == []
    with pytest.raises(PermissionError, match="component variable is not approved"):
        prepare(identity, {"UnexpectedInput": "yes"})


@pytest.mark.parametrize("identity", ZERO_INPUT_DIAGNOSTICS)
def test_zero_input_diagnostics_reject_identity_drift(identity):
    with pytest.raises(PermissionError, match="source-locked component identity mismatch"):
        prepare(("unapproved-uid", identity[1]), {})
    with pytest.raises(PermissionError, match="source-locked component identity mismatch"):
        prepare((identity[0], "Renamed component"), {})


@pytest.mark.parametrize("identity", ZERO_INPUT_DIAGNOSTICS)
def test_zero_input_diagnostics_ignore_runtime_variable_expansion(identity):
    from connectors.datto_rmm.component_execution import ComponentVariablePolicy

    entry = ComponentAllowlistEntry(
        allowlist_name="reviewed-per-run",
        canonical_component_id="reviewed-per-run",
        provider_component_uid=identity[0],
        display_name=identity[1],
        allowed_target_classes=frozenset({"workstation"}),
        variable_policies=(ComponentVariablePolicy(name="Dangerous", required=True),),
        requires_per_run_approval=True,
    )
    policy = DattoRmmComponentExecutionPolicy(
        allowlist=StaticComponentAllowlist(entries=(entry,))
    )
    with pytest.raises(PermissionError, match="component variable is not approved"):
        policy.prepare(
            allowlist_name="reviewed-per-run",
            device_uid="device-123",
            device_class="workstation",
            component_uid=identity[0],
            variables={"Dangerous": "true"},
            observed_component_name=identity[1],
        )
    planned = policy.prepare(
        allowlist_name="reviewed-per-run",
        device_uid="device-123",
        device_class="workstation",
        component_uid=identity[0],
        variables={},
        observed_component_name=identity[1],
    )
    assert planned.normalized_variables == {}

def test_source_locked_contract_registry_is_unambiguous():
    from connectors.datto_rmm.source_component_contracts import SOURCE_COMPONENT_CONTRACTS

    uids = [contract.uid for contract in SOURCE_COMPONENT_CONTRACTS]
    names = [contract.name.casefold() for contract in SOURCE_COMPONENT_CONTRACTS]
    assert len(uids) == len(set(uids))
    assert len(names) == len(set(names))
