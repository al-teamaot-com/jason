import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

MODULE_PATH = TOOLS / "todo_release_bridge.py"
SPEC = importlib.util.spec_from_file_location("todo_release_bridge", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

SHA = "a" * 40


def release_record(state="closed"):
    return {
        "release_id": "release-" + "a" * 16,
        "state": state,
        "updated_at": "2026-10-02T23:45:00+00:00",
        "production": {
            "live_sha": SHA,
            "verified_at": "2026-10-02T23:44:00+00:00",
        },
    }


def test_release_id_requires_exact_sha():
    assert module.release_id(SHA) == "release-" + "a" * 16
    try:
        module.release_id("main")
    except module.TodoReleaseBridgeError:
        pass
    else:
        raise AssertionError("symbolic ref should be rejected")


def test_update_todo_text_requires_closed_release():
    source = """# Backlog

### TODO-OPS-010 — Build thing

- **Priority:** P1
- **Status:** Planned
- **Idea:** Build it.

### TODO-OPS-011 — Other thing

- **Priority:** P2
- **Status:** Planned
"""
    updated = module.update_todo_text(
        source,
        todo_id="TODO-OPS-010",
        release=release_record(),
    )
    assert "**Status:** Implemented" in updated
    assert "release-" + "a" * 16 in updated
    assert SHA in updated
    assert "**Implementation evidence:**" in updated
    other = updated.split("### TODO-OPS-011", 1)[1]
    assert "**Status:** Planned" in other

    try:
        module.update_todo_text(
            source,
            todo_id="TODO-OPS-010",
            release=release_record("production_eligible"),
        )
    except module.TodoReleaseBridgeError:
        pass
    else:
        raise AssertionError("TODO must not close before Release Manager closed")


def test_release_record_reads_exact_merge_sha(tmp_path):
    root = tmp_path
    path = root / "records" / f"{module.release_id(SHA)}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(release_record()), encoding="utf-8")
    observed = module.release_record(root, SHA)
    assert observed is not None
    assert observed["state"] == "closed"


def test_prepare_release_delegates_to_release_manager(tmp_path):
    runner = tmp_path / "release_manager_host_runner.py"
    runner.write_text("# runner", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    state = tmp_path / "state"
    state.mkdir()

    payload = {**release_record("production_eligible"), "release_id": module.release_id(SHA)}
    with patch.object(module, "run", return_value=json.dumps(payload)) as run_cmd:
        result = module.prepare_release(
            repo=tmp_path,
            merge_sha=SHA,
            release_runner=runner,
            release_source=source,
            release_state=state,
        )
    assert result["state"] == "production_eligible"
    args = run_cmd.call_args.args[0]
    assert "prepare" in args
    assert "--candidate-sha" in args
    assert SHA in args
    assert "--change-class" in args
    assert "todo" in args


def test_todo_and_development_metadata_patterns_are_exact():
    assert module.TODO_META.search("- TODO item: TODO-OPS-010")
    assert not module.TODO_META.search("- TODO: TODO-OPS-010")
    assert module.DEV_META.search("- Development issue: #123")
