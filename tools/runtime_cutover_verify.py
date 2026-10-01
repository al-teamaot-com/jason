#!/usr/bin/env python3
"""Bounded post-cutover verification for the production Jason runtime."""

from __future__ import annotations

import argparse
import subprocess
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RuntimeState:
    image_id: str
    revision: str
    health: str


def _docker_value(container: str, template: str) -> str:
    completed = subprocess.run(
        ["docker", "inspect", container, "--format", template],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "docker inspect failed")
    return completed.stdout.strip()

def inspect_runtime(container: str) -> RuntimeState:
    return RuntimeState(
        image_id=_docker_value(container, "{{.Image}}"),
        revision=_docker_value(
            container,
            '{{index .Config.Labels "com.teamaot.jason.source_revision"}}',
        ),
        health=_docker_value(container, "{{.State.Health.Status}}"),
    )


def verify_runtime_cutover(
    *,
    container: str,
    expected_image_id: str,
    expected_revision: str,
    attempts: int = 30,
    interval: float = 1.0,
    inspect_fn: Callable[[str], RuntimeState] = inspect_runtime,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> RuntimeState:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last_state: RuntimeState | None = None
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            state = inspect_fn(container)
            last_state = state
            last_error = None
        except Exception as exc:
            last_error = exc
            print(f"POST_CUTOVER_VERIFY_ATTEMPT={attempt} RESULT=WAIT INSPECT_ERROR={type(exc).__name__}")
            if attempt < attempts:
                sleep_fn(interval)
            continue

        if state.image_id != expected_image_id:
            raise RuntimeError(
                "running image does not match candidate: "
                f"expected={expected_image_id} actual={state.image_id}"
            )
        if state.revision != expected_revision:
            raise RuntimeError(
                "running revision does not match source: "
                f"expected={expected_revision} actual={state.revision}"
            )

        if state.health == "healthy":
            print(f"POST_CUTOVER_VERIFY_ATTEMPT={attempt} RESULT=PASS")
            return state

        print(
            f"POST_CUTOVER_VERIFY_ATTEMPT={attempt} RESULT=WAIT "
            f"HEALTH={state.health or 'unknown'}"
        )
        if attempt < attempts:
            sleep_fn(interval)
    if last_state is not None:
        raise RuntimeError(
            "running container did not reach Docker healthy state within bounded verification: "
            f"health={last_state.health or 'unknown'}"
        )
    raise RuntimeError(
        "running container could not be inspected within bounded verification: "
        f"{type(last_error).__name__ if last_error else 'unknown'}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", required=True)
    parser.add_argument("--expected-image-id", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--interval", type=float, default=1.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        state = verify_runtime_cutover(
            container=args.container,
            expected_image_id=args.expected_image_id,
            expected_revision=args.expected_revision,
            attempts=args.attempts,
            interval=args.interval,
        )
    except Exception as exc:
        print("POST_CUTOVER_VERIFY=FAIL")
        print(f"REASON={exc}")
        return 1

    print("POST_CUTOVER_VERIFY=PASS")
    print(f"RUNNING_IMAGE_ID={state.image_id}")
    print(f"RUNNING_REVISION={state.revision}")
    print(f"RUNTIME_HEALTH={state.health}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
