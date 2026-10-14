#!/usr/bin/env python3
"""Offline, fail-closed evaluation of a separately governed live QBO read.

This evaluator performs NO QuickBooks API calls, OAuth operations or production
changes. Its input must be the result of Jason's governed company-read tool;
live profiles and source alignment are independently checked using bounded
Docker readback. OAuth status comes from Jason's canonical lifecycle tool.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

PRODUCTION_PROFILE = "quickbooks-production-read-v1"
EXPECTED_AOT_NAMES = frozenset({
    "atlantic office machines",
    "atlantic office technologies",
    # Exact DBA form confirmed by the Intuit production connection notice.
    # Do not use substring matching: unrelated similar names must fail closed.
    "atlantic office machines inc dba atlantic office technologies",
})


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
    oauth_status: Mapping[str, object] | None,
    services_aligned: bool = False,
) -> dict[str, object]:
    """Return a minimal decision; never echo full provider response or tokens."""
    checks: dict[str, bool] = {}
    # OAuth status is an independently collected, non-secret status report.
    # An expired access token must be refreshed through the governed connector,
    # not inferred from the mere presence of a refresh token.
    oauth = oauth_status if isinstance(oauth_status, Mapping) else {}
    checks["production_oauth_connected"] = (
        oauth.get("provider") == "quickbooks"
        and oauth.get("environment") == "production"
        and oauth.get("connected") is True
        and oauth.get("realm_bound") is True
        and oauth.get("has_refresh_token") is True
        and oauth.get("pending_authorization") is False
        and oauth.get("secret_values_printed") is False
    )
    checks["services_running_and_source_aligned"] = services_aligned is True
    checks["both_live_profiles_production"] = (
        runtime_profile == PRODUCTION_PROFILE and mcp_profile == PRODUCTION_PROFILE
    )
    checks["governed_read_succeeded"] = (
        read_result.get("status") == "succeeded"
        and read_result.get("stage") == "completed"
        and read_result.get("capability") == "accounting.company.read"
        and read_result.get("provider") == "quickbooks"
        and isinstance(read_result.get("correlation_id"), str)
        and bool(read_result.get("correlation_id").strip())
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
    # AOT trading/legal names can differ, but an explicit conflicting
    # legal name is never silently accepted.
    supplied_names = [name for name in names if name]
    checks["aot_company_identity"] = (
        bool(supplied_names)
        and all(name in EXPECTED_AOT_NAMES for name in supplied_names)
    )
    checks["quickbooks_domain"] = company.get("domain") == "QBO"
    return {
        "status": "pass" if checks and all(checks.values()) else "fail",
        "checks": checks,
        "note": (
            "Local evidence validation only. Independently attest both live "
            "profiles, production OAuth realm binding and governed read provenance."
        ),
    }


# Use literal template clauses that return *only* the allowed read-profile
# classifier. Never print or persist Docker environment variables or secrets.
_DOCKER_ATTESTATION_FORMAT = (
    '{{.Name}}|{{.State.Running}}|'
    '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|'
    '{{index .Config.Labels "com.teamaot.jason.source_revision"}}|'
    '{{range .Config.Env}}'
    '{{if eq . "JASON_QUICKBOOKS_READ_PROFILE=quickbooks-production-read-v1"}}production'
    '{{else if eq . "JASON_QUICKBOOKS_READ_PROFILE=quickbooks-sandbox-read-v1"}}sandbox'
    '{{end}}{{end}}'
)


def inspect_live_services() -> tuple[str, str, bool]:
    """Read exact Runtime/MCP profile and aligned revision; never emit secrets."""
    command = [
        "docker", "inspect", "jason-runtime", "jason-mcp-pilot",
        "--format", _DOCKER_ATTESTATION_FORMAT,
    ]
    try:
        completed = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Read-only live service attestation unavailable") from exc
    if len(completed.stdout.splitlines()) != 2:
        raise ValueError("Expected two live QuickBooks container attestations")
    observed = {}
    for line in completed.stdout.splitlines():
        fields = line.strip().split("|")
        if len(fields) != 5 or fields[0] not in {"/jason-runtime", "/jason-mcp-pilot"}:
            raise ValueError("Malformed live service attestation")
        name, running, health, revision, profile = fields
        if name in observed or not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("Invalid live service identity or source revision")
        if profile not in {"production", "sandbox"}:
            raise ValueError("Unsupported or ambiguous live read profile")
        observed[name] = (running, health, revision, profile)
    if len(observed) != 2:
        raise ValueError("Runtime/MCP attestation incomplete")
    runtime = observed["/jason-runtime"]
    mcp = observed["/jason-mcp-pilot"]
    aligned = (
        runtime[0] == "true" and runtime[1] == "healthy"
        and mcp[0] == "true" and mcp[1] in {"healthy", "none"}
        and runtime[2] == mcp[2]
    )
    profiles = {
        "production": PRODUCTION_PROFILE,
        "sandbox": "quickbooks-sandbox-read-v1",
    }
    return profiles[runtime[3]], profiles[mcp[3]], aligned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", required=True, type=Path)
    parser.add_argument("--oauth-status-json", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.result_json.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        oauth_payload = json.loads(args.oauth_status_json.read_text(encoding="utf-8"))
        if not isinstance(oauth_payload, dict):
            raise ValueError("Expected an OAuth status object")
        runtime_profile, mcp_profile, aligned = inspect_live_services()
        report = assess(
            payload, runtime_profile=runtime_profile,
            mcp_profile=mcp_profile, oauth_status=oauth_payload,
            services_aligned=aligned,
        )
    except (OSError, ValueError, json.JSONDecodeError):
        report = {"status": "fail", "checks": {}, "note": "Invalid or unreadable evidence"}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
