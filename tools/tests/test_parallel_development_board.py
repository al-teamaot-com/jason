"""Control Board surfaces development admission without DB/host mutation."""
import json
from datetime import datetime, timedelta, timezone

from tools import development_release_coordinator as coordinator


def state(when):
    return {'dependency_admission': {
        'schema_version': '1.0', 'observed_at': when.isoformat(),
        'active_claims': ['DEV-1117', 'DEV-2294'],
        'unclassified_active': [],
        'active_editor_holds': {'DEV-2294': [{'with': 'DEV-1117', 'reasons': ['providers']}]},
        'queue': {'DEV-1470': {'state': 'blocked_by_dependency'}},
        'production_authority': False,
    }}


def test_board_fresh_host_claims_are_visible_without_authority(tmp_path):
    now = datetime(2026,11,23,17,45,tzinfo=timezone.utc)
    f = tmp_path/'development-state.json'
    f.write_text(json.dumps(state(now)), encoding='utf-8')
    view = coordinator.development_admission_view(f, now=now)
    assert view['status'] == 'read_only_verified_snapshot'
    assert view['active'] == ['DEV-1117','DEV-2294']
    assert view['editor_holds'] == {'DEV-2294':['DEV-1117']}
    assert view['queued_holds'] == {'DEV-1470':'blocked_by_dependency'}
    assert view['production_authority'] is False
    board = {'generated_at':now.isoformat(), 'main_sha':'a'*40,
        'production':{},'preproduction':{},'release_control':{},
        'pr_states':[],'older_open_pr_count':0,'overlaps':[],
        'release_attention':'none','development_recommendation':'none',
        'support':[],'todos':[], 'production_policy':{}, 'autonomous_repair_policy':{},
        'support_autonomy_policy':{}, 'todo_autonomy_policy':{},'development_admission':view}
    rendered = coordinator.render(board)
    assert 'Blocked by dependency**: `DEV-2294` waiting on `DEV-1117`' in rendered
    assert '`DEV-1470`: blocked_by_dependency' in rendered
    assert 'not deployment authority' in rendered
    assert f.read_text() == json.dumps(state(now))


def test_missing_stale_or_forged_evidence_fails_closed(tmp_path):
    now = datetime(2026,11,23,17,45,tzinfo=timezone.utc)
    p=tmp_path/'state.json'
    assert coordinator.development_admission_view(p,now=now)['status']=='not_verified'
    p.write_text(json.dumps(state(now-timedelta(hours=2))))
    assert coordinator.development_admission_view(p,now=now)['reason']=='host_claim_evidence_stale_or_future'
    forged=state(now)
    forged['dependency_admission']['active_editor_holds']={'DEV-2294': [{'with':'DEV-1117\n## forged status','reasons':[]}]}
    p.write_text(json.dumps(forged))
    assert coordinator.development_admission_view(p,now=now)['reason']=='host_claim_content_invalid'


def test_board_missing_host_telemetry_never_claims_idle():
    board={'generated_at':'2026-11-23T00:00:00+00:00','main_sha':'a'*40,
        'production':{},'preproduction':{},'release_control':{},
        'pr_states':[],'older_open_pr_count':0,'overlaps':[],
        'release_attention':'none','development_recommendation':'none',
        'support':[],'todos':[], 'production_policy':{}, 'autonomous_repair_policy':{},
        'support_autonomy_policy':{},'todo_autonomy_policy':{},'development_admission':{'status':'not_verified'}}
    rendered=coordinator.render(board)
    assert 'cannot infer an idle or conflict-free engineering queue' in rendered


def _board(now, admission_view):
    return {'generated_at': now.isoformat(), 'main_sha': 'a'*40,
            'production': {}, 'preproduction': {}, 'release_control': {},
            'pr_states': [], 'older_open_pr_count': 0, 'overlaps': [],
            'release_attention': 'none', 'development_recommendation': 'none',
            'support': [], 'todos': [], 'production_policy': {},
            'autonomous_repair_policy': {}, 'support_autonomy_policy': {},
            'todo_autonomy_policy': {}, 'development_admission': admission_view}


def test_fresh_host_claim_report_survives_schedule_but_expires(tmp_path):
    now = datetime(2026, 11, 23, 17, 45, tzinfo=timezone.utc)
    f = tmp_path / 'development-state.json'
    f.write_text(json.dumps(state(now)))
    host = coordinator.render(_board(now, coordinator.development_admission_view(f, now=now)))
    scheduled = coordinator.render(_board(now + timedelta(minutes=10),
                                          {'status': 'not_verified'}))
    marker = coordinator.HOST_DEVELOPMENT_ADMISSION_MARKER
    assert marker in host and marker not in scheduled
    fresh = coordinator.preserve_fresh_host_development_admission(
        scheduled, host, now=now + timedelta(minutes=10))
    assert marker in fresh
    assert 'DEV-2294' in fresh and 'DEV-1117' in fresh
    assert 'cannot infer an idle' not in fresh
    expired = coordinator.preserve_fresh_host_development_admission(
        scheduled, host, now=now + timedelta(minutes=40))
    assert marker not in expired
    assert 'cannot infer an idle' in expired


def test_host_board_preservation_rejects_forged_or_invalid_prior():
    now = datetime(2026, 11, 23, 17, 45, tzinfo=timezone.utc)
    unknown = coordinator.render(_board(now, {'status': 'not_verified'}))
    bad = (unknown.replace(
        '- **Not verified**: fresh, authenticated host claim evidence is unavailable.',
        '- Claim snapshot observed: \x602026-11-23T17:45:00+00:00\x60; <script>bad</script>') +
        '\n' + coordinator.HOST_DEVELOPMENT_ADMISSION_MARKER)
    assert coordinator.preserve_fresh_host_development_admission(
        unknown, bad, now=now) == unknown
