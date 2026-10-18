from pathlib import Path
import json

from connectors.core.contracts import ConnectorTransportError

from jason_runtime.support_repair_reasoning import (
    SupportRepairReasoningMaintenance,
    _request_id,
)


class Client:
    def __init__(self):
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if 'diagnostician' in kwargs['system']:
            return {'diagnosis': 'queue alias mismatch', 'search_terms': ['queueName', 'queueID'], 'blocked_reason': None}
        return {
            'summary': 'normalize queue alias',
            'edits': [{'path': 'implementation/example.py', 'old_text': 'queueName', 'new_text': 'queueID'}],
            'test_paths': ['implementation/tests/test_example.py'],
            'blocked_reason': None,
        }


def _request(kind):
    payload = {
        'kind': kind,
        'support_item': 'SUPPORT-OPS-999',
        'title': 'Synthetic repair',
        'evidence': 'Observed failure',
        'acceptance': 'Regression passes',
        'context': {},
    }
    payload['request_id'] = _request_id(payload)
    return payload


def test_reasoning_maintenance_processes_bounded_search_request(tmp_path: Path):
    client = Client()
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    request = _request('search_plan')
    (request_dir / f"{request['request_id']}.json").write_text(json.dumps(request), encoding='utf-8')

    maintenance = SupportRepairReasoningMaintenance(
        structured_client=client,
        spool=tmp_path,
        interval_seconds=1,
    )
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / f"{request['request_id']}.json").read_text())
    assert response['status'] == 'succeeded'
    assert response['result']['search_terms'] == ['queueName', 'queueID']
    assert len(client.calls) == 1


def test_reasoning_accepts_owner_approved_development_work_item(tmp_path: Path):
    client = Client()
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    payload = {
        'kind': 'search_plan',
        'support_item': 'DEV-676',
        'title': 'Owner-only staff activity audit',
        'evidence': 'Owner-approved issue scope',
        'acceptance': 'Regression passes',
        'context': {'work_class': 'owner_approved_development'},
    }
    payload['request_id'] = _request_id(payload)
    (request_dir / f"{payload['request_id']}.json").write_text(json.dumps(payload), encoding='utf-8')
    maintenance = SupportRepairReasoningMaintenance(structured_client=client, spool=tmp_path, interval_seconds=1)
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / f"{payload['request_id']}.json").read_text())
    assert response['status'] == 'succeeded'
    assert len(client.calls) == 1
    assert 'owner-approved development diagnostician' in client.calls[0]['system']


def test_support_dev_recovery_keeps_support_repair_prompts(tmp_path: Path):
    # A recovery SUPPORT-DEV-* item is a support incident, not a newly
    # owner-approved DEV-* implementation request.  Reclassifying the former
    # silently changes prompt scope and cannot fix a transport HTTP 400.
    for kind, expected_role in (
        ('search_plan', 'support-repair diagnostician'),
        ('edit_plan', 'repair patch proposer'),
    ):
        base = tmp_path / kind
        request_dir = base / 'reasoning' / 'requests'
        request_dir.mkdir(parents=True)
        payload = _request(kind)
        payload['support_item'] = 'SUPPORT-DEV-1196'
        payload['request_id'] = _request_id(payload)
        (request_dir / f"{payload['request_id']}.json").write_text(
            json.dumps(payload), encoding='utf-8'
        )
        client = Client()
        worker = SupportRepairReasoningMaintenance(
            structured_client=client, spool=base, interval_seconds=1
        )
        assert worker.tick() is True
        assert len(client.calls) == 1
        system = client.calls[0]['system']
        assert expected_role in system
        assert 'owner-approved development' not in system
        response = json.loads((base / 'reasoning' / 'responses' /
                               f"{payload['request_id']}.json").read_text())
        assert response['status'] == 'succeeded'


def test_reasoning_maintenance_rejects_tampered_request(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    request = _request('search_plan')
    request['evidence'] = 'tampered'
    (request_dir / f"{request['request_id']}.json").write_text(json.dumps(request), encoding='utf-8')
    maintenance = SupportRepairReasoningMaintenance(structured_client=Client(), spool=tmp_path, interval_seconds=1)
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / f"{request['request_id']}.json").read_text())
    assert response['status'] == 'failed'
    assert 'fingerprint' in response['error']


def test_completed_requests_do_not_starve_later_pending_request(tmp_path: Path):
    client = Client()
    request_dir = tmp_path / 'reasoning' / 'requests'
    response_dir = tmp_path / 'reasoning' / 'responses'
    request_dir.mkdir(parents=True)
    response_dir.mkdir(parents=True)

    # Four alphabetically earlier requests are already complete. The bounded
    # processor must select from unresolved requests rather than slicing first.
    for index in range(4):
        name = f'0{index}.json'
        (request_dir / name).write_text('{}', encoding='utf-8')
        (response_dir / name).write_text('{"status":"succeeded"}', encoding='utf-8')

    request = _request('search_plan')
    pending_path = request_dir / f"{request['request_id']}.json"
    pending_path.write_text(json.dumps(request), encoding='utf-8')

    maintenance = SupportRepairReasoningMaintenance(
        structured_client=client,
        spool=tmp_path,
        interval_seconds=1,
    )

    assert maintenance.tick() is True
    response_path = response_dir / pending_path.name
    assert response_path.exists()
    response = json.loads(response_path.read_text(encoding='utf-8'))
    assert response['status'] == 'succeeded'
    assert len(client.calls) == 1


class TransientFailureClient:
    def __init__(self, status_code=429):
        self.status_code = status_code
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        raise ConnectorTransportError(
            f"HTTP transport failed with status {self.status_code}",
            status_code=self.status_code,
        )


def test_transient_failed_response_retries_with_local_fallback(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    response_dir = tmp_path / 'reasoning' / 'responses'
    request_dir.mkdir(parents=True)
    response_dir.mkdir(parents=True)
    request = _request('search_plan')
    request_path = request_dir / f"{request['request_id']}.json"
    response_path = response_dir / request_path.name
    request_path.write_text(json.dumps(request), encoding='utf-8')
    response_path.write_text(
        json.dumps({
            'status': 'failed',
            'request_id': request['request_id'],
            'error_type': 'ConnectorTransportError',
            'error': 'HTTP transport failed with status 429',
        }),
        encoding='utf-8',
    )
    primary = TransientFailureClient(429)
    fallback = Client()
    maintenance = SupportRepairReasoningMaintenance(
        structured_client=primary,
        fallback_structured_client=fallback,
        spool=tmp_path,
        interval_seconds=1,
    )

    assert maintenance.tick() is True
    response = json.loads(response_path.read_text(encoding='utf-8'))
    assert response['status'] == 'succeeded'
    assert response['result']['search_terms'] == ['queueName', 'queueID']
    assert primary.calls == 1
    assert len(fallback.calls) == 1
    assert fallback.calls[0]['max_output_tokens'] == 1024


def test_previous_ollama_budget_failure_is_bounded_retry_candidate(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    response_dir = tmp_path / 'reasoning' / 'responses'
    request_dir.mkdir(parents=True)
    response_dir.mkdir(parents=True)
    request = _request('search_plan')
    request_path = request_dir / f"{request['request_id']}.json"
    response_path = response_dir / request_path.name
    request_path.write_text(json.dumps(request), encoding='utf-8')
    response_path.write_text(json.dumps({
        'status': 'failed',
        'request_id': request['request_id'],
        'error_type': 'ValueError',
        'error': 'Ollama structured reasoning output budget is invalid',
        'attempts': 1,
    }), encoding='utf-8')
    maintenance = SupportRepairReasoningMaintenance(
        structured_client=Client(),
        spool=tmp_path,
        interval_seconds=1,
    )
    assert maintenance.tick() is True
    response = json.loads(response_path.read_text(encoding='utf-8'))
    assert response['status'] == 'succeeded'


def test_second_scope_review_separates_code_diagnosis_from_deployment(tmp_path: Path):
    client = Client()
    request = _request('search_plan')
    request['context'] = {'scope_review': 'source_diagnosis_only',
                          'prior_blocked_reason': 'root-governed rollback needs authority'}
    request['request_id'] = _request_id(request)
    root = tmp_path / 'reasoning' / 'requests'
    root.mkdir(parents=True)
    (root / (request['request_id'] + '.json')).write_text(json.dumps(request))
    maint = SupportRepairReasoningMaintenance(structured_client=client, spool=tmp_path, interval_seconds=1)
    assert maint.tick() is True
    assert len(client.calls) == 1
    prompt = client.calls[0]['system']
    assert 'source-only diagnosis' in prompt.lower()
    assert 'does not itself require production' in prompt
    assert 'Do not infer that permission' in prompt
    assert 'root-governed' in prompt


def test_hosted_patch_400_recovers_once_through_bounded_local_fallback(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    response_dir = tmp_path / 'reasoning' / 'responses'
    request_dir.mkdir(parents=True)
    response_dir.mkdir(parents=True)
    request = _request('edit_plan')
    (request_dir / (request['request_id'] + '.json')).write_text(json.dumps(request))
    (response_dir / (request['request_id'] + '.json')).write_text(json.dumps({
        'status': 'failed', 'request_id': request['request_id'],
        'error_type': 'ConnectorTransportError',
        'error': 'HTTP transport failed with status 400', 'attempts': 1,
    }))
    primary = TransientFailureClient(400)
    fallback = Client()
    maintenance = SupportRepairReasoningMaintenance(
        structured_client=primary, fallback_structured_client=fallback,
        spool=tmp_path, interval_seconds=1,
    )
    assert maintenance.tick() is True
    response = json.loads((response_dir / (request['request_id'] + '.json')).read_text())
    assert response['status'] == 'succeeded'
    assert response['result']['edits'][0]['path'] == 'implementation/example.py'
    assert primary.calls == 1
    assert len(fallback.calls) == 1
    assert fallback.calls[0]['max_output_tokens'] <= 1024


def test_hosted_search_400_does_not_bypass_request_validation(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    request = _request('search_plan')
    (request_dir / (request['request_id'] + '.json')).write_text(json.dumps(request))
    fallback = Client()
    maintenance = SupportRepairReasoningMaintenance(
        structured_client=TransientFailureClient(400),
        fallback_structured_client=fallback, spool=tmp_path, interval_seconds=1,
    )
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / (request['request_id'] + '.json')).read_text())
    assert response['status'] == 'failed'
    assert fallback.calls == []


def test_transport_failure_spool_keeps_only_bounded_diagnostic_code(tmp_path: Path):
    class FailedClient:
        def complete(self, **kwargs):
            raise ConnectorTransportError('HTTP transport failed', provider_error_code='DNS_RESOLUTION')

    request = _request('search_plan')
    directory = tmp_path / 'reasoning' / 'requests'
    directory.mkdir(parents=True)
    (directory / f"{request['request_id']}.json").write_text(json.dumps(request))
    maintenance = SupportRepairReasoningMaintenance(structured_client=FailedClient(), spool=tmp_path)
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / f"{request['request_id']}.json").read_text())
    assert response['status'] == 'failed'
    assert response['transport_failure_code'] == 'DNS_RESOLUTION'
    assert response['attempts'] == 1


class BillingFailureClient:
    def __init__(self, code='credit_balance_exhausted'):
        self.calls=0
        self.code=code
    def complete(self, **kwargs):
        self.calls+=1
        raise ConnectorTransportError('HTTP transport failed with status 429',status_code=429,
            provider_error_type='insufficient_quota',provider_error_code=self.code)


class FailedFallbackClient:
    def __init__(self):self.calls=0
    def complete(self, **kwargs):
        self.calls+=1
        raise ConnectorTransportError('HTTP transport failed')


def test_empty_credit_error_survives_fallback_failure_and_is_not_retried(tmp_path):
    from datetime import datetime,timedelta,timezone
    clock=[datetime(2026,10,16,tzinfo=timezone.utc)]
    primary=BillingFailureClient();fallback=FailedFallbackClient()
    directory=tmp_path/'reasoning'/'requests';directory.mkdir(parents=True)
    request=_request('search_plan')
    (directory/(request['request_id']+'.json')).write_text(json.dumps(request))
    maint=SupportRepairReasoningMaintenance(structured_client=primary,fallback_structured_client=fallback,
        spool=tmp_path,interval_seconds=1,now=lambda:clock[0])
    assert maint.tick()
    response=json.loads((tmp_path/'reasoning'/'responses'/(request['request_id']+'.json')).read_text())
    assert response['status']=='failed'
    assert response['primary_provider_error_code']=='credit_balance_exhausted'
    assert response['fallback_status']=='failed'
    assert response['required_owner_action']=='restore_provider_credits'
    assert response['retryable'] is False
    assert 'credit_balance_exhausted' in response['error']
    clock[0]+=timedelta(seconds=2)
    assert maint.tick() is False
    assert primary.calls==1 and fallback.calls==1


def test_configured_fallback_can_complete_without_hiding_billing_warning(tmp_path):
    primary=BillingFailureClient();fallback=Client()
    directory=tmp_path/'reasoning'/'requests';directory.mkdir(parents=True)
    request=_request('search_plan')
    (directory/(request['request_id']+'.json')).write_text(json.dumps(request))
    maint=SupportRepairReasoningMaintenance(structured_client=primary,fallback_structured_client=fallback,spool=tmp_path)
    assert maint.tick()
    response=json.loads((tmp_path/'reasoning'/'responses'/(request['request_id']+'.json')).read_text())
    assert response['status']=='succeeded'
    assert response['primary_provider_error_code']=='credit_balance_exhausted'
    assert response['fallback_status']=='succeeded'
    assert response['required_owner_action']=='restore_provider_credits'
    assert len(fallback.calls)==1


def test_quota_failure_without_fallback_is_not_mislabeled_network_error(tmp_path):
    directory=tmp_path/'reasoning'/'requests';directory.mkdir(parents=True)
    request=_request('search_plan')
    (directory/(request['request_id']+'.json')).write_text(json.dumps(request))
    maint=SupportRepairReasoningMaintenance(structured_client=BillingFailureClient('project_spend_limit_exceeded'),spool=tmp_path)
    assert maint.tick()
    response=json.loads((tmp_path/'reasoning'/'responses'/(request['request_id']+'.json')).read_text())
    assert response['required_owner_action']=='review_project_spend_limit'
    assert response['retryable'] is False
