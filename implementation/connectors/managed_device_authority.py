from __future__ import annotations

from dataclasses import dataclass

from connectors.resource_convergence import IdentityEvidence, ResourceConvergenceError


DATTO_MANAGED_DEVICE_AUTHORITY = "datto_rmm:managed-device-authority"
IT_GLUE_DEVICE_DOCUMENTATION_AUTHORITY = "it_glue:documentation-observation"


@dataclass(frozen=True, slots=True)
class ManagedDeviceAuthorityDecision:
    """Record the authoritative provider observation for an RMM-managed device.

    Datto RMM establishes managed-device existence and provider identity for the
    managed endpoint domain. Jason still owns the provider-independent canonical
    object identifier and all governed cross-provider mappings.
    """

    device: IdentityEvidence
    authoritative_provider: str = "datto_rmm"
    authority_scope: str = "rmm_managed_device_identity_and_operational_state"


def establish_managed_device_authority(
    device: IdentityEvidence,
) -> ManagedDeviceAuthorityDecision:
    """Validate a Datto observation as the authoritative managed-device source.

    This does not create a Jason canonical object, grant execution authority, or
    assert that any IT Glue configuration represents the device.
    """

    if device.provider != "datto_rmm":
        raise ResourceConvergenceError(
            "managed-device authority requires a Datto RMM observation"
        )
    if device.resource_type != "device":
        raise ResourceConvergenceError(
            "managed-device authority requires device evidence"
        )
    if not device.external_id.strip():
        raise ResourceConvergenceError(
            "managed-device authority requires a stable Datto device identifier"
        )
    if not device.organization_id.strip():
        raise ResourceConvergenceError(
            "managed-device authority requires organization context"
        )
    if device.source_authority != DATTO_MANAGED_DEVICE_AUTHORITY:
        raise ResourceConvergenceError(
            "Datto device evidence is not marked with managed-device authority"
        )

    return ManagedDeviceAuthorityDecision(device=device)
