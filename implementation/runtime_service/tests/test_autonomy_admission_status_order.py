"""Prevent misleading unsupported totals for technician-owned discovery rows."""
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src/jason_runtime/autonomy_worker_runtime.py"

def test_non_intake_status_is_classified_before_scope_matching():
    source = SOURCE.read_text()
    method = source[source.index("class OperationalAutonomyWorker"): ] if "class OperationalAutonomyWorker" in source else source
    start = method.index("# Classify already-active technician tickets before playbook coverage.")
    match = method.index("scope = self._match_scope(item.context)",start)
    unsupported = method.index('"no_applicable_promoted_playbook"', match)
    assert start < match < unsupported
    assert method.count('"discovery_status_not_admissible"') >= 1
