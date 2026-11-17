"""Protected GitHub check attestor for one catalog source-only transaction.

Uses the existing host operator's GitHub read-only access; it can only query
protected source and GitHub CI, never mutate a repo, release, or provider.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from tools.catalog_scoped_promotion import fail

REPO = Path('/home/al/.local/lib/jason/engineering-source-repo')
REQUIRED_SECURITY = 'governed-security-regressions'
SHA = re.compile(r'^[0-9a-f]{40}$')


def _operator_git(*args:str, repo:Path=REPO)->bytes:
    command=['git','-c',f'safe.directory={repo}','-C',str(repo),*args]
    done=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                        timeout=30,check=False)
    if done.returncode:fail('GIT_PROVENANCE_UNAVAILABLE')
    return done.stdout


def _github_check_query(revision:str,page:int)->dict[str,Any]:
    if not SHA.fullmatch(revision) or not 1<=page<=10:
        fail('CI_SOURCE_OR_PAGE_INVALID')
    # GitHub CLI obtains the existing operator's bounded read session; it
    # never receives production keys, root secrets or a caller URL.
    api=(f'repos/al-teamaot-com/jason/commits/{revision}/check-runs'
         f'?per_page=100&page={page}')
    command=['runuser','-u','al','--','env',
             'HOME=/home/al','PATH=/usr/local/bin:/usr/bin:/bin',
             '/usr/bin/gh','api','-H','Accept: application/vnd.github+json',
             '-H','X-GitHub-Api-Version: 2022-11-28',api]
    done=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                        timeout=30,check=False)
    if done.returncode or len(done.stdout)>2_000_000:
        fail('PROTECTED_CI_QUERY_UNAVAILABLE')
    try:result=json.loads(done.stdout)
    except (ValueError,TypeError) as exc:
        raise PermissionError('CATALOG_SCOPED_PROMOTION_CI_RESPONSE_INVALID') from exc
    if not isinstance(result,dict) or not isinstance(result.get('check_runs'),list):
        fail('PROTECTED_CI_RESPONSE_SCHEMA_INVALID')
    return result


def check_catalog_protected_ci(revision:str, *,repo:Path=REPO)->dict[str,Any]:
    """Native production-gate check names plus the exact catalog SEC-007 job."""
    if not isinstance(revision,str) or SHA.fullmatch(revision) is None:
        fail('PROTECTED_CI_SOURCE_INVALID')
    try:
        policy=json.loads(_operator_git('show',revision+':config/development-release-coordinator.json',repo=repo))
    except (ValueError,TypeError) as exc:
        raise PermissionError('CATALOG_SCOPED_PROMOTION_CHECK_POLICY_INVALID') from exc
    names=policy.get('required_checks') if isinstance(policy,dict) else None
    if (not isinstance(names,list) or not names or len(names)>40
            or any(not isinstance(name,str) or not re.fullmatch(r'[a-z0-9_-]{3,100}',name)
                   for name in names) or len(set(names))!=len(names)):
        fail('REQUIRED_CHECKS_SOURCE_INVALID')
    required=list(names)
    if REQUIRED_SECURITY not in required:required.append(REQUIRED_SECURITY)
    latest:dict[str,dict[str,Any]]={}
    for page in range(1,11):
        items=_github_check_query(revision,page).get('check_runs')
        if len(items)>100:fail('PROTECTED_CI_PAGE_LIMIT_INVALID')
        for item in items:
            if not isinstance(item,dict):fail('PROTECTED_CI_RESULT_INVALID')
            name=item.get('name')
            if not isinstance(name,str):continue
            try:run_id=int(item.get('id',0))
            except (TypeError,ValueError):fail('PROTECTED_CI_ID_INVALID')
            if name not in latest or run_id>int(latest[name].get('id',0)):
                latest[name]=item
        if len(items)<100:break
    else:fail('PROTECTED_CI_PAGINATION_LIMIT')
    failures=[]
    for name in required:
        item=latest.get(name)
        if not item:failures.append(name+':missing')
        elif item.get('status')!='completed':failures.append(name+':pending')
        elif item.get('conclusion')!='success':failures.append(name+':'+str(item.get('conclusion')))
    return {'passed':not failures,'required':required,'failures':failures}
