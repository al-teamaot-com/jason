from __future__ import annotations
import json
from types import SimpleNamespace
import pytest
from tools import isolated_service_github_sources as gh


def runner_for(payloads):
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        key=args[-1]
        assert args[:4]==['gh','api','--method','GET']
        return SimpleNamespace(returncode=0,stdout=json.dumps(payloads[key]))
    return run,calls


def test_ci_reads_exact_sha_and_no_mutating_endpoint():
    sha='a'*40;key=f'repos/aot/jason/commits/{sha}/check-runs?per_page=100'
    run,calls=runner_for({key:{'total_count':2,'check_runs':[
        {'name':'documentation','status':'completed','conclusion':'success'},
        {'name':'regression','status':'completed','conclusion':'success'}]}})
    out=gh.ci_checks('aot/jason',sha,run)
    assert out['status']=='reported_passing'
    assert out['candidate_sha']==sha
    assert out['advisory_only'] is True
    assert calls==[['gh','api','--method','GET',key]]


def test_ci_failure_and_incomplete_cannot_report_passing():
    sha='b'*40;key=f'repos/aot/jason/commits/{sha}/check-runs?per_page=100'
    cases=[({'total_count':1,'check_runs':[{'name':'test','status':'completed','conclusion':'failure'}]},'failed'),
           ({'total_count':2,'check_runs':[{'name':'test','status':'completed','conclusion':'success'}]},'unknown'),
           ({'total_count':0,'check_runs':[]},'unknown'),
           ({'total_count':1,'check_runs':[{'name':'test','status':'in_progress','conclusion':None}]},'pending')]
    for data,expected in cases:
        run,_=runner_for({key:data})
        assert gh.ci_checks('aot/jason',sha,run)['status']==expected


def test_pr_inventory_bounded_and_overlap_visible():
    data={
        'repos/aot/jason/pulls/1/files?per_page=100':[{'filename':'tools/pmv3_engineering_controller.py'}],
        'repos/aot/jason/pulls/2/files?per_page=100':[{'filename':'tools/pmv3_engineering_controller.py'}],
    }
    run,calls=runner_for(data)
    out=gh.pr_file_inventory('aot/jason',[1,2],run)
    assert out['status']=='complete'
    assert out['semantic_conflicts_verified'] is False
    assert len(calls)==2
    from tools import dependency_conflict_service
    conflicts=dependency_conflict_service.analyze(out['items'])
    assert conflicts['status']=='conflict'


def test_invalid_pr_list_and_unbounded_results_fail_closed():
    with pytest.raises(ValueError):gh.pr_file_inventory('aot/jason',[])
    with pytest.raises(ValueError):gh.pr_file_inventory('aot/jason',[1]*2)
    with pytest.raises(ValueError):gh.ci_checks('aot/jason','main')
    with pytest.raises(ValueError):gh.ci_checks('../jason','a'*40)
    key='repos/aot/jason/pulls/1/files?per_page=100'
    run,_=runner_for({key:[{'filename':f'tools/f{i}.py'} for i in range(100)]})
    assert gh.pr_file_inventory('aot/jason',[1],run)['status']=='incomplete'


def test_shadow_github_adapters_are_advisory(monkeypatch,tmp_path):
    from tools import isolated_service_shadow as shadow
    monkeypatch.setattr(shadow.github_sources,'ci_checks',lambda *args:{'status':'reported_passing','candidate_sha':'a'*40,'check_count':2})
    monkeypatch.setattr(shadow.github_sources,'pr_file_inventory',lambda *args:{'status':'complete','items':[{'id':'PR-1','files':['tools/a.py'],'components':['tools/a']},{'id':'PR-2','files':['tools/b.py'],'components':['tools/b']}],'missing_or_truncated_prs':[]})
    repo=tmp_path/'repo';repo.mkdir();out=tmp_path/'out'
    ci=shadow.run_one('test_evidence_collection',repo=repo,state_root=out,candidate_sha='a'*40)
    deps=shadow.run_one('dependency_conflict',repo=repo,state_root=out,pr_numbers=[1,2])
    assert ci['status']=='reported_passing' and ci['production_authority'] is False
    assert deps['status']=='clear_file_overlap_only' and deps['semantic_conflicts_verified'] is False


def test_adjacent_files_in_same_directory_do_not_create_false_conflict():
    data={
        'repos/aot/jason/pulls/1/files?per_page=100':[{'filename':'docs/engineering/separation.md'}],
        'repos/aot/jason/pulls/2/files?per_page=100':[{'filename':'docs/engineering/rollback.md'}],
    }
    run,_=runner_for(data)
    inventory=gh.pr_file_inventory('aot/jason',[1,2],run)
    from tools import dependency_conflict_service
    result=dependency_conflict_service.analyze(inventory['items'])
    assert result['status']=='clear'
    assert inventory['semantic_conflicts_verified'] is False
