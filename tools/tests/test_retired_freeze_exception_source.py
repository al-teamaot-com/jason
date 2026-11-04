"""Exact-source regression: no expired one-time freeze exception remains requested."""
from __future__ import annotations
import subprocess
from pathlib import Path
from tools import release_manager_host_runner as runner

REPO=Path(__file__).resolve().parents[2]


def test_source_retirement_leaves_no_one_transaction_exception():
    assert not (REPO/'config/production-deployment-freeze-exception.json').exists()
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    assert len(sha)==40
    # Candidate-bound Git inspection, not a filesystem-only configuration check.
    assert runner.declared_one_transaction_freeze_exception(REPO,sha) is None


def test_retired_exception_does_not_disable_freeze_marker_gate(tmp_path):
    marker=tmp_path/runner.PRODUCTION_FREEZE_MARKER
    marker.write_text('{"status":"active","scope":"manual-and-automatic-production-promotions"}\n')
    marker.chmod(0o600)
    import pytest
    with pytest.raises(runner.ReleaseManagerError, match='owner production deployment freeze is active'):
        runner.require_owner_production_deployment_unfrozen(tmp_path)
    assert marker.exists()
