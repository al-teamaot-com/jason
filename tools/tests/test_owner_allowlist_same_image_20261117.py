"""No-production-IO tests of the exact local Owner MCP allowlist recovery."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


MODULE = Path(__file__).resolve().parents[1] / 'owner_allowlist_same_image_20261117.py'
spec = importlib.util.spec_from_file_location('catalog_owner_allowlist', MODULE)
assert spec is not None and spec.loader is not None
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def fixture_inspect(value: str) -> dict:
    return {
        'Image': subject.IMAGE,
        'Config': {'Env': ['UNRELATED_CONFIG=preserve', 'SECRET_REF=never_print',
                           subject.KEY + '=' + value],
                   'Labels': {'com.teamaot.jason.source_revision': subject.VERSION}},
        'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False},
        'Mounts': [{'Type': 'bind', 'Source': '/immutable/fixture',
                    'Destination': '/immutable/fixture', 'RW': False}],
        'NetworkSettings': {'Networks': {'private': {'Aliases': ['fixture']}}},
    }


def test_single_config_change_acceptance():
    previous = fixture_inspect(subject.OLD)
    current = fixture_inspect(subject.NEW)
    subject.other_config_unchanged(previous, current)


@pytest.mark.parametrize('mutation,error', [
    ('env', 'UNRELATED_ENVIRONMENT_CHANGED'),
    ('image', 'IMAGE_REPLACED'),
    ('bind', 'UNRELATED_MOUNTS_CHANGED'),
    ('network', 'NETWORK_OPTION_CHANGED'),
    ('security', 'UNRELATED_SECURITY_OR_PORT_CHANGE'),
])
def test_unrelated_mutation_fails_closed(mutation, error):
    previous = fixture_inspect(subject.OLD)
    current = fixture_inspect(subject.NEW)
    if mutation == 'env':
        current['Config']['Env'][0] = 'UNRELATED_CONFIG=changed'
    elif mutation == 'image':
        current['Image'] = 'sha256:' + 'f' * 64
    elif mutation == 'bind':
        current['Mounts'][0]['RW'] = True
    elif mutation == 'network':
        current['NetworkSettings']['Networks']['private']['Aliases'] = ['changed']
    elif mutation == 'security':
        current['HostConfig']['Privileged'] = True
    with pytest.raises(RuntimeError, match=error):
        subject.other_config_unchanged(previous, current)


def test_duplicate_environment_key_fails_closed():
    with pytest.raises(RuntimeError, match='DUPLICATE_ENVIRONMENT_KEY'):
        subject.environment({'Config': {'Env': ['X=1', 'X=2']}})


def test_apply_refuses_automated_non_owner_execution(monkeypatch):
    monkeypatch.setattr(subject.os, 'geteuid', lambda: 1000)
    with pytest.raises(RuntimeError, match='LOCAL_INDIVIDUAL_OWNER_SUDO_TTY_REQUIRED'):
        subject.do_apply('0' * 64)


def test_review_is_read_only_and_binds_identity_scope(monkeypatch, capsys):
    monkeypatch.setattr(subject, 'live', lambda expected=subject.OLD: {'Id': 'fixture-id'})
    monkeypatch.setattr(subject, 'cmd', lambda *a, **k: pytest.fail('review called subprocess'))
    monkeypatch.setattr(sys, 'argv', ['owner-allowlist', '--review'])
    subject.main()
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'review_only'
    assert result['no_mutations'] is True
    assert result['requires_human_local_sudo_approval'] is True
    assert result['owner_allowlist_current'] == 'person-al'
    assert result['owner_allowlist_proposed'] == subject.NEW
    assert result['scope_sha256'] == subject.DIGEST
    assert result['image_digest'] == subject.IMAGE


def test_scope_never_grants_production_release_authority():
    assert subject.SCOPE['new_code_or_image'] is False
    assert subject.SCOPE['other_configuration_changed'] is False
    assert subject.SCOPE['freeze_restored_byte_exact'] is True
    assert subject.SCOPE['changed_environment_key'] == subject.KEY
    assert subject.VERSION == 'd1b8c196dadd4b672ec8ba47075f27bb61c98d63'
