#!/usr/bin/env python3
"""Source-only exact catalog root worker + projection rebind plan.

No --apply, sudo, Owner consent minting, privileged read, Docker mutation,
policy write, systemd control, freeze removal, or provider write. Independent
native Owner-approved root transaction is REQUIRED after four-unit drift repair.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import stat
import sys
from typing import Any, Mapping

from tools.catalog_scoped_root_install_plan import canonical, repo_revision, source_git

SHA=re.compile(r'^[0-9a-f]{40}$')
DIGEST=re.compile(r'^[0-9a-f]{64}$')
ACTION='catalog-root-worker-and-projection-rebind-v1'
WORKER=Path('/usr/local/lib/jason/release_host_reconcile_worker.py')
PROJECTION=Path('/usr/local/lib/jason/catalog-scoped-promotion/tools/pmv4_mcp_projection.py')
POLICY=Path('/etc/jason-owner-release/catalog-scoped-promotion-installed.json')
FREEZE=Path('/var/lib/jason/openclaw/release-manager/production-deployment-freeze')
ALLOWED=('tools/release_host_reconcile_worker.py','tools/pmv4_mcp_projection.py')


class CatalogProjectionRebindDenied(PermissionError):pass


def fail(code:str):raise CatalogProjectionRebindDenied('CATALOG_PROJECTION_REBIND_'+code)


def read_old_root_plan(path:Path)->dict[str,Any]:
    if (path.is_symlink() or not path.is_file() or path.stat().st_size>200000):
        fail('OLD_APPROVED_PLAN_MISSING')
    doc=json.loads(path.read_bytes())
    if not isinstance(doc,dict) or doc.get('status')!='SOURCE_ONLY_ROOT_INSTALL_PREPARED_NOT_AUTHORIZED':
        fail('OLD_APPROVED_PLAN_INVALID')
    m=dict(doc)
    claimed=m.pop('install_plan_sha256',None)
    if (not isinstance(claimed,str) or sha256(canonical(m)).hexdigest()!=claimed
            or doc.get('production_mutations') is not False
            or doc.get('owner_approval_recorded') is not False):
        fail('OLD_APPROVED_PLAN_HASH_INVALID')
    return doc


def build(repo:Path,old:Mapping[str,Any],*,
          installed_worker:Path=WORKER,freeze:Path=FREEZE,
          source_main_sha:str|None=None,
          git_blob:Any=None)->dict[str,Any]:
    """Build exact source-only intent; not a signed release or approval."""
    if (not isinstance(old,Mapping) or not isinstance(old.get('root_policy_after_separate_approval'),Mapping)
            or len(old.get('root_file_plan',[]))!=17):
        fail('OLD_ROOT_INSTALL_SCOPE_CHANGED')
    main=source_main_sha or repo_revision(repo)
    if not isinstance(main,str) or not SHA.fullmatch(main):fail('PROTECTED_MAIN_INVALID')
    if main==old.get('source_sha'):fail('SOURCE_ONLY_UPDATE_NOT_NEEDED')
    old_policy=dict(old['root_policy_after_separate_approval'])
    old_worker=old.get('root_file_plan',[])
    expected_old=next((e for e in old_worker if isinstance(e,Mapping)
              and e.get('destination')==str(WORKER)),None)
    if (not isinstance(expected_old,Mapping) or old_policy.get('source_sha')!=old.get('source_sha')
            or old_policy.get('root_worker_sha256')!=expected_old.get('sha256')
            or expected_old.get('sha256')!=sha256(installed_worker.read_bytes()).hexdigest()):
        fail('INSTALLED_ROOT_WORKER_NOT_ORIGINAL_APPROVED')
    meta=installed_worker.lstat()
    if (installed_worker.is_symlink() or not stat.S_ISREG(meta.st_mode)
            or meta.st_uid!=0 or stat.S_IMODE(meta.st_mode)!=0o755
            or meta.st_nlink!=1):fail('ROOT_WORKER_OWNER_OR_MODE_DRIFT')
    frozen=freeze.read_bytes()
    if (sha256(frozen).hexdigest()!=old.get('freeze_sha256')
            or len(frozen)>4096 or len(frozen)<1):
        fail('ORIGINAL_FREEZE_CHANGED')
    frozen_stat=freeze.lstat()
    if (freeze.is_symlink() or not stat.S_ISREG(frozen_stat.st_mode)
            or stat.S_IMODE(frozen_stat.st_mode)!=0o600):
        fail('FREEZE_MODE_CHANGED')
    if PROJECTION.exists() or PROJECTION.is_symlink():
        fail('PINNED_PROJECTION_ALREADY_INSTALLED_REQUIRE_REVIEW')
    getter=git_blob or source_git
    blobs={rel:getter(repo,'show',main+':'+rel) for rel in ALLOWED}
    if any(not b or len(b)>262144 for b in blobs.values()):
        fail('SOURCE_BLOB_UNAVAILABLE')
    if b'"tools/pmv4_mcp_projection.py"' not in blobs[ALLOWED[0]]:
        fail('WORKER_DOES_NOT_PIN_PROJECTION')
    if b'from pmv4_mcp_projection import (' not in getter(repo,'show',main+':tools/deploy_live_container.py'):
        fail('NATIVE_DEPLOY_HELPER_DEPENDENCY_CHANGED')
    if b'--preflight' not in getter(repo,'show',main+':tools/deploy_live_container.py'):
        fail('NATIVE_READONLY_PREFLIGHT_CHANGED')
    new_policy=dict(old_policy)
    new_policy['source_sha']=main
    new_policy['root_worker_sha256']=sha256(blobs[ALLOWED[0]]).hexdigest()
    if set(new_policy)!=set(old_policy) or any(new_policy[k]!=old_policy[k]
           for k in old_policy if k not in ('source_sha','root_worker_sha256')):
        fail('OTHER_ROOT_POLICY_FIELD_CHANGED')
    result={
        'schema_version':'1.0','action':ACTION,
        'status':'SOURCE_ONLY_REBIND_PREP_NOT_AUTHORIZED',
        'current_protected_main_sha':main,
        'original_install_source_sha':old['source_sha'],
        'original_install_plan_sha256':old['install_plan_sha256'],
        'existing_root_worker_sha256':old_policy['root_worker_sha256'],
        'original_freeze_sha256':old['freeze_sha256'],
        'existing_root_policy_expected_sha256':sha256(canonical(old_policy)+b'\n').hexdigest(),
        'updated_root_policy_sha256':sha256(canonical(new_policy)+b'\n').hexdigest(),
        'updated_root_policy_exactly':new_policy,
        'root_install_targets':[
            {'source':ALLOWED[0],'destination':str(WORKER),'sha256':sha256(blobs[ALLOWED[0]]).hexdigest(),
             'mode':'0755','owner':'root:root','operation':'atomic_replace_with_original_backup'},
            {'source':ALLOWED[1],'destination':str(PROJECTION),'sha256':sha256(blobs[ALLOWED[1]]).hexdigest(),
             'mode':'0644','owner':'root:root','operation':'create_only'},
        ],
        'original_policy_preserved_except':['source_sha','root_worker_sha256'],
        # The root-owned bootstrap recovery timer still compares the *old*
        # catalog root policy against the original approved install plan. It
        # must be explicitly and atomically superseded by the already-running
        # scoped catalog recovery control during a fresh Owner-approved native
        # release, not left polling an expected policy change as drift.
        'requires_bootstrap_recovery_supersession':True,
        'existing_bootstrap_recovery_timer':'jason-catalog-root-bootstrap-recovery.timer',
        'bootstrap_recovery_timer_retirement_separately_approved':False,
        'catalog_recovery_timer_must_remain_active':True,
        'requires_rollback_of_bootstrap_timer_on_failure':True,
        'requires_four_unit_drift_reconciled':True,
        'requires_native_breaker_closed':True,
        'requires_original_freeze_unchanged':True,
        'requires_native_production_lock':True,
        'requires_pm_host_mutation_lock':True,
        'requires_fresh_signed_exact_owner':True,
        'requires_root_only_backup_rollback_readback':True,
        'provider_write_authorized':False,
        'runtime_mcp_promotion_authorized':False,
        'new_global_owner_allowlist':False,
        'production_mutations':False,
        'signed_owner_proof_attached':False,
    }
    result['plan_sha256']=sha256(canonical(result)).hexdigest()
    return result


def main()->int:
    parser=argparse.ArgumentParser(description='Source-only exact catalog worker/projection rebind plan')
    parser.add_argument('--repo',required=True,type=Path)
    parser.add_argument('--original-install-plan',required=True,type=Path)
    parser.add_argument('--expected-main-sha',required=True)
    args=parser.parse_args()
    repo=args.repo.expanduser().resolve(strict=True)
    remote=repo_revision(repo)
    if remote!=args.expected_main_sha:fail('PROTECTED_MAIN_CHANGED')
    old=read_old_root_plan(args.original_install_plan)
    result=build(repo,old,source_main_sha=remote)
    assert repo_revision(repo)==remote
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
