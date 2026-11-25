"""Immutable bootstrap packet security: no production, no root or OAuth calls."""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import pytest
from tools import catalog_scoped_root_bootstrap_packet as b
from tools import catalog_scoped_root_install_plan as p
from tools.tests.test_catalog_scoped_root_install_transaction import evidence, plan


@pytest.fixture
def prepared(monkeypatch,plan):
    source=plan['source_sha']
    def git(repo,*args):
        assert args[0]=='show'
        assert args[1].startswith(source+':')
        return ('exact reviewed source: '+args[1]).encode()
    monkeypatch.setattr(b,'source_git',git)
    monkeypatch.setattr(p,'repo_revision',lambda repo:source)
    files={}
    for rel in b.FILES:
        files[rel]={'sha256':sha256(git(None,'show',source+':'+rel)).hexdigest(),
                    'bytes':len(git(None,'show',source+':'+rel))}
    original={'schema_version':'1.0','status':'source_only_not_installed',
              'source_sha':source,'files':files,'production_mutations':False,
              'root_installation_authorized':False,'bundle_sha256':'f'*64}
    return source,original


def test_exact_packet_pins_every_install_and_new_root_bootstrap_file(prepared,plan):
    source,original=prepared
    packet=b.exact_packet(Path('/tmp/mock-repo'),source,plan,original,b'verified root Owner jwt source')
    assert packet['status']=='SOURCE_ONLY_BOOTSTRAP_NOT_ROOT_INSTALLED'
    assert packet['bootstrap_staging_file_count']==len(b.SOURCES)
    assert len(packet['stage_files'])==len(b.SOURCES)
    assert packet['root_bootstrap_trust_policy']['protected_source_sha']==source
    assert packet['root_bootstrap_trust_policy']['plan_sha256']==plan['install_plan_sha256']
    assert packet['root_bootstrap_trust_policy']['install_scope_sha256']==plan['installation_scope_sha256']
    assert packet['signed_entra_owner_approval_recorded'] is False
    assert packet['privileged_installation_executed'] is False
    assert packet['automatic_root_elevation'] is False
    assert packet['runtime_mcp_promotion'] is False
    assert packet['provider_writes'] is False
    assert packet['packet_sha256']==sha256(b.canonical({k:v for k,v in packet.items() if k!='packet_sha256'})).hexdigest()


def test_packet_does_not_allow_source_main_to_move(prepared,plan,monkeypatch):
    source,original=prepared
    monkeypatch.setattr(p,'repo_revision',lambda repo:'e'*40)
    with pytest.raises(b.BootstrapPacketDenied,match='SOURCE_NO_LONGER_PROTECTED_MAIN'):
        b.exact_packet(Path('/tmp/repo'),source,plan,original,b'pinned source')


@pytest.mark.parametrize('change',[
    {'source_sha':'0'*40}, {'status':'installed'},
    {'production_mutations':True}, {'root_installation_authorized':True},
])
def test_original_bundles_do_not_claim_approval_or_mutation(prepared,plan,change):
    source,original=prepared
    modified=dict(original,**change)
    with pytest.raises(b.BootstrapPacketDenied,match='EXACT_ORIGINAL_BUNDLE_NOT_VERIFIED'):
        b.exact_packet(Path('/tmp/repo'),source,plan,modified,b'owner source')


def test_original_17_file_source_is_immutably_pinned(prepared,plan):
    source,original=prepared
    changed=deepcopy(original)
    first=next(iter(changed['files']))
    changed['files'][first]['sha256']='0'*64
    with pytest.raises(b.BootstrapPacketDenied,match='ORIGINAL_17_FILE_SOURCE_BUNDLE_CHANGED'):
        b.exact_packet(Path('/tmp/repo'),source,plan,changed,b'owner verifier')


def test_exact_staging_stays_out_of_production(prepared,plan,monkeypatch,tmp_path):
    source,original=prepared
    packet=b.exact_packet(Path('/tmp/repo'),source,plan,original,b'owner verifier')
    with pytest.raises(b.BootstrapPacketDenied,match='STAGING_DESTINATION_MUST_BE_NEW_TEMP_DIRECTORY'):
        b.write_staged(Path('/tmp/repo'),source,Path('/etc/jason-owner-release/bootstrap'),packet)
    with pytest.raises(b.BootstrapPacketDenied,match='STAGING_DESTINATION_MUST_BE_NEW_TEMP_DIRECTORY'):
        b.write_staged(Path('/tmp/repo'),source,Path('/var/lib/jason/catalog'),packet)


def test_operator_can_stage_only_readonly_source_files(prepared,plan,monkeypatch):
    source,original=prepared
    packet=b.exact_packet(Path('/tmp/repo'),source,plan,original,b'owner verifier')
    import tempfile
    parent=Path(tempfile.mkdtemp(prefix='catalog-bootstrap-ci-',dir='/tmp'))
    name=parent/'staged'
    try:
        b.write_staged(Path('/tmp/repo'),source,name,packet)
        for record in packet['stage_files']:
            file=name/record['source']
            assert file.is_file()
            assert sha256(file.read_bytes()).hexdigest()==record['sha256']
            assert file.stat().st_mode & 0o222==0
        assert (name/'ROOT_BOOTSTRAP_TRUST_POLICY.json').is_file()
        assert (name/'SOURCE_ONLY_BOOTSTRAP_PACKET.json').is_file()
    finally:
        import shutil
        if parent.exists():shutil.rmtree(parent)


def test_bootstrap_proof_cannot_be_reinterpreted_as_catalog_image_release(prepared,plan):
    source,original=prepared
    packet=b.exact_packet(Path('/tmp/repo'),source,plan,original,b'owner verifier')
    assert packet['root_bootstrap_trust_policy']['install_scope_sha256']!=plan['catalog_scope_sha256']
    assert packet['root_bootstrap_trust_policy']['plan_sha256']!=plan['signed_promotion_manifest_sha256']


def test_root_stage_script_only_installs_exact_bootstrap_and_requires_owner_flow(prepared,plan):
    source,original=prepared
    packet=b.exact_packet(Path('/tmp/repo'),source,plan,original,b'owner verifier')
    script=b.stage_script(packet,Path('/tmp/source-root-reviewed'))
    assert script.startswith('#!/bin/sh\nset -eu\numask 077\n')
    assert script.count('install -D -o root -g root -m')==len(packet['stage_files'])+1
    assert script.count('sha256sum -c -')==(len(packet['stage_files'])+1)*2
    assert 'root' in script
    assert 'APPROVE-EXACT-CATALOG-ROOT-INSTALL-ONLY' not in script
    assert 'sudo' not in script
    assert 'systemctl' not in script
    assert 'docker' not in script
    assert '/etc/sudoers' not in script
    assert script.index('--check-only') < script.index('--execute')
    assert plan['install_plan_sha256'] in script
    assert plan['installation_scope_sha256'] in script


def test_script_cannot_stage_foreign_root_target(prepared,plan):
    source,original=prepared
    packet=b.exact_packet(Path('/tmp/repo'),source,plan,original,b'owner verifier')
    packet['stage_files'][0]['destination']='/etc/sudoers.d/all-admins'
    packet['packet_sha256']=sha256(b.canonical({k:v for k,v in packet.items()
                                               if k!='packet_sha256'})).hexdigest()
    with pytest.raises(b.BootstrapPacketDenied,match='UNREVIEWED_ROOT_STAGE_DESTINATION'):
        b.stage_script(packet,Path('/tmp/staged'))
