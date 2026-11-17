"""SEC-007: exact root catalog native dependency closure is immutable.

Regression: imported pinned deploy_live_container.py lacked the sibling
pmv4_mcp_projection.py and failed *before* the read-only --preflight.
Do not resolve it through a mutable checkout or unpinned import fallback.
"""
from __future__ import annotations
from hashlib import sha256
import inspect
from pathlib import Path
import shutil
import subprocess
import sys

from tools import release_host_reconcile_worker as worker

ROOT = Path(__file__).resolve().parents[2]
IMMUTABLE = Path('/usr/local/lib/jason/catalog-scoped-promotion')
PROJECTION = 'tools/pmv4_mcp_projection.py'


def test_root_worker_requires_pinned_projection_blob_from_protected_git():
    source = inspect.getsource(worker._trusted_catalog_scoped_promotion_module)
    assert '"tools/pmv4_mcp_projection.py"' in source
    assert '_catalog_scoped_installed_source_path(trusted, relative)' in source
    assert 'sha256(path.read_bytes()).digest() != hashlib.sha256(expected).digest()' in source
    assert 'meta.st_uid != 0' in source
    assert 'path.is_symlink()' in source
    assert worker._catalog_scoped_installed_source_path(IMMUTABLE, PROJECTION) == IMMUTABLE/PROJECTION


def test_pinned_native_deployer_requires_exact_sibling_projection(tmp_path):
    files = ('tools/deploy_live_container.py','tools/pmv4_mcp_projection.py')
    module = (tmp_path/'tools')
    module.mkdir()
    for relative in files:
        assert (ROOT/relative).is_file()
    shutil.copyfile(ROOT/files[0], module/'deploy_live_container.py')
    run = lambda: subprocess.run(
        [sys.executable,str(module/'deploy_live_container.py'),'--help'],
        capture_output=True,text=True,timeout=15,check=False)
    missing = run()
    assert missing.returncode != 0
    assert 'No module named' in missing.stderr and 'pmv4_mcp_projection' in missing.stderr
    shutil.copyfile(ROOT/files[1], module/'pmv4_mcp_projection.py')
    exact = run()
    assert exact.returncode == 0, exact.stderr
    assert '--preflight' in exact.stdout
    assert sha256((module/'pmv4_mcp_projection.py').read_bytes()).hexdigest() == sha256(
        (ROOT/PROJECTION).read_bytes()).hexdigest()


def test_no_preflight_import_ever_references_mutable_source_repository():
    root = inspect.getsource(worker._trusted_catalog_scoped_promotion_module)
    assert 'sys.modules' in root
    assert 'source_revision + ":" + relative' in root
    assert '/opt/jason/current/tools/pmv4_mcp_projection.py' not in root
    helper = (ROOT/'tools/deploy_live_container.py').read_text()
    assert 'from pmv4_mcp_projection import (' in helper
    assert 'exec(' not in helper[:1200]
