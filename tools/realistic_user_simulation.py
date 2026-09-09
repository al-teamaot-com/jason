#!/usr/bin/env python3
"""Run realistic observe-only user-language regression scenarios for Jason.

The harness deliberately evaluates semantic behavior rather than exact provider values.
It can consume captured responses or call a pluggable driver command. The driver receives
one question on stdin and scenario metadata through environment variables; its stdout is
used as Jason's response.

No provider credential, Teams token, or transport authority is embedded here. A real
Teams/OpenClaw driver can be supplied separately once it is implemented through the
approved authenticated ingress boundary.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIOS = REPO_ROOT / "config/user_simulation/realistic-read-scenarios.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / ".build/user-simulation"


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    category: str
    question: str
    expected: str
    response: str
    passed: bool
    reason: str


def _normalized(value: str) -> str:
    return " ".join(str(value).casefold().split())


def _contains(response: str, phrase: str) -> bool:
    return _normalized(phrase) in _normalized(response)


def _string_list(value: Any, *, field: str, scenario_id: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{scenario_id}: {field} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _string_groups(value: Any, *, field: str, scenario_id: str) -> tuple[tuple[str, ...], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{scenario_id}: {field} must be a list of string lists")
    groups: list[tuple[str, ...]] = []
    for index, group in enumerate(value, 1):
        if not isinstance(group, list) or not group or not all(isinstance(item, str) and item.strip() for item in group):
            raise ValueError(f"{scenario_id}: {field}[{index}] must contain non-empty strings")
        groups.append(tuple(item.strip() for item in group))
    return tuple(groups)


def load_scenarios(path: Path) -> tuple[dict[str, Any], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("scenario file must contain a JSON object")
    raw = payload.get("scenarios")
    if not isinstance(raw, list) or not raw:
        raise ValueError("scenario file must contain a non-empty scenarios list")

    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("every scenario must be an object")
        scenario = dict(item)
        scenario_id = str(scenario.get("id", "")).strip()
        category = str(scenario.get("category", "")).strip()
        question = str(scenario.get("question", "")).strip()
        if not scenario_id or not category or not question:
            raise ValueError("every scenario requires id, category, and question")
        if scenario_id in seen:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        seen.add(scenario_id)

        all_terms = _string_list(scenario.get("must_include_all"), field="must_include_all", scenario_id=scenario_id)
        any_terms = _string_list(scenario.get("must_include_any"), field="must_include_any", scenario_id=scenario_id)
        forbidden = _string_list(scenario.get("must_not_include"), field="must_not_include", scenario_id=scenario_id)
        groups = _string_groups(scenario.get("must_include_groups"), field="must_include_groups", scenario_id=scenario_id)
        if not all_terms and not any_terms and not groups:
            raise ValueError(f"{scenario_id}: at least one positive expectation is required")
        result.append(scenario)
    return tuple(result)


def expected_description(scenario: Mapping[str, Any]) -> str:
    parts: list[str] = []
    all_terms = tuple(scenario.get("must_include_all", ()))
    any_terms = tuple(scenario.get("must_include_any", ()))
    groups = tuple(scenario.get("must_include_groups", ()))
    forbidden = tuple(scenario.get("must_not_include", ()))
    if all_terms:
        parts.append("all: " + ", ".join(all_terms))
    if any_terms:
        parts.append("any: " + " | ".join(any_terms))
    for group in groups:
        parts.append("group: " + " | ".join(group))
    if forbidden:
        parts.append("forbid: " + ", ".join(forbidden))
    return "; ".join(parts)


def evaluate(scenario: Mapping[str, Any], response: str) -> ScenarioResult:
    scenario_id = str(scenario["id"])
    category = str(scenario["category"])
    question = str(scenario["question"])
    response = str(response or "").strip()
    failures: list[str] = []

    if not response:
        failures.append("empty response")

    for phrase in scenario.get("must_include_all", ()):
        if not _contains(response, str(phrase)):
            failures.append(f"missing required phrase {phrase!r}")

    any_terms = tuple(str(item) for item in scenario.get("must_include_any", ()))
    if any_terms and not any(_contains(response, phrase) for phrase in any_terms):
        failures.append("missing every allowed alternative: " + " | ".join(any_terms))

    for group in scenario.get("must_include_groups", ()):
        alternatives = tuple(str(item) for item in group)
        if not any(_contains(response, phrase) for phrase in alternatives):
            failures.append("missing required semantic group: " + " | ".join(alternatives))

    for phrase in scenario.get("must_not_include", ()):
        if _contains(response, str(phrase)):
            failures.append(f"contained forbidden phrase {phrase!r}")

    passed = not failures
    return ScenarioResult(
        scenario_id=scenario_id,
        category=category,
        question=question,
        expected=expected_description(scenario),
        response=response,
        passed=passed,
        reason="pass" if passed else "; ".join(failures),
    )


def load_responses(path: Path) -> dict[str, str]:
    if path.suffix.casefold() == ".jsonl":
        mapping: dict[str, str] = {}
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw_line.strip():
                continue
            item = json.loads(raw_line)
            if not isinstance(item, Mapping):
                raise ValueError(f"JSONL line {line_number} must be an object")
            scenario_id = str(item.get("id", item.get("scenario_id", ""))).strip()
            response = str(item.get("response", ""))
            if not scenario_id:
                raise ValueError(f"JSONL line {line_number} is missing id/scenario_id")
            mapping[scenario_id] = response
        return mapping

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        if "responses" in payload and isinstance(payload["responses"], list):
            payload = payload["responses"]
        else:
            return {str(key): str(value) for key, value in payload.items()}
    if isinstance(payload, list):
        result: dict[str, str] = {}
        for item in payload:
            if not isinstance(item, Mapping):
                raise ValueError("response list items must be objects")
            scenario_id = str(item.get("id", item.get("scenario_id", ""))).strip()
            if not scenario_id:
                raise ValueError("response item is missing id/scenario_id")
            result[scenario_id] = str(item.get("response", ""))
        return result
    raise ValueError("responses file must be an object, list, or JSONL stream")


def run_driver(command: str, scenario: Mapping[str, Any], *, timeout: float) -> str:
    argv = shlex.split(command)
    if not argv:
        raise ValueError("driver command is empty")
    env = os.environ.copy()
    env.update(
        {
            "JASON_SIMULATION_SCENARIO_ID": str(scenario["id"]),
            "JASON_SIMULATION_CATEGORY": str(scenario["category"]),
            "JASON_SIMULATION_QUESTION": str(scenario["question"]),
        }
    )
    completed = subprocess.run(
        argv,
        input=str(scenario["question"]) + "\n",
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"driver exited {completed.returncode}: {detail[:500]}")
    return completed.stdout.strip()


def select_scenarios(
    scenarios: Iterable[dict[str, Any]],
    *,
    scenario_ids: set[str],
    categories: set[str],
    limit: int | None,
) -> tuple[dict[str, Any], ...]:
    selected = [
        item
        for item in scenarios
        if (not scenario_ids or str(item["id"]) in scenario_ids)
        and (not categories or str(item["category"]) in categories)
    ]
    if limit is not None:
        selected = selected[:limit]
    return tuple(selected)


def write_reports(results: tuple[ScenarioResult, ...], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"realistic-user-simulation-{stamp}.json"
    csv_path = output_dir / f"realistic-user-simulation-{stamp}.csv"

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": sum(result.passed for result in results),
        "failed": sum(not result.passed for result in results),
        "results": [asdict(result) for result in results],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("scenario_id", "category", "question", "expected", "response", "passed", "reason"),
        )
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))
    return json_path, csv_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run realistic observe-only Jason user-language regression scenarios.")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--responses", type=Path, help="Captured JSON/JSONL responses keyed by scenario id.")
    parser.add_argument("--driver-command", help="Command invoked once per question; question is passed on stdin.")
    parser.add_argument("--driver-timeout", type=float, default=90.0)
    parser.add_argument("--scenario", action="append", default=[], help="Run one scenario id; repeatable.")
    parser.add_argument("--category", action="append", default=[], help="Run one category; repeatable.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--list", action="store_true", help="List selected scenarios without executing them.")
    parser.add_argument("--validate-scenarios", action="store_true", help="Validate scenario structure and exit.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        scenarios = load_scenarios(args.scenarios)
        selected = select_scenarios(
            scenarios,
            scenario_ids=set(args.scenario),
            categories=set(args.category),
            limit=args.limit,
        )
    except Exception as exc:
        print(f"ERROR: scenario validation failed: {exc}", file=sys.stderr)
        return 2

    if args.validate_scenarios:
        print(f"PASS: validated {len(scenarios)} scenarios from {args.scenarios}")
        return 0

    if not selected:
        print("ERROR: no scenarios matched the requested filters", file=sys.stderr)
        return 2

    if args.list:
        for item in selected:
            print(f"{item['id']}\t{item['category']}\t{item['question']}")
        print(f"TOTAL={len(selected)}")
        return 0

    if bool(args.responses) == bool(args.driver_command):
        print("ERROR: choose exactly one response source: --responses or --driver-command", file=sys.stderr)
        return 2

    response_map: dict[str, str] = {}
    if args.responses:
        try:
            response_map = load_responses(args.responses)
        except Exception as exc:
            print(f"ERROR: could not load responses: {exc}", file=sys.stderr)
            return 2

    results: list[ScenarioResult] = []
    for index, scenario in enumerate(selected, 1):
        scenario_id = str(scenario["id"])
        print(f"[{index}/{len(selected)}] {scenario_id}: {scenario['question']}")
        try:
            if args.driver_command:
                response = run_driver(args.driver_command, scenario, timeout=args.driver_timeout)
            else:
                response = response_map.get(scenario_id, "")
            result = evaluate(scenario, response)
        except Exception as exc:
            result = ScenarioResult(
                scenario_id=scenario_id,
                category=str(scenario["category"]),
                question=str(scenario["question"]),
                expected=expected_description(scenario),
                response="",
                passed=False,
                reason=f"driver/harness error: {exc}",
            )
        results.append(result)
        print(f"  {'PASS' if result.passed else 'FAIL'}: {result.reason}")

    final = tuple(results)
    json_path, csv_path = write_reports(final, args.output_dir)
    passed = sum(item.passed for item in final)
    failed = len(final) - passed
    print("========== SUMMARY ==========")
    print(f"TOTAL={len(final)}")
    print(f"PASSED={passed}")
    print(f"FAILED={failed}")
    print(f"JSON_REPORT={json_path}")
    print(f"CSV_REPORT={csv_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
