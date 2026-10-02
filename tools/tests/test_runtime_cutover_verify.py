from __future__ import annotations

import pytest

from tools.runtime_cutover_verify import RuntimeState, verify_runtime_cutover


def test_waits_for_docker_health_after_application_cutover():
    states = iter(
        (
            RuntimeState("sha256:new", "rev-new", "starting"),
            RuntimeState("sha256:new", "rev-new", "starting"),
            RuntimeState("sha256:new", "rev-new", "healthy"),
        )
    )
    sleeps: list[float] = []

    result = verify_runtime_cutover(
        container="jason-runtime",
        expected_image_id="sha256:new",
        expected_revision="rev-new",
        attempts=5,
        interval=0.25,
        inspect_fn=lambda _name: next(states),
        sleep_fn=sleeps.append,
    )

    assert result.health == "healthy"
    assert sleeps == [0.25, 0.25]

def test_image_mismatch_fails_closed_without_waiting():
    sleeps: list[float] = []
    with pytest.raises(RuntimeError, match="running image does not match candidate"):
        verify_runtime_cutover(
            container="jason-runtime",
            expected_image_id="sha256:new",
            expected_revision="rev-new",
            inspect_fn=lambda _name: RuntimeState("sha256:old", "rev-new", "healthy"),
            sleep_fn=sleeps.append,
        )
    assert sleeps == []


def test_revision_mismatch_fails_closed_without_waiting():
    with pytest.raises(RuntimeError, match="running revision does not match source"):
        verify_runtime_cutover(
            container="jason-runtime",
            expected_image_id="sha256:new",
            expected_revision="rev-new",
            inspect_fn=lambda _name: RuntimeState("sha256:new", "rev-old", "healthy"),
            sleep_fn=lambda _seconds: None,
        )

def test_health_timeout_fails_closed_after_bounded_wait():
    sleeps: list[float] = []
    with pytest.raises(RuntimeError, match="did not reach Docker healthy state"):
        verify_runtime_cutover(
            container="jason-runtime",
            expected_image_id="sha256:new",
            expected_revision="rev-new",
            attempts=3,
            interval=0.5,
            inspect_fn=lambda _name: RuntimeState("sha256:new", "rev-new", "starting"),
            sleep_fn=sleeps.append,
        )
    assert sleeps == [0.5, 0.5]


def test_transient_inspect_error_is_retried():
    calls = iter((RuntimeError("temporary inspect failure"), RuntimeState("sha256:new", "rev-new", "healthy")))
    def inspect(_name: str):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    result = verify_runtime_cutover(
        container="jason-runtime",
        expected_image_id="sha256:new",
        expected_revision="rev-new",
        attempts=2,
        interval=0,
        inspect_fn=inspect,
        sleep_fn=lambda _seconds: None,
    )
    assert result.health == "healthy"