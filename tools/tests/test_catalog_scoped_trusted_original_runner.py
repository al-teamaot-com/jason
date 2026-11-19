"""Catalog trusted source keeps the root-install runner immutable across PMv4 main changes."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "release_host_reconcile_worker.py"
spec = importlib.util.spec_from_file_location("test_catalog_root_trusted_file_policy", SOURCE)
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

CURRENT = "a" * 40
PINNED = "01ba71c54d9dd0391734b16a92d0b292fc457ae9"
EXPECTED_RUNNER_SHA256 = "b194084a9a54fe024ae89784e2e75d54a26e1369ed65d824abed4ce958f58edf"


def test_only_reviewed_unchanged_root_runner_has_larger_size_allowance():
    assert worker._catalog_scoped_trusted_file_size_limit("tools/release_manager_host_runner.py") == 524288
    for other in (
        "tools/catalog_scoped_promotion_root.py",
        "tools/catalog_scoped_promotion_host.py",
        "tools/deploy_live_container.py",
        "tools/pmv4_mcp_projection.py",
        "implementation/kernel/catalog_scoped_promotion_contract.py",
        "docs/engineering/evidence/catalog-scope-admission-20261117.json",
    ):
        assert worker._catalog_scoped_trusted_file_size_limit(other) == 262144


def test_original_runner_remains_bound_to_exact_reviewed_root_install():
    assert worker.CATALOG_SCOPED_ORIGINAL_ROOT_SOURCE == PINNED
    assert worker.CATALOG_SCOPED_PINNED_RUNNER_SHA256 == EXPECTED_RUNNER_SHA256
    assert worker._catalog_scoped_trusted_source_ref(
        "tools/release_manager_host_runner.py", CURRENT
    ) == PINNED + ":tools/release_manager_host_runner.py"


@pytest.mark.parametrize("source", [
    "tools/catalog_scoped_promotion_host.py",
    "tools/catalog_scoped_promotion_root.py",
    "tools/pmv4_mcp_projection.py",
    "config/catalog-scoped-release-admission.json",
    "infrastructure/openclaw-operations/systemd/jason-catalog-scoped-recovery.timer",
])
def test_all_other_trusted_modules_must_match_current_protected_main(source):
    assert worker._catalog_scoped_trusted_source_ref(source, CURRENT) == CURRENT + ":" + source


def test_fails_closed_without_exact_historical_runner_hash():
    # The trust loader must still independently hash-check BOTH Git's original
    # blob and the on-disk root-owned file after the limited size exception.
    content = SOURCE.read_text()
    assert "CATALOG_SCOPED_ORIGINAL_RUNNER_SOURCE_DRIFT" in content
    assert "CATALOG_SCOPED_TRUSTED_SOURCE_DRIFT" in content
    assert "hashlib.sha256(expected).hexdigest() != CATALOG_SCOPED_PINNED_RUNNER_SHA256" in content
    assert "meta.st_size > _catalog_scoped_trusted_file_size_limit(relative)" in content
