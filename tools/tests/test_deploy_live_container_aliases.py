from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture()
def module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "deploy_live_container.py"
    spec = importlib.util.spec_from_file_location("deploy_live_container", path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _fake_image_id(state: dict[str, str], image: str) -> str:
    if image.startswith("sha256:"):
        return image
    if image not in state:
        raise RuntimeError(f"missing fake image tag: {image}")
    return state[image]


def test_promote_aliases_rotates_actual_previous_live_image(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    state = {
        "jason-runtime:production": "sha256:stale-production",
        "jason-runtime:local": "sha256:stale-production",
        "jason-runtime:rollback-current": "sha256:older-rollback",
    }

    def fake_run(args: list[str], **_: object) -> None:
        assert args[:2] == ["docker", "tag"]
        state[args[3]] = args[2]

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_image_id", lambda image: _fake_image_id(state, image))

    module._promote_image_aliases(
        candidate_id="sha256:new",
        previous_live_image_id="sha256:actual-previous-live",
        promote_tags=["jason-runtime:production", "jason-runtime:local"],
        rollback_tag="jason-runtime:rollback-current",
    )

    assert state["jason-runtime:production"] == "sha256:new"
    assert state["jason-runtime:local"] == "sha256:new"
    assert state["jason-runtime:rollback-current"] == "sha256:actual-previous-live"


def test_same_image_redeploy_does_not_replace_rollback_alias(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    state = {
        "jason-mcp:production": "sha256:same",
        "jason-mcp:rollback-current": "sha256:known-good-previous",
    }

    def fake_run(args: list[str], **_: object) -> None:
        assert args[:2] == ["docker", "tag"]
        state[args[3]] = args[2]

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_image_id", lambda image: _fake_image_id(state, image))

    module._promote_image_aliases(
        candidate_id="sha256:same",
        previous_live_image_id="sha256:same",
        promote_tags=["jason-mcp:production"],
        rollback_tag="jason-mcp:rollback-current",
    )

    assert state["jason-mcp:production"] == "sha256:same"
    assert state["jason-mcp:rollback-current"] == "sha256:known-good-previous"


def test_restore_aliases_restores_existing_tags_and_removes_new_tags(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    state = {
        "jason-runtime:production": "sha256:new",
        "jason-runtime:local": "sha256:new",
        "jason-runtime:rollback-current": "sha256:actual-previous-live",
    }
    snapshot = {
        "jason-runtime:production": "sha256:old-production",
        "jason-runtime:local": None,
        "jason-runtime:rollback-current": "sha256:old-rollback",
    }

    class Result:
        returncode = 0
        stdout = ""

    def fake_subprocess_run(args: list[str], **_: object) -> Result:
        if args[:2] == ["docker", "tag"]:
            state[args[3]] = args[2]
        elif args[:3] == ["docker", "image", "rm"]:
            state.pop(args[3], None)
        else:
            raise AssertionError(args)
        return Result()

    monkeypatch.setattr(module.subprocess, "run", fake_subprocess_run)

    module._restore_image_aliases(snapshot)

    assert state["jason-runtime:production"] == "sha256:old-production"
    assert "jason-runtime:local" not in state
    assert state["jason-runtime:rollback-current"] == "sha256:old-rollback"
