from __future__ import annotations

import importlib.util
import json
import os
import pwd
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'tools/openbao_identity_lifecycle_worker.py'
spec = importlib.util.spec_from_file_location('openbao_identity_lifecycle_worker_test', SCRIPT)
worker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.path.insert(0, str(ROOT / 'tools'))
sys.modules[spec.name] = worker
spec.loader.exec_module(worker)

SHA = 'a' * 40


def write_request(path: Path, body: dict) -> None:
    path.write_text(json.dumps(body), encoding='utf-8')
    os.chmod(path, 0o600)


def valid_request(request_id: str = '1' * 32) -> dict:
    return {
        'request_id': request_id,
        'action': 'rotate',
        'provider': 'dnsfilter',
        'reason': '#2203 provider AppRole recovery',
        'source_revision': SHA,
        'release_id': '',
    }


def test_request_contract_rejects_extra_privileged_inputs(tmp_path):
    path = tmp_path / ('1' * 32 + '.json')
    body = valid_request()
    body['role_name'] = 'arbitrary-role'
    write_request(path, body)
    with pytest.raises(ValueError, match='contract'):
        worker._read_request(path)


def test_request_contract_rejects_unknown_provider(tmp_path):
    path = tmp_path / ('1' * 32 + '.json')
    body = valid_request()
    body['provider'] = 'arbitrary'
    write_request(path, body)
    with pytest.raises(ValueError, match='not approved'):
        worker._read_request(path)


def test_process_rejects_stale_source_without_rotating(monkeypatch, tmp_path):
    requests = tmp_path / 'requests'; results = tmp_path / 'results'
    requests.mkdir(); results.mkdir()
    lock = tmp_path / 'worker.lock'; lock.touch()
    request_id = '2' * 32
    write_request(requests / (request_id + '.json'), valid_request(request_id))
    monkeypatch.setattr(worker, 'REQUESTS', requests)
    monkeypatch.setattr(worker, 'RESULTS', results)
    monkeypatch.setattr(worker, 'LOCK', lock)
    monkeypatch.setattr(worker.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(worker, '_current_revision', lambda: 'b' * 40)
    called = []
    monkeypatch.setattr(worker, 'rotate', lambda provider: called.append(provider))
    worker.process()
    result = json.loads((results / (request_id + '.json')).read_text())
    assert result['success'] is False
    assert 'stale' in result['detail']
    assert called == []


def test_process_rotates_only_approved_provider_and_returns_sanitized_result(monkeypatch, tmp_path):
    requests = tmp_path / 'requests'; results = tmp_path / 'results'
    requests.mkdir(); results.mkdir()
    lock = tmp_path / 'worker.lock'; lock.touch()
    request_id = '3' * 32
    write_request(requests / (request_id + '.json'), valid_request(request_id))
    monkeypatch.setattr(worker, 'REQUESTS', requests)
    monkeypatch.setattr(worker, 'RESULTS', results)
    monkeypatch.setattr(worker, 'LOCK', lock)
    monkeypatch.setattr(worker.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(worker, '_current_revision', lambda: SHA)
    monkeypatch.setattr(worker, 'rotate', lambda provider: {
        'runtime_refresh_required': True,
        'secret_id': 'must-not-escape',
    })
    worker.process()
    result = json.loads((results / (request_id + '.json')).read_text())
    assert result == {
        'request_id': request_id,
        'success': True,
        'action': 'rotate',
        'provider': 'dnsfilter',
        'source_revision': SHA,
        'runtime_refresh_required': True,
        'initial_admin_token_revoked': False,
        'provider_api_credentials_changed': False,
        'secret_values_exposed': False,
    }
    assert 'must-not-escape' not in json.dumps(result)


def test_process_bootstrap_from_init_is_bounded_and_sanitized(monkeypatch, tmp_path):
    requests = tmp_path / 'requests'; results = tmp_path / 'results'
    requests.mkdir(); results.mkdir()
    lock = tmp_path / 'worker.lock'; lock.touch()
    request_id = '4' * 32
    body = {
        'request_id': request_id,
        'action': 'bootstrap_from_init',
        'provider': 'identity_lifecycle',
        'reason': '#2203 one-time lifecycle bootstrap',
        'source_revision': SHA,
        'release_id': 'release-' + SHA[:16],
    }
    write_request(requests / (request_id + '.json'), body)
    monkeypatch.setattr(worker, 'REQUESTS', requests)
    monkeypatch.setattr(worker, 'RESULTS', results)
    monkeypatch.setattr(worker, 'LOCK', lock)
    monkeypatch.setattr(worker.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(worker, '_current_revision', lambda: SHA)
    monkeypatch.setattr(worker, 'rotate', lambda provider: (_ for _ in ()).throw(AssertionError('rotate not expected')))
    monkeypatch.setattr(worker, '_verify_bootstrap_authority', lambda request: None)
    monkeypatch.setattr(worker, 'bootstrap_from_init', lambda: {
        'initial_admin_token_revoked': True,
        'secret_value': 'must-not-escape',
    })
    worker.process()
    result = json.loads((results / (request_id + '.json')).read_text())
    assert result['success'] is True
    assert result['action'] == 'bootstrap_from_init'
    assert result['provider'] == 'identity_lifecycle'
    assert result['initial_admin_token_revoked'] is True
    assert 'must-not-escape' not in json.dumps(result)


def test_bootstrap_authority_requires_exact_authenticated_teams_release(monkeypatch, tmp_path):
    records = tmp_path / 'records'
    records.mkdir()
    monkeypatch.setattr(worker, 'RELEASE_RECORDS', records)
    release_id = 'release-' + SHA[:16]
    request = {
        'release_id': release_id,
        'source_revision': SHA,
    }
    base = {
        'release_candidate': {'candidate_sha': SHA},
        'risk_profile': 'production_control_core',
        'state': 'production_eligible',
        'changed_files': [
            'tools/openbao_identity_lifecycle.py',
            'tools/openbao_identity_lifecycle_worker.py',
            'tools/install_openbao_identity_lifecycle.py',
        ],
        'owner_approval': {
            'approved': True,
            'candidate_sha': SHA,
            'source': 'authenticated_mobile_teams_owner:relapproval-' + 'a' * 32,
        },
    }
    path = records / (release_id + '.json')
    path.write_text(json.dumps(base), encoding='utf-8')
    os.chmod(path, 0o600)
    worker._verify_bootstrap_authority(request)

    denied = json.loads(json.dumps(base))
    denied['owner_approval']['source'] = 'explicit_owner_instruction'
    path.write_text(json.dumps(denied), encoding='utf-8')
    with pytest.raises(PermissionError, match='authenticated Teams'):
        worker._verify_bootstrap_authority(request)
