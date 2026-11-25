from tools.dependency_conflict_service import admission


def work(wid, *, state='active', kind='repair', **domains):
    data = {'id': wid, 'state': state, 'kind': kind}
    for key in ('files', 'components', 'contracts', 'providers', 'schemas',
                'deployment_paths', 'authorization_paths', 'tenant_scopes', 'depends_on'):
        data[key] = domains.get(key, [])
    return data


def test_parallel_independent_repair_is_admitted_despite_production_hold():
    assert admission(work('B', components=['kfs']), [work('A', components=['sharepoint'])])['state'] == 'admitted'


def test_shared_contract_conflict_blocks_admission():
    result = admission(work('B', contracts=['mcp-v1']), [work('A', contracts=['mcp-v1'])])
    assert result['state'] == 'blocked_by_dependency'
    assert result['conflicts'][0]['reasons'] == ['contracts']


def test_shared_governance_and_tenant_scope_conflicts():
    a = work('A', authorization_paths=['owner-gate'], tenant_scopes=['shared'])
    b = work('B', authorization_paths=['owner-gate'], tenant_scopes=['shared'])
    assert admission(b, [a])['state'] == 'blocked_by_dependency'


def test_explicit_dependencies_require_verified_upstream():
    b = work('B', components=['new'], depends_on=['A'])
    assert admission(b, [work('A', components=['old'])])['state'] == 'blocked_by_dependency'
    assert admission(b, [work('A', components=['old'], state='production_verified')])['state'] == 'admitted'


def test_missing_semantic_metadata_fails_closed():
    b = work('B', components=['independent'])
    del b['contracts']
    assert admission(b, [])['state'] == 'blocked'


def test_new_features_wait_for_real_production_health():
    b = work('B', kind='feature', components=['new'])
    assert admission(b, [])['state'] == 'blocked'
    assert admission(b, [], production_healthy=True)['state'] == 'admitted'


def test_unknown_and_duplicate_inventory_cannot_allow_new_work():
    b = work('B', components=['new'])
    assert admission(b, [work('A', components=['old'], state='unknown')])['state'] == 'blocked'
    a = work('A', components=['old'])
    assert admission(b, [a, a])['state'] == 'blocked'


def test_same_file_conflict_and_finished_work_not_active():
    b = work('B', files=['tools/worker.py'])
    a = work('A', files=['tools/worker.py'])
    assert admission(b, [a])['state'] == 'blocked_by_dependency'
    assert admission(b, [work('A', state='production_verified', files=['tools/worker.py'])])['state'] == 'admitted'


def test_cli_refuses_conflict_with_nonzero_status(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    inv, candidate, out = [tmp_path / name for name in ('inventory.json', 'candidate.json', 'out.json')]
    inv.write_text(json.dumps({'items': [work('A', components=['core'])]}))
    candidate.write_text(json.dumps(work('B', components=['core'])))
    run = subprocess.run([sys.executable, str(root / 'tools/dependency_conflict_service.py'),
                          '--input', str(inv), '--candidate', str(candidate), '--output', str(out)],
                         capture_output=True, text=True, check=False)
    assert run.returncode == 2
    assert json.loads(out.read_text())['state'] == 'blocked_by_dependency'


def test_legacy_overlap_analysis_also_sees_shared_authorization_and_tenant_scope():
    from tools.dependency_conflict_service import analyze
    a = work('A', authorization_paths=['owner-approval'], tenant_scopes=['aot-shared'])
    b = work('B', authorization_paths=['owner-approval'], tenant_scopes=['aot-shared'])
    result = analyze([a, b])
    assert result['status'] == 'conflict'
    assert set(result['conflicts'][0]['reasons']) == {'authorization_paths', 'tenant_scopes'}
