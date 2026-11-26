"""SEC-007: catalog root trust must follow the *actual* approved install map.

Regression for live 2026-11-17 offer staging failure: the source-only 17-file
bundle did not create catalog-scoped-promotion/infrastructure, because the
approved two recovery unit destinations are /etc/systemd/system.  Never fix
that missing directory by weakening root trust or creating unapproved files.
"""
from pathlib import Path
import inspect
import pytest

from tools import catalog_scoped_root_install_plan as install_plan
from tools import release_host_reconcile_worker as worker
from tools.catalog_scoped_promotion_bundle import FILES


ROOT_BUNDLE = Path('/usr/local/lib/jason/catalog-scoped-promotion')


def test_every_reviewed_blob_maps_to_the_approved_live_destination():
    assert len(FILES) == 17
    for relative in FILES:
        actual = worker._catalog_scoped_installed_source_path(ROOT_BUNDLE, relative)
        reviewed = Path(install_plan.target_for_source(relative)['destination'])
        assert actual == reviewed, (relative, actual, reviewed)


def test_fixed_root_destinations_not_relocated_under_uninstalled_bundle():
    assert worker._catalog_scoped_installed_source_path(
        ROOT_BUNDLE, 'tools/release_host_reconcile_worker.py') == Path(
        '/usr/local/lib/jason/release_host_reconcile_worker.py')
    for suffix in ('service', 'timer'):
        relative = ('infrastructure/openclaw-operations/systemd/'
                    'jason-catalog-scoped-recovery.' + suffix)
        actual = worker._catalog_scoped_installed_source_path(ROOT_BUNDLE, relative)
        assert actual == Path('/etc/systemd/system/jason-catalog-scoped-recovery.'+suffix)
        assert ROOT_BUNDLE not in actual.parents


@pytest.mark.parametrize('relative', [
    '', '../etc/passwd', '/etc/passwd', 'tools/../root/keys',
    'infrastructure/../../etc/sudoers',
])
def test_unreviewed_parent_traversal_or_absolute_source_denied(relative):
    with pytest.raises(worker.HostReconcileError,
                       match='CATALOG_SCOPED_INSTALLED_SOURCE_PATH_INVALID'):
        worker._catalog_scoped_installed_source_path(ROOT_BUNDLE, relative)


def test_root_attestation_uses_correct_mapping_and_keeps_git_digest_gate():
    source = inspect.getsource(worker._trusted_catalog_scoped_promotion_module)
    assert 'path = _catalog_scoped_installed_source_path(trusted, relative)' in source
    assert 'trusted / "infrastructure"' not in source
    assert 'trusted / "infrastructure/openclaw-operations"' not in source
    assert 'sha256(path.read_bytes()).digest() != hashlib.sha256(expected).digest()' in source
    assert 'meta.st_uid != 0' in source
    assert 'path.is_symlink()' in source


def test_mapping_does_not_change_any_global_release_or_owner_identity():
    source = inspect.getsource(worker._catalog_scoped_installed_source_path)
    assert 'sudo' not in source
    assert 'os.chown' not in source
    assert 'subprocess' not in source
    assert 'docker' not in source.casefold()
    assert '/etc/jason-owner-release' not in source
