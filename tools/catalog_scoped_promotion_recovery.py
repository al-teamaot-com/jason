#!/usr/bin/env python3
"""Root-only watch/recover for interrupted catalog scoped image transactions.

SOURCE ONLY. It is never launched from an engineering checkout. A separately
authorized root installer must deploy this exact script and its guarded
systemd timer before any scoped promotion can be production eligible.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any,Mapping

_BOOTSTRAP_ENTRYPOINT=Path('/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_recovery.py')
if Path(__file__).resolve()==_BOOTSTRAP_ENTRYPOINT and os.geteuid()==0:
    sys.path.insert(0,str(_BOOTSTRAP_ENTRYPOINT.parent.parent))

from tools.catalog_scoped_promotion import fail, validate_offer
from tools.catalog_scoped_promotion_host import NativeCatalogHost,ROOT,secure_read

INSTALLED=Path('/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_recovery.py')
TERMINAL={
    'freeze_restored_verified',
    'interrupted_rollback_verified',
    'interrupted_before_unfreeze_verified',
}


def run_once(*,host:NativeCatalogHost|None=None)->dict[str,Any]:
    """Never reuse a signed release approval to retry an interrupted promote."""
    if os.geteuid()!=0 or Path(__file__).resolve()!=INSTALLED:
        fail('RECOVERY_ROOT_INSTALLED_EXECUTION_REQUIRED')
    host=host or NativeCatalogHost()
    host.enforce_installed_production_trust()
    state=ROOT/'transactions'
    if not state.is_dir() or state.is_symlink() or state.stat().st_uid!=0:
        fail('RECOVERY_TRUSTED_JOURNAL_DIRECTORY_MISSING')
    attempts=sorted(state.glob('release-*.json'))
    if len(attempts)>1:
        fail('MULTIPLE_SCOPED_TRANSACTIONS_REQUIRE_REVIEW')
    if not attempts:return {'status':'idle_no_scoped_transaction'}
    path=attempts[0]
    journal=json.loads(secure_read(path))
    if (path.name!=str(journal.get('release_id'))+'.json'
            or journal.get('schema_version')!='1.0'):
        fail('RECOVERY_UNTRUSTED_JOURNAL')
    offer_file=ROOT/'offers'/(journal['release_id']+'.json')
    offer=validate_offer(json.loads(secure_read(offer_file,max_bytes=16384)))
    if (journal.get('manifest_sha256')!=offer['manifest_sha256']
            or journal.get('candidate_sha')!=offer['candidate_sha']
            or journal.get('rollback_sha')!=offer['rollback_sha']):
        fail('RECOVERY_OFFER_JOURNAL_DRIFT')
    if journal.get('status') in TERMINAL:
        if journal.get('outcome')=='production_pair_verified':
            # The protected release freeze is required to be back. The
            # independent root readback must be checked by the installed
            # policy before another catalog action can run.
            host._frozen(offer)
            host.active_offer=offer
            host.protected_before=journal.get('protected_services_before')
            host.verify_scoped_control_readback(offer,phase='steady_frozen')
            return {'status':'active_catalog_pair_verified'}
        return {'status':'resolved_previous_rollback'}
    # If the active native PM lock is held, defer without touching a live
    # transaction. Recovery is serialized with all PMV3/PMV4 release work.
    lock=host.state/'production-transaction.lock'
    if lock.is_symlink() or not lock.is_file():fail('RECOVERY_PRODUCTION_LOCK_MISSING')
    fd=os.open(lock,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status':'native_release_transaction_in_progress_no_change'}
        finally:
            # The recovery routine acquires the same native lock for the
            # actual procedure, so release our probe lock before calling it.
            fcntl.flock(fd,fcntl.LOCK_UN)
    finally:os.close(fd)
    return host.recover_interrupted(offer)


if __name__=='__main__':
    print(json.dumps(run_once(),sort_keys=True))
