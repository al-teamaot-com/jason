from __future__ import annotations

from dataclasses import dataclass


DATTO_RMM_READONLY_LOGICAL_SECRET = "datto_rmm.readonly"
DATTO_RMM_EXECUTION_LOGICAL_SECRET = "datto_rmm.execution"

# Datto RMM API v2 documents these as the minimum API Security Level
# permissions for PUT /v2/device/{deviceUid}/quickjob.  Device Visibility and
# API Component Level are independent global restrictions and are validated
# separately below.
REQUIRED_QUICK_JOB_API_PERMISSIONS = frozenset(
    {
        "sites.sites.view",
        "sites.devices.manage",
        "jobs.active_jobs.manage",
        "components.components.view",
    }
)


@dataclass(frozen=True, slots=True)
class DattoRmmExecutionIdentityContainment:
    """Source-of-truth containment contract for the future Datto execution identity.

    This object describes the provider-side boundary that must be proven before a
    write-capable credential may be consumed by Jason. It does not load secrets,
    change Datto configuration, register an execution capability, or issue network
    requests.
    """

    provider_identity_name: str
    security_level_name: str
    device_visibility_scope: tuple[str, ...]
    component_allowlist: tuple[str, ...]
    api_security_permissions: frozenset[str] = REQUIRED_QUICK_JOB_API_PERMISSIONS
    logical_secret: str = DATTO_RMM_EXECUTION_LOGICAL_SECRET
    provider_identity_distinct_from_readonly: bool = True
    quick_job_execution_allowed: bool = True
    user_administration_allowed: bool = False
    site_administration_allowed: bool = False
    policy_administration_allowed: bool = False
    component_administration_allowed: bool = False
    unrestricted_device_visibility: bool = False

    def validate(self) -> None:
        if self.logical_secret != DATTO_RMM_EXECUTION_LOGICAL_SECRET:
            raise ValueError("Datto execution identity must use datto_rmm.execution")
        if self.logical_secret == DATTO_RMM_READONLY_LOGICAL_SECRET:
            raise ValueError("Datto execution identity may not reuse the read-only secret")
        if not self.provider_identity_distinct_from_readonly:
            raise ValueError("Datto execution identity must be distinct from the read-only identity")
        if not self.provider_identity_name.strip():
            raise ValueError("provider identity name is required")
        if not self.security_level_name.strip():
            raise ValueError("security level name is required")
        if not self.quick_job_execution_allowed:
            raise ValueError("execution identity must be capable of the approved quick-job operation")
        if self.api_security_permissions != REQUIRED_QUICK_JOB_API_PERMISSIONS:
            raise ValueError("Datto execution API Security Level must match the minimum quick-job permissions exactly")
        if self.unrestricted_device_visibility:
            raise ValueError("execution identity may not have unrestricted device visibility")

        scopes = tuple(value.strip() for value in self.device_visibility_scope if value.strip())
        if not scopes:
            raise ValueError("execution identity requires an explicit pilot device visibility scope")
        if any(value.casefold() in {"*", "all", "all devices", "global", "unrestricted"} for value in scopes):
            raise ValueError("execution identity device visibility must be explicitly bounded")

        components = tuple(value.strip() for value in self.component_allowlist if value.strip())
        if not components:
            raise ValueError("execution identity requires an explicit component allowlist")
        if any(value.casefold() in {"*", "all", "all components", "global", "unrestricted"} for value in components):
            raise ValueError("execution identity component visibility must be explicitly bounded")

        forbidden_admin = (
            self.user_administration_allowed,
            self.site_administration_allowed,
            self.policy_administration_allowed,
            self.component_administration_allowed,
        )
        if any(forbidden_admin):
            raise ValueError("execution identity may not include provider administration authority")


def validate_execution_identity_separation(
    *,
    readonly_logical_secret: str,
    execution: DattoRmmExecutionIdentityContainment,
) -> None:
    """Prove that the approved Phase 3 identity does not broaden the read identity."""

    if readonly_logical_secret != DATTO_RMM_READONLY_LOGICAL_SECRET:
        raise ValueError("Datto read identity contract drifted")
    execution.validate()
    if execution.logical_secret == readonly_logical_secret:
        raise ValueError("Datto read and execution identities must remain separate")
