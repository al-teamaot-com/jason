#!/usr/bin/env python3
"""Read-only, bounded GitHub facts for independent CI and dependency evidence.

Uses the existing authenticated `gh api` GET surface; never supplies a token,
executes GitHub mutations, merges code, or changes admission policy.
"""
from __future__ import annotations
import json,re,subprocess
from typing import Any,Callable

REPO=re.compile(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z')
SHA=re.compile(r'[0-9a-f]{40}\Z')
MAX_RESPONSE=800_000
MAX_PRS=10


def read_gh(repo:str,path:str,runner:Callable[...,Any]=subprocess.run)->Any:
    if REPO.fullmatch(repo) is None or any(part in {'.', '..'} for part in repo.split('/')):
        raise ValueError('invalid repository identifier')
    result=runner(['gh','api','--method','GET',f'repos/{repo}/{path}'],
                  capture_output=True,text=True,check=False,timeout=25)
    if result.returncode or len(result.stdout)>MAX_RESPONSE:
        raise RuntimeError('bounded GitHub read unavailable')
    return json.loads(result.stdout)


def ci_checks(repo:str,sha:str,runner:Callable[...,Any]=subprocess.run)->dict[str,Any]:
    if SHA.fullmatch(sha) is None: raise ValueError('exact candidate SHA required')
    result=read_gh(repo,f'commits/{sha}/check-runs?per_page=100',runner)
    if not isinstance(result,dict) or not isinstance(result.get('check_runs'),list):
        return {'status':'unknown','reason':'invalid_ci_check_results','checks':[]}
    checks=[]
    for item in result['check_runs']:
        if not isinstance(item,dict):
            return {'status':'unknown','reason':'invalid_ci_check_record','checks':[]}
        name=item.get('name');status=item.get('status');conclusion=item.get('conclusion')
        if not isinstance(name,str) or status not in {'queued','in_progress','completed','waiting','pending','requested'}:
            return {'status':'unknown','reason':'incomplete_ci_check_record','checks':[]}
        checks.append({'name':name[:128],'status':status,'conclusion':str(conclusion or 'pending')[:30]})
    total=result.get('total_count')
    if not isinstance(total,int) or total>len(checks):
        return {'status':'unknown','reason':'truncated_ci_check_results','checks':checks}
    if not checks:
        overall,reason='unknown','no_ci_checks_reported'
    elif any(c['status']=='completed' and c['conclusion'] not in {'success','neutral','skipped'} for c in checks):
        overall,reason='failed','one_or_more_ci_checks_failed'
    elif any(c['status']!='completed' for c in checks):
        overall,reason='pending','ci_checks_still_running'
    else:
        overall,reason='reported_passing','github_ci_checks_complete'
    return {'status':overall,'reason':reason,'candidate_sha':sha,'check_count':len(checks),'checks':checks,
            'advisory_only':True}


def pr_file_inventory(repo:str,prs:list[int],runner:Callable[...,Any]=subprocess.run)->dict[str,Any]:
    if not isinstance(prs,list) or not 1<=len(prs)<=MAX_PRS or len(set(prs))!=len(prs) or any(type(x)is not int or x<1 for x in prs):
        raise ValueError('invalid bounded PR inventory')
    items=[];incomplete=[]
    for number in prs:
        payload=read_gh(repo,f'pulls/{number}/files?per_page=100',runner)
        if not isinstance(payload,list) or not payload or len(payload)>=100:
            incomplete.append(number);continue
        files=[]
        for row in payload:
            if not isinstance(row,dict) or not isinstance(row.get('filename'),str):
                incomplete.append(number);files=[];break
            path=row['filename']
            if len(path)>300 or path.startswith('/') or '..' in path.split('/'):
                incomplete.append(number);files=[];break
            files.append(path)
        if not files:continue
        # Directory membership is NOT semantic overlap. Infer only exact file
        # collisions here; shared contracts require independently declared
        # dependency metadata and semantic review before admission.
        items.append({'id':f'PR-{number}','files':files,'components':[]})
    return {'status':'complete' if not incomplete else 'incomplete','items':items,
            'missing_or_truncated_prs':incomplete,'semantic_conflicts_verified':False}
