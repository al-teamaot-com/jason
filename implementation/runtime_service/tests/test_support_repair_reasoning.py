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
