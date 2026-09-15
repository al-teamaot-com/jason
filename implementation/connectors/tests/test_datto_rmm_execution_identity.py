import pytest

from connectors.datto_rmm.execution_identity import (
    DATTO_RMM_EXECUTION_LOGICAL_SECRET,
    DATTO_RMM_READONLY_LOGICAL_SECRET,
    REQUIRED_QUICK_JOB_API_PERMISSIONS,
    DattoRmmExecutionIdentityContainment,
    validate_execution_identity_separation,
)


def contained_identity(**overrides):
    values = {
        "provider_identity_name": "Jason governed component executor",
        "security_level_name": "Jason governed component execution",
        "device_visibility_scope": ("pilot-scope",),
        "component_allowlist": ("approved-component",),
    }
    values.update(overrides)
    return DattoRmmExecutionIdentityContainment(**values)


def test_execution_identity_is_separate_and_bounded():
    contract = contained_identity()
    validate_execution_identity_separation(
        readonly_logical_secret=DATTO_RMM_READONLY_LOGICAL_SECRET,
        execution=contract,
    )
    assert contract.logical_secret == DATTO_RMM_EXECUTION_LOGICAL_SECRET
    assert contract.logical_secret != DATTO_RMM_READONLY_LOGICAL_SECRET
    assert contract.api_security_permissions == REQUIRED_QUICK_JOB_API_PERMISSIONS
    assert contract.quick_job_execution_allowed is True
    assert contract.unrestricted_device_visibility is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("unrestricted_device_visibility", True),
        ("user_administration_allowed", True),
        ("site_administration_allowed", True),
        ("policy_administration_allowed", True),
        ("component_administration_allowed", True),
        ("provider_identity_distinct_from_readonly", False),
    ],
)
def test_execution_identity_rejects_broadened_authority(field, value):
    with pytest.raises(ValueError):
        contained_identity(**{field: value}).validate()


@pytest.mark.parametrize(
    "field,value",
    [
        ("device_visibility_scope", ()),
        ("device_visibility_scope", ("all devices",)),
        ("component_allowlist", ()),
        ("component_allowlist", ("all components",)),
    ],
)
def test_execution_identity_requires_explicit_pilot_and_component_scope(field, value):
    with pytest.raises(ValueError):
        contained_identity(**{field: value}).validate()


def test_api_security_level_rejects_missing_quick_job_permission():
    reduced = frozenset(REQUIRED_QUICK_JOB_API_PERMISSIONS - {"jobs.active_jobs.manage"})
    with pytest.raises(ValueError, match="minimum quick-job permissions exactly"):
        contained_identity(api_security_permissions=reduced).validate()


def test_api_security_level_rejects_extra_provider_authority():
    broadened = frozenset((*REQUIRED_QUICK_JOB_API_PERMISSIONS, "setup.global_settings.view"))
    with pytest.raises(ValueError, match="minimum quick-job permissions exactly"):
        contained_identity(api_security_permissions=broadened).validate()


def test_readonly_identity_contract_may_not_be_repurposed():
    with pytest.raises(ValueError, match="read identity contract drifted"):
        validate_execution_identity_separation(
            readonly_logical_secret=DATTO_RMM_EXECUTION_LOGICAL_SECRET,
            execution=contained_identity(),
        )


def test_execution_secret_name_is_fail_closed():
    with pytest.raises(ValueError, match="datto_rmm.execution"):
        contained_identity(logical_secret="datto_rmm.write").validate()
