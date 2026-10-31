import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for name in ("pmv3_work_engine", "pmv3_scheduler"):
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

spec = importlib.util.spec_from_file_location(
    "pmv3_acceptance_harness", ROOT / "tools" / "pmv3_acceptance_harness.py"
)
harness = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = harness
spec.loader.exec_module(harness)


def test_end_to_end_acceptance(tmp_path):
    result = harness.run_acceptance(tmp_path)
    assert result["status"] == "pass"
    assert result["progress_percent"] == 100
    assert result["receipts"] == 6
    assert result["transient_attempts"] == 2
    assert result["approval_channel"] == "teams"
    assert result["validation_attempts"] == 2
