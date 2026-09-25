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


def test_timeline_states_what_ran_returned_and_verified():
    row = {'created_at': '2026-09-25T15:14:03+00:00'}
    terminal = {'occurred_at': '2026-09-25T15:14:04+00:00'}
    plan = {'arguments': {'command': 'Get-Date'}}
    result = {'output': {'data': {'stdout': '09/25/2026'}}}
    timeline = mod._timeline(
        row=row, terminal=terminal, plan=plan, result=result,
        action_name='Get-Date', target={'device_name': 'AOT-50282'},
        state='succeeded', failure_reason=None,
        verification={'readbackVerified': True},
    )
    assert timeline[0]['event'] == 'Ran'
    assert 'Jason ran Get-Date' in timeline[0]['message']
    assert timeline[0]['input'] == 'Get-Date'
    assert timeline[1]['event'] == 'Returned'
    assert timeline[1]['output'] == '09/25/2026'
    assert timeline[2]['message'] == 'Result: Success.'
    assert timeline[3]['message'] == 'Verification: Passed.'
    assert '09/25/2026' in timeline[0]['time']


def test_timeline_states_failure_reason():
    timeline = mod._timeline(
        row={'created_at': '2026-09-25T15:14:03+00:00'}, terminal=None,
        plan={'arguments': {'command': 'Get-Date'}}, result={},
        action_name='Get-Date', target={}, state='failed',
        failure_reason='provider_invocation_failed', verification={},
    )
    assert timeline[-1]['message'] == 'Result: Failed — provider_invocation_failed.'


def test_target_prefers_friendly_context_when_present():
    plan = {
        'resource_type': 'service_ticket',
        'normalized_payload': {
            'ticketID': 141233, 'ticketNumber': 'T20260925.0051',
            'companyID': 1158, 'companyName': 'XYZ Test Company',
            'configurationItemID': 379, 'deviceName': 'AOT-50282',
        },
    }
    out = mod._target_from_plan(plan)
    assert out['ticket_number'] == 'T20260925.0051'
    assert out['client_name'] == 'XYZ Test Company'
    assert out['device_name'] == 'AOT-50282'


def test_governed_execution_db_uses_immutable_readonly_uri(monkeypatch, tmp_path):
    db_path = tmp_path / 'governed.sqlite3'
    import sqlite3
    c = sqlite3.connect(db_path)
    c.execute('create table sample (id integer)')
    c.commit(); c.close()
    monkeypatch.setattr(mod, 'LEDGER_DB', db_path)
    conn = mod._db(db_path)
    try:
        assert conn.execute('select count(*) from sample').fetchone()[0] == 0
    finally:
        conn.close()


def test_enrichment_promotes_friendly_ticket_company_and_title():
    target = {
        'ticket_id': '141233', 'ticket_number': None,
        'client_id': None, 'client_name': None,
        'device': None, 'device_name': None,
        'configuration_item_id': None,
    }
    out = mod._enrich_target(target, {
        '141233': {
            'ticket_number': 'T20260925.0051',
            'ticket_title': 'Controlled Test',
            'company_id': 1158,
            'company_name': 'XYZ Test Company',
        }
    })
    assert out['ticket_number'] == 'T20260925.0051'
    assert out['client_id'] == '1158'
    assert out['client_name'] == 'XYZ Test Company'
    assert out['ticket_title'] == 'Controlled Test'


def test_timeline_rows_are_flat_human_readable_strings():
    record = {
        'details': {
            'action_timeline': [
                {'time': '09/25/2026 11:14:03 AM EDT', 'event': 'Ran', 'message': 'Jason ran Get-Date.', 'input': 'Get-Date'},
                {'time': '09/25/2026 11:14:04 AM EDT', 'event': 'Returned', 'message': 'Provider returned output.', 'output': {'stdout': '09/25/2026'}},
                {'time': '09/25/2026 11:14:04 AM EDT', 'event': 'Verification', 'message': 'Verification: Passed.', 'evidence': {'readbackVerified': True}},
            ]
        }
    }
    rows = mod._timeline_rows(record)
    assert rows[0]['input'] == 'Get-Date'
    assert rows[1]['returned'] == 'stdout=09/25/2026'
    assert rows[2]['verification'] == 'readbackVerified=true'
    assert all(isinstance(v, str) for row in rows for v in row.values())


def test_display_playbook_is_human_readable():
    assert mod._display_playbook('autonomy_execution_acceptance') == 'Autonomy Execution Acceptance'
