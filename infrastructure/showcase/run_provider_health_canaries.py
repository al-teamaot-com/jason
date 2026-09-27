#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


ALLOWED_PROVIDERS = frozenset(
    {"autotask", "it_glue", "datto_rmm", "microsoft_graph"}
)
ALLOWED_ERROR_CLASSES = frozenset(
    {
        "none",
        "authority_denied",
        "information_release_denied",
        "timeout",
        "provider_unavailable",
        "provider_error",
        "unexpected_provider",
        "execution_failed",
        "runner_error",
    }
)


def _validate(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("canary payload must be an object")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported canary schema")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("canary results must be a list")
    seen = set()
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("canary result must be an object")
        provider = str(item.get("provider") or "")
        capability = str(item.get("capability") or "")
        error_class = str(item.get("error_class") or "")
        if provider not in ALLOWED_PROVIDERS:
            raise ValueError("unexpected provider in canary result")
        if not capability or capability in seen:
            raise ValueError("invalid or duplicate canary capability")
        seen.add(capability)
        if not isinstance(item.get("healthy"), bool):
            raise ValueError("healthy must be boolean")
        latency = item.get("latency_seconds")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)):
            raise ValueError("latency_seconds must be numeric")
        if latency < 0 or latency > 300:
            raise ValueError("latency_seconds outside bounded range")
        if error_class not in ALLOWED_ERROR_CLASSES:
            raise ValueError("unbounded canary error class")
        correlation_id = str(item.get("correlation_id") or "")
        if not correlation_id.startswith("corr_"):
            raise ValueError("invalid canary correlation id")
    return payload


def run(
    *,
    container: str,
    output_path: Path,
    timeout_seconds: int,
) -> dict:
    completed = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "python",
            "-m",
            "jason_mcp.provider_health_canary",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "governed provider canary runner failed inside MCP container"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("governed provider canary returned invalid JSON") from exc
    validated = _validate(payload)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".provider-health-canaries-",
        suffix=".json",
        dir=str(output_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(validated, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, output_path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
    return validated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="jason-mcp-pilot")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/var/lib/jason/provider-health-canaries.json"),
    )
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    run(
        container=args.container,
        output_path=args.output,
        timeout_seconds=args.timeout_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
