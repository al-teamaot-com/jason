"""Offline exact source bundle for future separately signed root install."""
from pathlib import Path
import json
import os
import subprocess
import pytest
from tools import catalog_scoped_promotion_bundle as bundle


def git(repo,*args):
    done=subprocess.run(['git','-C',str(repo),*args],stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,check=True)
    return done.stdout.strip()


def example_repo(tmp_path):
    repo=tmp_path/'source'
    repo.mkdir()
    git(repo,'init','-q')
    for rel in bundle.FILES:
        path=repo/rel
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('# immutable reviewed source-only fixture: '+rel+'\n')
    git(repo,'add','.')
    git(repo,'-c','user.name=Jason Fixture','-c','user.email=jason@test.invalid',
        'commit','-qm','Source fixture')
    return repo,git(repo,'rev-parse','HEAD')


def test_only_exact_committed_blobs_staged_without_install(tmp_path):
    repo,sha=example_repo(tmp_path)
    destination=tmp_path/'stage'
    result=bundle.bundle_exact_source(repo,sha,destination,require_protected_main=False)
    assert destination.is_dir()
    assert result['source_sha']==sha
    assert result['status']=='source_only_not_installed'
    assert result['production_mutations'] is False
    assert result['release_approval_recorded'] is False
    assert result['root_installation_authorized'] is False
    assert set(result['files'])==set(bundle.FILES)
    for rel in bundle.FILES:
        assert (destination/rel).read_bytes()==(repo/rel).read_bytes()
    assert (destination/'SOURCE_ONLY_MANIFEST.json').is_file()
    assert not (tmp_path/'root-state').exists()


def test_changes_in_developer_checkout_not_included(tmp_path):
    repo,sha=example_repo(tmp_path)
    changed=repo/bundle.FILES[0]
    changed.write_text('MALICIOUS UNCOMMITTED CONTENT\n')
    result=bundle.bundle_exact_source(repo,sha,tmp_path/'out',require_protected_main=False)
    assert b'MALICIOUS' not in (tmp_path/'out'/bundle.FILES[0]).read_bytes()
    assert result['files'][bundle.FILES[0]]['bytes']!=changed.stat().st_size


@pytest.mark.parametrize('path',[
    Path('/opt/jason/catalog-staging'),Path('/etc/jason/catalog-staging'),
    Path('/var/lib/jason/catalog-staging'),Path('/usr/local/lib/jason/catalog-staging'),
])
def test_staging_production_paths_fail_before_mutation(tmp_path,path):
    repo,sha=example_repo(tmp_path)
    with pytest.raises(bundle.CatalogBundleDenied,match='PRODUCTION_PATH_DENIED'):
        bundle.bundle_exact_source(repo,sha,path,require_protected_main=False)


def test_missing_or_invalid_protected_source_refuses_staging(tmp_path):
    repo,sha=example_repo(tmp_path)
    with pytest.raises(bundle.CatalogBundleDenied,match='SOURCE_NOT_CURRENT_PROTECTED_MAIN'):
        bundle.bundle_exact_source(repo,sha,tmp_path/'reject',require_protected_main=True)
    assert not (tmp_path/'reject').exists()
    with pytest.raises(bundle.CatalogBundleDenied,match='EXACT_SOURCE_SHA_REQUIRED'):
        bundle.bundle_exact_source(repo,'main',tmp_path/'bad',require_protected_main=False)


def test_duplicate_output_or_symlink_is_never_followed(tmp_path):
    repo,sha=example_repo(tmp_path)
    target=tmp_path/'real'
    target.mkdir()
    symlink=tmp_path/'stage'
    symlink.symlink_to(target,target_is_directory=True)
    with pytest.raises(bundle.CatalogBundleDenied,match='OUTPUT_SYMLINK_DENIED'):
        bundle.bundle_exact_source(repo,sha,symlink,require_protected_main=False)
    assert list(target.iterdir())==[]
