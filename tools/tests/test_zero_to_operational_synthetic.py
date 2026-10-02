from __future__ import annotations

from pathlib import Path

from tools.zero_to_operational_synthetic import (
    run_synthetic_zero_to_operational,
)


ROOT = Path(__file__).resolve().parents[2]


def test_synthetic_zero_to_operational_exercises_full_deployability_chain(tmp_path):
    receipt = run_synthetic_zero_to_operational(
        repository_root=ROOT,
        workspace=tmp_path / "acceptance",
    )
    failures = [
        (item.phase, item.summary)
        for item in receipt.phases
        if item.status != "PASS"
    ]
    assert failures == []
    assert receipt.status == "PASS"
    assert receipt.deployability_proven is False
    assert receipt.production_authorized is False
    assert len(receipt.phases) == 17
