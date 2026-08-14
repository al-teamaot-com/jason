#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import uuid
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

from connectors.core.contracts import ConnectorContext
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from orchestrator.openai_semantic_intent_translation import (
    OpenAISemanticIntentTranslator,
)


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


CATALOG: dict[str, tuple[str, ...]] = {
    "endpoint": (
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
    ),
    "management_site": (
        "sites",
    ),
    "alert": (
        "alerts",
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return parsed


def resolve_api_key(openbao_url: str) -> str:
    resolver = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=ROLE_ID,
        secret_id_path=SECRET_ID,
    )

    values = dict(
        resolver.resolve(
            "openai.semantic_intent",
            ConnectorContext(
                correlation_id=(
                    "semantic-benchmark-"
                    + uuid.uuid4().hex
                ),
                principal_id="semantic-benchmark",
                organization_id="aot",
                client_id=None,
                capability="semantic.intent.translate",
                mode="observe",
            ),
        )
    )

    try:
        api_key = str(values["api_key"]).strip()
        if not api_key:
            raise RuntimeError(
                "OpenAI semantic API key resolved empty"
            )
        return api_key
    finally:
        values.clear()


def classify(
    *,
    actual_resource: str | None,
    actual_concepts: tuple[str, ...],
    expected_resource: str,
    expected_concepts: tuple[str, ...],
) -> tuple[str, list[str], list[str]]:
    if actual_resource is None:
        return (
            "unresolved",
            list(expected_concepts),
            [],
        )

    if actual_resource != expected_resource:
        return (
            "wrong_resource",
            list(expected_concepts),
            list(actual_concepts),
        )

    expected = set(expected_concepts)
    actual = set(actual_concepts)

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)

    if not missing and not extra:
        return "exact", [], []

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

    scenario_doc = load_json(SCENARIOS)
    expectation_doc = load_json(EXPECTATIONS)

    scenarios = scenario_doc.get("scenarios")
    expectations = expectation_doc.get("scenarios")

    if not isinstance(scenarios, list):
        raise ValueError(
            "realistic scenario catalog is invalid"
        )
    if not isinstance(expectations, dict):
        raise ValueError(
            "semantic expectation catalog is invalid"
        )

    if args.limit > 0:
        scenarios = scenarios[: args.limit]

    api_key = resolve_api_key(args.openbao_url)

    translator = OpenAISemanticIntentTranslator(
        api_key=api_key,
        transport=BenchmarkJsonHttpTransport(),
        model=args.model,
    )

    results: list[dict[str, Any]] = []

    totals = {
        "exact": 0,
        "over_selected": 0,
        "under_selected": 0,
        "mixed": 0,
        "wrong_resource": 0,
        "unresolved": 0,
        "error": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    try:
        for index, scenario in enumerate(
            scenarios,
            start=1,
        ):
            scenario_id = str(scenario["id"])
            question = str(scenario["question"])

            expected = expectations.get(scenario_id)
            if not isinstance(expected, dict):
                raise ValueError(
                    f"missing benchmark expectation: {scenario_id}"
                )

            expected_resource = str(
                expected["resource_type"]
            )
            expected_concepts = tuple(
                str(item)
                for item in expected["concepts"]
            )

            grounded_selectors = {}

            # Grounding is deterministic benchmark setup,
            # not semantic interpretation.
            if "AOT-50282" in question.upper():
                grounded_selectors["endpoint"] = {
                    "hostname": "AOT-50282",
                }

            print(
                f"[{index:02d}/{len(scenarios):02d}] "
                f"{scenario_id}: {question}"
            )

            try:
                outcome = (
                    translator.translate_with_usage(
                        text=question,
                        eligible_resources=CATALOG,
                        grounded_selectors=grounded_selectors,
                    )
                )

                totals["input_tokens"] += (
                    outcome.usage.input_tokens
                )
                totals["output_tokens"] += (
                    outcome.usage.output_tokens
                )
                totals["total_tokens"] += (
                    outcome.usage.total_tokens
                )

                if outcome.translation is None:
                    actual_resource = None
                    actual_concepts: tuple[str, ...] = ()
                    confidence = 0.0
                else:
                    actual_resource = (
                        outcome.translation.resource_type
                    )
                    actual_concepts = (
                        outcome.translation.requested_concepts
                    )
                    confidence = (
                        outcome.translation.confidence
                    )

                status, missing, extra = classify(
                    actual_resource=actual_resource,
                    actual_concepts=actual_concepts,
                    expected_resource=expected_resource,
                    expected_concepts=expected_concepts,
                )

                totals[status] += 1

                results.append(
                    {
                        "id": scenario_id,
                        "category": scenario.get(
                            "category"
                        ),
                        "question": question,
                        "status": status,
                        "expected": {
                            "resource_type":
                                expected_resource,
                            "concepts":
                                list(expected_concepts),
                        },
                        "actual": {
                            "resource_type":
                                actual_resource,
                            "concepts":
                                list(actual_concepts),
                            "confidence":
                                confidence,
                        },
                        "missing_concepts": missing,
                        "extra_concepts": extra,
                        "usage": {
                            "input_tokens":
                                outcome.usage.input_tokens,
                            "output_tokens":
                                outcome.usage.output_tokens,
                            "total_tokens":
                                outcome.usage.total_tokens,
                        },
                    }
                )

                print(
                    "    "
                    + status.upper()
                    + " -> "
                    + (
                        ", ".join(actual_concepts)
                        if actual_concepts
                        else "<unresolved>"
                    )
                )

            except Exception as error:
                totals["error"] += 1

                results.append(
                    {
                        "id": scenario_id,
                        "category": scenario.get(
                            "category"
                        ),
                        "question": question,
                        "status": "error",
                        "expected": expected,
                        "error_type":
                            type(error).__name__,
                        "error_message":
                            str(error)[:500],
                    }
                )

                print(
                    "    ERROR -> "
                    f"{type(error).__name__}: "
                    f"{str(error)[:250]}"
                )

    finally:
        api_key = ""

    completed = len(results)
    exact = totals["exact"]

    accuracy = (
        exact / completed
        if completed
        else 0.0
    )

    report = {
        "benchmark": "openai-semantic-intent",
        "model": args.model,
        "scenario_count": completed,
        "exact_accuracy": accuracy,
        "totals": totals,
        "catalog": {
            key: list(value)
            for key, value in CATALOG.items()
        },
        "results": results,
    }

    args.output.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "========== BENCHMARK SUMMARY =========="
    )
    print(f"MODEL={args.model}")
    print(f"SCENARIOS={completed}")
    print(f"EXACT={totals['exact']}")
    print(
        f"EXACT_ACCURACY={accuracy:.1%}"
    )
    print(
        "OVER_SELECTED="
        f"{totals['over_selected']}"
    )
    print(
        "UNDER_SELECTED="
        f"{totals['under_selected']}"
    )
    print(f"MIXED={totals['mixed']}")
    print(
        "WRONG_RESOURCE="
        f"{totals['wrong_resource']}"
    )
    print(
        f"UNRESOLVED={totals['unresolved']}"
    )
    print(f"ERRORS={totals['error']}")
    print(
        "INPUT_TOKENS="
        f"{totals['input_tokens']}"
    )
    print(
        "OUTPUT_TOKENS="
        f"{totals['output_tokens']}"
    )
    print(
        "TOTAL_TOKENS="
        f"{totals['total_tokens']}"
    )
    print(f"REPORT={args.output}")
    print(
        "======================================="
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
