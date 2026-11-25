"""Safety-only tests for a second, exact Owner-attested source repair.

No Root identity, service mutations, Docker actions, credential access, or
original 40GB journal recreation are used in these tests.
"""
from hashlib import sha256
import json
import pytest
from tools import audit_journal_no_restore_worker as worker


def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()


def validate_worker_overlay(grant,source_sha,overlay,monkeypatch):
    monkeypatch.setattr(worker,'read_control',lambda *args:overlay)
    return worker.verified_reader_repair_source(grant,source_sha)


def test_exact_successor_does_not_rewrite_previous_approval(monkeypatch):
    prior={'scope_sha256':'a'*64,'source_sha256':'b'*64,'status':'recovery_authorized'}
    saved=canon(prior)
    updated='c'*64
    overlay={'schema_version':'1.0','action':worker.READER_REPAIR_ACTION,
        'owner_oid':worker.old.OWNER,'independently_verified_entra_owner':True,
        'root_release_finalized':True,'no_legacy_rebuild':True,'provider_calls':0,
        'previous_forward_grant_sha256':sha256(saved).hexdigest(),
        'worker_sha256':updated}
    validate_worker_overlay(prior,updated,overlay,monkeypatch)
    assert canon(prior)==saved


@pytest.mark.parametrize('field,value',[
    ('owner_oid','other'),('independently_verified_entra_owner',False),
    ('root_release_finalized',False),('no_legacy_rebuild',False),
    ('provider_calls',1),('action','UNRELATED'),('schema_version','2.0'),
    ('worker_sha256','0'*64),('previous_forward_grant_sha256','0'*64)])
def test_unreviewed_successor_denied(field,value,monkeypatch):
    prior={'scope_sha256':'a'*64,'source_sha256':'b'*64,'status':'recovery_authorized'}
    updated='c'*64
    overlay={'schema_version':'1.0','action':worker.READER_REPAIR_ACTION,
        'owner_oid':worker.old.OWNER,'independently_verified_entra_owner':True,
        'root_release_finalized':True,'no_legacy_rebuild':True,'provider_calls':0,
        'previous_forward_grant_sha256':sha256(canon(prior)).hexdigest(),
        'worker_sha256':updated}
    overlay[field]=value
    with pytest.raises(worker.JournalUnavailable,match='FORWARD_NEW_SIGNED_READER_REPAIR_REQUIRED'):
        validate_worker_overlay(prior,updated,overlay,monkeypatch)
