"""Exact canary input binding; no provider transport or authority changes."""
from dataclasses import replace
import json
import pytest

from connectors.datto_rmm.component_execution import (
    ComponentAllowlistEntry, DattoRmmComponentExecutionPolicy, StaticComponentAllowlist,
)


UID = "6efeedfb-fc41-4cee-a499-3641efe056f4"
NAME = "AOT DEB Recovery - Native Read-Only Canary [WIN]"


def entry():
    return ComponentAllowlistEntry(
        allowlist_name="per-run-canary", canonical_component_id="deb.native-readonly",
        provider_component_uid=UID, display_name=NAME,
        allowed_target_classes=frozenset({"workstation"}),
        requires_per_run_approval=True,
    )


def prepare(component, variables, *, device_class="workstation"):
    return DattoRmmComponentExecutionPolicy(
        allowlist=StaticComponentAllowlist(entries=(component,))
    ).prepare(
        allowlist_name=component.allowlist_name, device_uid="synthetic-device",
        device_class=device_class, component_uid=component.provider_component_uid,
        variables=variables, observed_component_name=component.display_name,
    )


def test_exact_binding_only_serializes_bounded_profile_and_preserves_per_run_gate():
    profile=json.dumps({"hostname":"synthetic-host","agent_id":"synthetic-agent"})
    prepared=prepare(entry(), {"AOTDebCanaryProfile":profile})
    assert prepared.allowlist_entry.requires_per_run_approval is True
    assert prepared.provider_request.body["jobComponent"] == {
        "componentUid":UID, "variables":[{"name":"AOTDebCanaryProfile","value":profile}]}


@pytest.mark.parametrize('component', [
    replace(entry(),provider_component_uid="different-uid"),
    replace(entry(),display_name="Different component"),
    replace(entry(),display_name=NAME.lower()),
])
def test_contract_does_not_transfer_to_copied_or_renamed_component(component):
    with pytest.raises(PermissionError, match="variable is not approved"):
        prepare(component,{"AOTDebCanaryProfile":"{}"})


@pytest.mark.parametrize('variables', [
    {}, {"AOTDebCanaryProfile":"x"*4097}, {"AOTDebCanaryProfile":{}},
    {"AOTDebCanaryProfile":"{}","usrInput":"unapproved"},
])
def test_missing_oversized_structured_or_extra_inputs_fail_closed(variables):
    with pytest.raises((ValueError,PermissionError)):
        prepare(entry(),variables)


def test_variable_contract_does_not_expand_target_class():
    with pytest.raises(PermissionError,match="target device class"):
        prepare(entry(),{"AOTDebCanaryProfile":"{}"},device_class="unapproved")
