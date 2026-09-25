import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'autonomy_flight_recorder_exporter.py'
spec = importlib.util.spec_from_file_location('flight_recorder', MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_sanitize_redacts_secret_keys_and_bearer_values():
    value = {
        'password': 'fixture-value',
        'nested': {'api_token': 'fixture-token', 'message': ''.join(['Bearer', ' ', 'X' * 24])},
        'safe': 'visible',
    }
    out = mod._sanitize(value)
    assert out['password'] == '[REDACTED]'
    assert out['nested']['api_token'] == '[REDACTED]'
    assert out['nested']['message'] == '[REDACTED]'
    assert out['safe'] == 'visible'


def test_target_from_normalized_ticket_note_plan():
    plan = {
        'resource_type': 'service_ticket_note',
        'resource_identifier': '141233',
        'normalized_payload': {'ticketID': 141233},
        'client_id': None,
    }
    out = mod._target_from_plan(plan)
    assert out['ticket_id'] == '141233'
    assert out['device'] is None


def test_target_prefers_explicit_device_selector():
    plan = {
        'resource_type': 'endpoint',
        'resource_identifier': 'abc',
        'target_selectors': {'hostname': 'PC-01'},
        'client_id': 'client-1',
    }
    out = mod._target_from_plan(plan)
    assert out['ticket_id'] is None
    assert out['device'] == 'PC-01'
    assert out['client_id'] == 'client-1'
