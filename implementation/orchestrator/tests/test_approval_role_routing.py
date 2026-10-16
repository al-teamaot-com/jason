from dataclasses import replace
import pytest
from orchestrator.approval_role_routing import TenantApprovalPolicy, route_approval_candidates


def policy():
    return TenantApprovalPolicy('aot', {'admin': frozenset({'al', 'lindsey'}), 'finance': frozenset({'lindsey','adam'})},
        {'release.promote': frozenset({'admin'}), 'quickbooks.invoice': frozenset({'finance'})}, frozenset({'adam'}))


def test_role_based_multiuser_routing():
    p = policy()
    assert route_approval_candidates(policy=p, organization_id='aot', capability='release.promote', requester_identity_id='al') == ('lindsey',)
    assert route_approval_candidates(policy=p, organization_id='aot', capability='quickbooks.invoice', requester_identity_id='requester') == ('lindsey',)


def test_foreign_tenant_is_denied():
    with pytest.raises(PermissionError):
        route_approval_candidates(policy=policy(), organization_id='foreign', capability='release.promote', requester_identity_id='worker')


def test_no_configured_role_fails_closed():
    with pytest.raises(PermissionError):
        route_approval_candidates(policy=policy(), organization_id='aot', capability='unknown', requester_identity_id='worker')


def test_empty_candidates_fails_closed():
    with pytest.raises(PermissionError):
        route_approval_candidates(policy=replace(policy(),disabled_principals=frozenset({'lindsey'})), organization_id='aot', capability='release.promote', requester_identity_id='al')
