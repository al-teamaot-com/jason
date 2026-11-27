#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ROOT / "implementation"
CONNECTORS = IMPLEMENTATION / "connectors" / "src"

for candidate in (
    str(ROOT),
    str(IMPLEMENTATION),
    str(CONNECTORS),
):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)



SCENARIOS = (
    ROOT
    / "config"
    / "user_simulation"
    / "realistic-read-scenarios.json"
)

EXPECTATIONS = (
    ROOT
    / "config"
    / "user_simulation"
    / "semantic-intent-expectations.json"
)

ROLE_ID = Path(
    "/opt/jason/bootstrap/secrets/openbao/"
    "openai-semantic-intent-approle/role-id"
)

SECRET_ID = Path(
    "/opt/jason/bootstrap/secrets/openbao/"
    "openai-semantic-intent-approle/secret-id"
)


CONCEPT_CATALOG: tuple[str, ...] = (
    "last logged in user",
    "LAN IP address",
    "WAN IP address",
    "operating system",
    "operating system display version",
    "operating system build",
    "processor model",
    "logical processor count",
    "total memory",
    "motherboard model",
    "bios version",
    "free disk space",
    "logical disks",
    "printers",
    "network adapters",
    "display adapters",
    "open alerts",
    "disk error evidence",
    "software",
    "sites",
)


def load_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return parsed


def resolve_api_key(openbao_url: str) -> str:
    # Historical live benchmark is no longer authorized; retain offline scoring.
    raise PermissionError("PAID_AI_API_PROHIBITED")


def classify(
    *,
    actual_concepts: tuple[str, ...],
    acceptable_concept_sets: tuple[
        tuple[str, ...],
        ...
    ],
    resolved: bool,
) -> tuple[str, list[str], list[str]]:
    if not resolved:
        expected = (
            acceptable_concept_sets[0]
            if acceptable_concept_sets
            else ()
        )
        return (
            "unresolved",
            list(expected),
            [],
        )

    actual = set(actual_concepts)

    for acceptable in acceptable_concept_sets:
        if actual == set(acceptable):
            return "exact", [], []

    # Use the closest acceptable set to make diagnostics meaningful.
    best = min(
        acceptable_concept_sets,
        key=lambda candidate: (
            len(
                set(candidate)
                ^ actual
            ),
            len(candidate),
        ),
    )

    expected = set(best)
    missing = sorted(
        expected - actual
    )
    extra = sorted(
        actual - expected
    )

    if missing and extra:
        return "mixed", missing, extra

    if missing:
        return "under_selected", missing, []

    return "over_selected", [], extra


class BenchmarkJsonHttpTransport:
    """Benchmark-only JSON transport with sanitized provider diagnostics."""

    def request(
        self,
        *,
        method,
        url,
        headers,
        params=None,
        json=None,
        timeout_seconds=30.0,
    ):
        del params

        body = None
        request_headers = {
            str(key): str(value)
            for key, value in headers.items()
        }

        if json is not None:
            body = __import__("json").dumps(
                dict(json),
                separators=(",", ":"),
            ).encode("utf-8")
            request_headers.setdefault(
                "Content-Type",
                "application/json",
            )

        request_headers.setdefault(
            "Accept",
            "application/json",
        )

        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method.upper(),
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raw = error.read()

            try:
                decoded = __import__("json").loads(
                    raw.decode("utf-8")
                )
            except Exception:
                raise RuntimeError(
                    f"OpenAI HTTP {error.code}: "
                    "response body was not valid JSON"
                ) from error

            provider_error = decoded.get("error", {})
            if not isinstance(provider_error, dict):
                provider_error = {}

            error_type = str(
                provider_error.get("type", "")
            )[:120]
            error_code = str(
                provider_error.get("code", "")
            )[:120]
            message = str(
                provider_error.get("message", "")
            )[:500]

            raise RuntimeError(
                f"OpenAI HTTP {error.code}; "
                f"type={error_type!r}; "
                f"code={error_code!r}; "
                f"message={message!r}"
            ) from error

        if not raw:
            return {}

        decoded = __import__("json").loads(
            raw.decode("utf-8")
        )

        if not isinstance(decoded, dict):
            raise RuntimeError(
                "OpenAI response was not a JSON object"
            )

        return decoded


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Observe-only live benchmark for Jason's "
            "OpenAI semantic intent translator."
        )
    )
    parser.add_argument(
        "--model",
        default="gpt-5.4-nano",
    )
    parser.add_argument(
        "--openbao-url",
        default="http://127.0.0.1:8200",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="0 runs every scenario",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "/tmp/jason-openai-semantic-benchmark.json"
        ),
    )
    args = parser.parse_args()
    print("BLOCKED: PAID_AI_API_PROHIBITED; historical live benchmark is retired", file=sys.stderr)
    return 2



if __name__ == "__main__":
    raise SystemExit(main())
