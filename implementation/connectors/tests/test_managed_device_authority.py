import pytest

from connectors.managed_device_authority import (
    DATTO_MANAGED_DEVICE_AUTHORITY,
    ManagedDeviceAuthorityDecision,
    establish_managed_device_authority,
)
from connectors.resource_convergence import IdentityEvidence, ResourceConvergenceError


def test_datto_device_establishes_managed_device_authority() -> None:
    device = IdentityEvidence(
        provider="datto_rmm",
        resource_type="device",
        external_id="device-123",
        organization_id="org-1",
        attributes={"hostname": "HOST-01"},
        source_authority=DATTO_MANAGED_DEVICE_AUTHORITY,
    )

    decision = establish_managed_device_authority(device)

    assert isinstance(decision, ManagedDeviceAuthorityDecision)
    assert decision.authoritative_provider == "datto_rmm"
    assert decision.authority_scope == "rmm_managed_device_identity_and_operational_state"
    assert decision.device is device


def test_it_glue_cannot_establish_managed_device_authority() -> None:
    configuration = IdentityEvidence(
        provider="it_glue",
        resource_type="configuration",
        external_id="cfg-1",
        organization_id="org-1",
        attributes={"name": "HOST-01"},
        source_authority="it_glue:documentation-observation",
    )

    with pytest.raises(ResourceConvergenceError, match="Datto RMM"):
        establish_managed_device_authority(configuration)


def test_datto_observation_requires_explicit_managed_device_authority_marker() -> None:
    device = IdentityEvidence(
        provider="datto_rmm",
        resource_type="device",
        external_id="device-123",
        organization_id="org-1",
        attributes={"hostname": "HOST-01"},
        source_authority="datto_rmm:governed-live-read",
    )

    with pytest.raises(ResourceConvergenceError, match="not marked"):
        establish_managed_device_authority(device)
