"""Offline contract tests. No Microsoft tenant or production calls."""
import pytest

from connectors.microsoft_graph.governed_operations import (
    MICROSOFT_GOVERNED_OPERATIONS,
    GovernedMicrosoftOperation,
    operation,
)


def test_catalog_is_reusable_and_default_deny():
    assert set(MICROSOFT_GOVERNED_OPERATIONS) == {
        "identity.group.create", "identity.group.member.add",
    }
    with pytest.raises(PermissionError):
        operation("identity.user.delete")
    with pytest.raises(TypeError):
        MICROSOFT_GOVERNED_OPERATIONS["identity.user.delete"] = object()


@pytest.mark.parametrize("operation_name", list(MICROSOFT_GOVERNED_OPERATIONS))
def test_mutations_require_bound_approval_and_readback(operation_name):
    item = operation(operation_name)
    assert item.requires_exact_approval and item.requires_readback
    assert item.permission_profile
    assert item.route.startswith("/v1.0/")


def test_group_schema_rejects_unrecognized_and_missing_arguments():
    item = operation("identity.group.create")
    valid = {"display_name": "Accounting", "mail_nickname": "accounting", "group_type": "security"}
    assert item.validate_arguments(valid) == valid
    for bad in (
        {"display_name": "Accounting"},
        {**valid, "url": "https://attacker.invalid"},
        {**valid, "method": "DELETE"},
        {**valid, "display_name": "\n"},
        {**valid, "display_name": 7},
        {**valid, "group_type": "dynamic"},
    ):
        with pytest.raises(ValueError):
            item.validate_arguments(bad)


def test_invalid_policy_descriptor_rejected():
    with pytest.raises(ValueError):
        GovernedMicrosoftOperation(
            "unsafe", "microsoft_graph", "write", "POST",
            "/v1.0/groups", frozenset(), requires_exact_approval=False,
        )



def test_membership_requires_exact_canonical_object_ids():
    item = operation("identity.group.member.add")
    args = {
        "verified_group_id": "33333333-3333-4333-8333-333333333333",
        "verified_member_id": "44444444-4444-4444-8444-444444444444",
    }
    assert item.validate_arguments(args) == args
    with pytest.raises(ValueError):
        item.validate_arguments({**args, "verified_member_id": "user@example.com"})
