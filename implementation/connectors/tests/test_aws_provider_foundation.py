from __future__ import annotations

import pytest

from aws.credential_binding import AwsCredentialBinding, AwsCredentialBindingError, AwsRoleBinding
from aws.platform import AwsCloudRequest, AwsOperationMode, AwsRequestPolicyError, build_governed_request
from aws.service_catalog import AwsService, service_profile


def test_account_id_and_role_binding_are_strict() -> None:
    role = AwsRoleBinding(
        logical_name='aws.readonly.assume_role',
        role_arn='arn:aws:iam::123456789012:role/JasonReadOnly',
        external_id_logical_name='aws.readonly.external_id',
    )
    binding = AwsCredentialBinding(
        account_id='123456789012',
        organization_id='o-example1234',
        role=role,
        home_region='us-east-1',
    )

    assert binding.required_logical_secrets == (
        'aws.readonly.assume_role',
        'aws.readonly.external_id',
    )
    assert binding.persists_runtime_credentials is False

    with pytest.raises(AwsCredentialBindingError):
        AwsCredentialBinding(account_id='123', organization_id='o-example1234', role=role)


def test_regional_service_requires_explicit_region() -> None:
    with pytest.raises(ValueError):
        AwsCloudRequest(
            service=AwsService.EC2,
            action='DescribeInstances',
            account_id='123456789012',
            organization_id='o-example1234',
        )


def test_governed_read_request_is_provider_neutral_and_scoped() -> None:
    request = build_governed_request(
        AwsCloudRequest(
            service=AwsService.EC2,
            action='DescribeInstances',
            account_id='123456789012',
            organization_id='o-example1234',
            region='us-east-1',
            parameters={'MaxResults': 25},
        )
    )

    assert request.provider_name == 'aws'
    assert request.account_id == '123456789012'
    assert request.region == 'us-east-1'
    assert request.mode is AwsOperationMode.READ


def test_mutation_and_uncatalogued_actions_fail_closed() -> None:
    with pytest.raises(AwsRequestPolicyError):
        build_governed_request(
            AwsCloudRequest(
                service=AwsService.EC2,
                action='DescribeInstances',
                account_id='123456789012',
                organization_id='o-example1234',
                region='us-east-1',
                mode=AwsOperationMode.WRITE_WITH_APPROVAL,
            )
        )

    with pytest.raises(AwsRequestPolicyError):
        build_governed_request(
            AwsCloudRequest(
                service=AwsService.EC2,
                action='TerminateInstances',
                account_id='123456789012',
                organization_id='o-example1234',
                region='us-east-1',
            )
        )


def test_assume_role_is_not_an_ordinary_provider_capability() -> None:
    with pytest.raises(AwsRequestPolicyError):
        build_governed_request(
            AwsCloudRequest(
                service=AwsService.STS,
                action='AssumeRole',
                account_id='123456789012',
                organization_id='o-example1234',
            )
        )


def test_organizations_catalog_uses_read_only_discovery_actions() -> None:
    profile = service_profile(AwsService.ORGANIZATIONS)
    assert 'ListAccounts' in profile.read_actions
    assert 'DescribeAccount' in profile.read_actions
    assert all(not action.startswith(('Create', 'Delete', 'Move', 'Update')) for action in profile.read_actions)
