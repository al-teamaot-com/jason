import importlib.util
from pathlib import Path


def load():
    path = Path(__file__).resolve().parents[1] / "work_item_exporter.py"
    spec = importlib.util.spec_from_file_location("work_items", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_metrics_render_support_and_todo_metadata(tmp_path):
    module = load()
    module.SUPPORT = tmp_path / "SUPPORT.md"
    module.TODO = tmp_path / "TODO.md"
    module.SUPPORT.write_text(
        "# Support\n\n"
        "| ID | Priority | Status | Item | Current blocker / evidence | Acceptance criteria |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| SUPPORT-CAP-101 | P1 | Open | Test support issue | SECRET EVIDENCE | SECRET ACCEPTANCE |\n",
        encoding="utf-8",
    )
    module.TODO.write_text(
        "# TODO\n\n"
        "### TODO-REQ-101 — Test requested capability\n\n"
        "- **Priority:** P2\n"
        "- **Status:** Proposed\n"
        "- **Idea:** SECRET IDEA\n",
        encoding="utf-8",
    )
    metrics = module.render_metrics()
    assert 'jason_work_items_total{list="support"} 1' in metrics
    assert 'jason_work_items_total{list="todo"} 1' in metrics
    assert 'item_id="SUPPORT-CAP-101"' in metrics
    assert 'item_id="TODO-REQ-101"' in metrics
    assert 'title="Test support issue"' in metrics
    assert 'title="Test requested capability"' in metrics
    for secret in ("SECRET EVIDENCE", "SECRET ACCEPTANCE", "SECRET IDEA"):
        assert secret not in metrics
