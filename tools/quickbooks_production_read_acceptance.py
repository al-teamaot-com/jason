#!/usr/bin/env python3
"""Offline, fail-closed evaluation of a separately governed live QBO read.

This evaluator performs NO QuickBooks API calls, OAuth operations or production
changes. Its input must be the result of Jason's governed company-read tool;
the two profile arguments must be independently checked against live container
configuration. The caller must also verify the production OAuth realm binding.
"""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path

PRODUCTION_PROFILE = "quickbooks-production-read-v1"
EXPECTED_AOT_NAMES = frozenset({
    "atlantic office machines",
    "atlantic office technologies",
})
VALID_STATUS = ("succeeded", "completed")


def _company_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    tokens = normalized.split()
    while tokens and tokens[-1] in {"inc", "incorporated", "llc", "corp", "corporation"}:
        tokens.pop()
    return " ".join(tokens)


def assess(
    read_result: Mapping[str, object],
    *,
    runtime_profile: str,
    mcp_profile: str,
) -> dict[str, object]:
    """Return a minimal decision; never echo full provider response or tokens."""
    checks: dict[str, bool] = {}
    checks["both_live_profiles_production"] = (
        runtime_profile == PRODUCTION_PROFILE and mcp_profile == PRODUCTION_PROFILE
    )
    checks["governed_read_succeeded"] = (
        read_result.get("status") == "succeeded"
        and read_result.get("stage") == "completed"
        and read_result.get("capability") == "accounting.company.read"
        and read_result.get("provider") == "quickbooks"
    )
    evidence = read_result.get("evidence")
    if not isinstance(evidence, Mapping):
        evidence = {}
    checks["read_capability_evidence"] = (
        evidence.get("provider") == "quickbooks"
        and evidence.get("provider_capability") == "quickbooks.company.read"
    )
    data = evidence.get("data")
    if not isinstance(data, Mapping):
        data = {}
    company = data.get("CompanyInfo")
    if not isinstance(company, Mapping):
        company = {}
    names = [
        _company_name(company.get("CompanyName")),
        _company_name(company.get("LegalName")),
    ]
    checks["not_sandbox"] = bool(all(
        not any(word in name.split() for word in ("sandbox", "sample", "demo"))
        for name in names if name
    ))
    checks["aot_company_identity"] = any(name in EXPECTED_AOT_NAMES for name in names)
    checks["quickbooks_domain"] = company.get("domain") == "QBO"
    return {
        "status": "pass" if checks and all(checks.values()) else "fail",
        "checks": checks,
        "note": (
            "Local evidence validation only. Independently attest both live "
            "profiles, production OAuth realm binding and governed read provenance."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", required=True, type=Path)
    parser.add_argument("--runtime-profile", required=True)
    parser.add_argument("--mcp-profile", required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.result_json.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        report = assess(
            payload, runtime_profile=args.runtime_profile, mcp_profile=args.mcp_profile
        )
    except (OSError, ValueError, json.JSONDecodeError):
        report = {"status": "fail", "checks": {}, "note": "Invalid or unreadable evidence"}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
