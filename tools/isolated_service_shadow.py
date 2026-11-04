#!/usr/bin/env python3
"""One-shot independent shadow runner for each isolated service.

The service process reads existing evidence, writes exclusively to a separate
service-state directory, and never calls a production, approval, or write path.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path

try:
 from isolated_service_common import atomic_json,load_json,now_iso
 from isolated_service_live_sources import bounded_json,provider_canaries,todo_commitments
 import documentation_assurance_service as documentation
 import isolated_service_ledger as ledger
 import isolated_service_supervisor as supervisor
 import source_baseline_monitor_service as source_baseline
 import test_evidence_collection_service as test_evidence
 import dependency_conflict_service as dependency
 import rollback_readiness_service as rollback
 import operational_acceptance_service as acceptance
except ModuleNotFoundError:
 from tools.isolated_service_common import atomic_json,load_json,now_iso
 from tools.isolated_service_live_sources import bounded_json,provider_canaries,todo_commitments
 from tools import documentation_assurance_service as documentation
 from tools import isolated_service_ledger as ledger
 from tools import isolated_service_supervisor as supervisor
 from tools import source_baseline_monitor_service as source_baseline
 from tools import test_evidence_collection_service as test_evidence
 from tools import dependency_conflict_service as dependency
 from tools import rollback_readiness_service as rollback
 from tools import operational_acceptance_service as acceptance

PRODUCTION_STATE=Path('/var/lib/jason/openclaw').resolve()
SERVICE_FILES={
 'documentation_assurance':'documentation-assurance.json',
 'provider_health_monitor':'provider-health.json',
 'test_evidence_collection':'test-evidence.json',
 'work_reconciliation':'work-reconciliation.json',
 'dependency_conflict':'dependency-conflict.json',
 'source_baseline_monitor':'source-baseline.json',
 'rollback_readiness':'rollback-readiness.json',
 'operational_acceptance':'operational-acceptance.json',
 'ledger':'ledger.json',
 'supervisor':'supervisor.json',
}


def run_one(service:str,*,repo:Path,state_root:Path,provider_path:Path|None=None,
            todo_path:Path|None=None,expected_sha:str|None=None,input_path:Path|None=None,
            candidate_sha:str|None=None,now:datetime|None=None)->dict:
 current=now or datetime.now(timezone.utc)
 state_root=state_root.resolve()
 repo=repo.resolve()
 if (state_root==PRODUCTION_STATE or PRODUCTION_STATE in state_root.parents or
     state_root==repo or repo in state_root.parents):
  raise ValueError('isolated output must be outside production and source trees')
 if service not in SERVICE_FILES: raise ValueError('unsupported standalone service')
 output=state_root/SERVICE_FILES[service]
 base={'schema_version':'1.0','service':service,'observed_at':current.isoformat(),
       'advisory_only':True,'production_authority':False}
 if service=='documentation_assurance':
  result=documentation.scan(repo,output,head='origin/main')
  result.update({'advisory_only':True,'production_authority':False})
 elif service=='provider_health_monitor':
  if provider_path is None: raise ValueError('provider source path required')
  source,digest=bounded_json(provider_path)
  result={**base,'source_sha256':digest,'source_type':'existing_provider_canary_snapshot',
          **provider_canaries(source,now=current)}
 elif service=='work_reconciliation':
  if todo_path is None: raise ValueError('commitment source path required')
  source,digest=bounded_json(todo_path)
  result={**base,'source_sha256':digest,'source_type':'existing_todo_commitment_state',
          **todo_commitments(source,now=current)}
 elif service=='source_baseline_monitor':
  if expected_sha is None:
   result={**base,'status':'unknown','reason':'expected_sha_not_provided'}
  else:
   result={**base,**source_baseline.check_remote(repo,expected_sha)}
 elif service=='test_evidence_collection':
  if input_path is None or not candidate_sha:
   result={**base,'status':'refresh_required','reason':'candidate_or_test_evidence_missing','records':[]}
  else:
   _,digest=bounded_json(input_path)
   data=test_evidence.collect([input_path],output,candidate_sha=candidate_sha,now=current)
   result={**base,**data,'source_sha256':digest}
 elif service=='dependency_conflict':
  if input_path is None:
   result={**base,'status':'unknown','reason':'dependency_inventory_missing','conflicts':[]}
  else:
   source,digest=bounded_json(input_path)
   items=source.get('items')
   if not isinstance(items,list):
    result={**base,'status':'unknown','reason':'invalid_dependency_inventory','conflicts':[],'source_sha256':digest}
   else:
    result={**base,**dependency.analyze(items),'source_sha256':digest}
 elif service=='rollback_readiness':
  if input_path is None:
   result={**base,'status':'not_ready','reason':'verified_rollback_evidence_missing'}
  else:
   source,digest=bounded_json(input_path)
   result={**base,**rollback.evaluate(source),'source_sha256':digest}
 elif service=='operational_acceptance':
  if input_path is None:
   result={**base,'status':'pending','reason':'operational_acceptance_evidence_missing'}
  else:
   source,digest=bounded_json(input_path)
   checks=source.get('checks') if isinstance(source.get('checks'),list) else []
   result={**base,**acceptance.evaluate(checks),'source_sha256':digest}
 elif service=='ledger':
  config=load_json(repo/'config/isolated-services.json')
  result={**base,'service':'isolated_service_ledger',**ledger.build(config,state_root,now=current)}
 else:
  l=load_json(state_root/'ledger.json')
  result={**base,'service':'isolated_service_supervisor',**supervisor.classify(l)}
 atomic_json(output,result)
 return result


def main()->int:
 p=argparse.ArgumentParser()
 p.add_argument('--service',required=True,choices=sorted(SERVICE_FILES))
 p.add_argument('--repo',type=Path,required=True)
 p.add_argument('--state-root',type=Path,required=True)
 p.add_argument('--provider-source',type=Path)
 p.add_argument('--todo-source',type=Path)
 p.add_argument('--expected-sha')
 p.add_argument('--input-source',type=Path)
 p.add_argument('--candidate-sha')
 a=p.parse_args()
 result=run_one(a.service,repo=a.repo,state_root=a.state_root,
  provider_path=a.provider_source,todo_path=a.todo_source,
  expected_sha=a.expected_sha,input_path=a.input_source,candidate_sha=a.candidate_sha)
 print(f"{a.service}: {result['status']} (advisory only)")
 return 0
if __name__=='__main__': raise SystemExit(main())
