#!/usr/bin/env python3
"""Disposable two-cycle independent-services preproduction acceptance.

No providers, production systems, service installs, or GitHub writes are used.
Tests honest failure isolation and digest-bound, idempotent one-shot outcomes.
"""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[2]
RUNNER=SOURCE/'tools/isolated_service_shadow.py'
CONFIG=SOURCE/'config/isolated-services.json'


def run(args:list[str],*,cwd:Path|None=None)->str:
    result=subprocess.run(args,cwd=cwd,text=True,capture_output=True,check=False,timeout=25)
    if result.returncode:
        raise RuntimeError(f"isolated lab command failed: {args[0]} rc={result.returncode}: {result.stderr[-500:]}")
    return result.stdout.strip()


def write(path:Path,value:dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True)+'\n',encoding='utf-8')


def repo_fixture(root:Path)->Path:
    repo=root/'fixture-repo';repo.mkdir()
    run(['git','init','-q'],cwd=repo)
    run(['git','config','user.name','Isolated Services Lab'],cwd=repo)
    run(['git','config','user.email','lab@example.invalid'],cwd=repo)
    write(repo/'config/isolated-services.json',json.loads(CONFIG.read_text()))
    (repo/'README.md').write_text('test baseline\n')
    run(['git','add','.'],cwd=repo)
    run(['git','commit','-qm','baseline'],cwd=repo)
    (repo/'tools').mkdir()
    (repo/'docs').mkdir()
    (repo/'tools/worker.py').write_text('print("shadow")\n')
    (repo/'docs/worker.md').write_text('shadow docs for content review\n')
    run(['git','add','.'],cwd=repo)
    run(['git','commit','-qm','implementation and documentation'],cwd=repo)
    sha=run(['git','rev-parse','HEAD'],cwd=repo)
    run(['git','update-ref','refs/remotes/origin/main',sha],cwd=repo)
    return repo


def acceptance(root:Path)->dict:
    now=datetime.now(timezone.utc).isoformat()
    repo=repo_fixture(root)
    state=root/'isolated-state'
    provider=root/'provider-snapshot.json'
    todo=root/'todo-commitments.json'
    dependency=root/'dependency-inventory.json'
    rollback=root/'rollback-fixture.json'
    checks=root/'checks.json'
    test=root/'test-evidence.json'
    candidate='a'*40
    write(provider,{'generated_at':now,'results':[
        {'provider':'autotask','healthy':True},
        {'provider':'it_glue','healthy':False}]})
    write(todo,{'updated_at':now,'items':{
        'TODO-LAB-1':{'phase':'waiting_development_start','reason':'eligible existing commitment'},
        'TODO-LAB-2':{'phase':'development_blocked','reason':'API credentials required'},
    }})
    write(dependency,{'items':[{'id':'PR-A','files':['docs/a.md']},
                                      {'id':'PR-B','files':['docs/b.md']}]})
    write(rollback,{'rollback_sha':'b'*40,'runtime_image':'sha256:runtime',
                    'mcp_image':'sha256:mcp','host_release':'/opt/jason/releases/lab',
                    'verified':True})
    write(checks,{'checks':[{'name':'simulated_smoke','status':'passed'}]})
    write(test,{'candidate_sha':candidate,'status':'passed','observed_at':now})
    fixtures=[provider,todo,dependency,rollback,checks,test]
    original={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures}
    services=['documentation_assurance','provider_health_monitor','test_evidence_collection',
              'work_reconciliation','dependency_conflict','source_baseline_monitor',
              'rollback_readiness','operational_acceptance']
    observations=[]
    for cycle in (1,2):
        for service in services:
            args=[sys.executable,str(RUNNER),'--service',service,'--repo',str(repo),
                  '--state-root',str(state),'--provider-source',str(provider),
                  '--todo-source',str(todo)]
            if service in {'test_evidence_collection','dependency_conflict','rollback_readiness','operational_acceptance'}:
                source={'test_evidence_collection':test,'dependency_conflict':dependency,
                        'rollback_readiness':rollback,'operational_acceptance':checks}[service]
                args+=['--input-source',str(source)]
            if service=='test_evidence_collection': args+=['--candidate-sha',candidate]
            run(args)
        for service in ('ledger','supervisor'):
            run([sys.executable,str(RUNNER),'--service',service,'--repo',str(repo),
                 '--state-root',str(state)])
        ledger=json.loads((state/'ledger.json').read_text())
        supervision=json.loads((state/'supervisor.json').read_text())
        if len(ledger['entries'])!=8 or supervision['status']!='degraded':
            raise RuntimeError('incomplete service inventory or false-green supervision')
        statuses={item['name']:item['service_status'] for item in ledger['entries']}
        if statuses['provider_health_monitor']!='unhealthy':
            raise RuntimeError('provider failure was not isolated/honestly reported')
        if statuses['documentation_assurance']!='review_required':
            raise RuntimeError('documentation review was incorrectly cleared on recheck')
        if statuses['work_reconciliation']!='work_available':
            raise RuntimeError('existing TODO record not normalized')
        if statuses['dependency_conflict']!='clear' or statuses['operational_acceptance']!='checks_reported_passing':
            raise RuntimeError('independent services did not progress alongside provider failure')
        if statuses['source_baseline_monitor']!='unknown':
            raise RuntimeError('unbound SHA was incorrectly trusted')
        if len(supervision['warnings'])<2 or supervision['problems']:
            raise RuntimeError('failure isolation did not preserve correct warning-only behavior')
        observations.append({'cycle':cycle,'statuses':statuses,
                             'supervisor_status':supervision['status'],
                             'warning_count':len(supervision['warnings'])})
    final={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures}
    if final!=original:raise RuntimeError('source inputs mutated during shadow execution')
    if len(list(state.glob('*.json')))!=10:
        raise RuntimeError('shadow state divergence/duplicate output')
    if observations[0]['statuses']!=observations[1]['statuses']:
        raise RuntimeError('independent workers were not stable across cycles')
    return {'schema_version':'1.0','status':'pass','advisory_only':True,
            'production_write':False,'provider_contacted':False,
            'service_count':len(services),'cycles':observations,
            'fixture_sha256':original,'source_revision':run(['git','rev-parse','HEAD'],cwd=SOURCE)}


def main()->int:
    with tempfile.TemporaryDirectory(prefix='jason-isolated-preprod-') as folder:
        proof=acceptance(Path(folder))
    out=os.environ.get('JASON_ISOLATED_LAB_RECEIPT')
    if out:
        path=Path(out);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(proof,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:proof[k] for k in ('status','production_write','provider_contacted','service_count')},sort_keys=True))
    return 0

if __name__=='__main__':raise SystemExit(main())
