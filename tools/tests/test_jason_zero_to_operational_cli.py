from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def test_synthetic_cli_writes_valid_non_proving_receipt(tmp_path):
    output = tmp_path / "receipt.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/jason_zero_to_operational.py"),
            "synthetic",
            "--workspace",
            str(tmp_path / "workspace"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PYTHONPATH": (
                str(ROOT)
                + ":"
                + str(ROOT / "implementation")
                + ":"
                + str(ROOT / "implementation/runtime_service/src")
            ),
        },
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    receipt = json.loads(output.read_text())
    assert summary["status"] == "PASS"
    assert summary["phase_count"] == 17
    assert summary["deployability_proven"] is False
    assert summary["production_authorized"] is False
    assert receipt["status"] == "PASS"
    assert receipt["mode"] == "synthetic"
    assert receipt["deployability_proven"] is False
    assert receipt["production_authorized"] is False

def test_host_preflight_subcommand_is_exposed():
    source = (
        ROOT / "tools/jason_zero_to_operational.py"
    ).read_text(encoding="utf-8")
    assert '"host-preflight"' in source
    assert "preflight_host_acceptance_plan" in source
