from types import SimpleNamespace
import pytest
from orchestrator.teams_plan_response_dispatch import UniversalPlanResponseDispatch

class Store:
    def __init__(self, value):
        self.value = value
    def require(self, key, **kwargs):
        assert key == 'planapproval-1'
        return self.value

class Service:
    def __init__(self):
        self.calls = []
    def handle_stored_response(self, **kwargs):
        self.calls.append(kwargs)
        return 'verified-flow-result'

def test_server_sources_override_card_identity_and_scope():
    service = Service()
    original_request = SimpleNamespace(organization_id='tenant-org')
    repository = Store('server-proposal')
    adapter = UniversalPlanResponseDispatch(service, repository, Store(original_request), Store('trusted-token'))
    result = adapter.handle(approval_id='planapproval-1', decision='deny', token='forged',
        original_request='forged', organization_id='forged', plan_fingerprint='forged',
        microsoft_tenant_id='tenant', microsoft_object_id='actor', channel_response_id='receipt')
    assert result == 'verified-flow-result'
    call = service.calls[0]
    assert call['token'] == 'trusted-token'
    assert call['original_request'] is original_request
    assert call['proposal_repository'] is repository
    assert call['payload'] == {'approval_id':'planapproval-1', 'decision':'deny',
        'organization_id':'tenant-org', 'channel_response_id':'receipt'}

def test_non_plan_intent_rejected_without_dispatch():
    adapter = UniversalPlanResponseDispatch(Service(), object(), object(), object())
    with pytest.raises(PermissionError):
        adapter.handle(approval_id='procapproval-1', decision='approve')


def test_missing_authenticated_actor_fails_before_server_lookups():
    class ForbiddenStore:
        def require(self, *args, **kwargs):
            raise AssertionError('must not consult server-side stores without an actor')
    adapter = UniversalPlanResponseDispatch(Service(), ForbiddenStore(), ForbiddenStore(), ForbiddenStore())
    with pytest.raises(PermissionError, match='authenticated actor context required'):
        adapter.handle(approval_id='planapproval-1', decision='approve')


def test_missing_response_receipt_fails_closed():
    service = Service()
    adapter = UniversalPlanResponseDispatch(service, Store('proposal'),
        Store(SimpleNamespace(organization_id='tenant-org')), Store('trusted-token'))
    with pytest.raises(PermissionError, match='response identifier required'):
        adapter.handle(approval_id='planapproval-1', decision='approve',
            microsoft_tenant_id='tenant', microsoft_object_id='actor')
    assert service.calls == []
