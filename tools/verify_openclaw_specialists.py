#!/usr/bin/env python3
"""Read-only validation of a staged OpenClaw specialist configuration.

No network use, credential ingestion, production service control, or config mutation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

EXPECTED = ("j-compliance", "j-docs", "j-observe", "j-qa", "j-integrations", "j-release")
EXISTING = ("main", "j-man", "j-dev")


def verify(source: Path, state: Path) -> dict:
    problems = []
    manifest = json.loads((source / "config/openclaw-specialists/manifest.json").read_text())
    config_path = state / "openclaw.json"
    config = json.loads(config_path.read_text())
    agents = config.get("agents", {}).get("list", [])
    id_list = [a.get("id") for a in agents]
    ids = set(id_list)
    desired = set(EXPECTED + EXISTING)
    if len(id_list) != len(ids) or ids != desired:
        problems.append("agent_inventory_mismatch")
    if config.get("bindings") or config.get("channels") or config.get("gateway") or config.get("auth"):
        problems.append("offline_state_contains_live_routing_or_auth")
    if manifest.get("activation") != "disabled" or manifest.get("api_fallback_allowed") is not False:
        problems.append("manifest_does_not_fail_closed")
    policy = manifest.get("staged_coordinator_policy", {})
    mapped = {a.get("id"): a for a in agents}
    for name, permitted in (("main", ["j-man"]), ("j-man", ["j-dev", *EXPECTED])):
        actual = mapped.get(name, {}).get("subagents", {}).get("allowAgents")
        if actual != permitted:
            problems.append("delegation_mismatch:" + name)
    for name in (*EXPECTED, "j-dev"):
        conf = mapped.get(name, {})
        sub = conf.get("subagents", {})
        if sub.get("allowAgents") != [] or sub.get("requireAgentId") is not True:
            problems.append("worker_permission_mismatch:" + name)
        if conf.get("model") != "openai/gpt-5.6-sol":
            problems.append("model_mismatch:" + name)
    for name in (*EXPECTED, "j-man", "j-dev"):
        workspace = state / "workspaces" / name
        for filename in ("AGENTS.md", "IDENTITY.md"):
            if not (workspace / filename).is_file():
                problems.append("missing_workspace_file:" + name + "/" + filename)
    shared = state / "workspaces/_shared/AGENT-CONTRACT.md"
    if not shared.is_file():
        problems.append("shared_contract_missing")
    if config_path.stat().st_mode & 0o077:
        problems.append("offline_config_permissions_unsafe")
    if any(k in config_path.read_text() for k in ('"accessToken"', '"refreshToken"', '"apiKey"', '"api_key"')):
        problems.append("credential_key_in_offline_config")
    for record in manifest.get("agents", []):
        if record.get("production_write_authority") is not False or record.get("auto_dispatch") is not False or record.get("channel_bindings") != []:
            problems.append("manifest_runtime_activation:" + str(record.get("id")))
    return {
        "status": "PASS" if not problems else "FAIL",
        "staged_agent_count": len(agents),
        "specialists": list(EXPECTED),
        "delegation_validated": not any("delegation" in p or "permission" in p for p in problems),
        "production_activation": False,
        "oauth_execution_verified": False,
        "workboard_resumption_verified": False,
        "problems": problems,
    }


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--offline-state", type=Path, required=True)
    args=p.parse_args()
    try:
        result=verify(args.source.resolve(), args.offline_state.resolve())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result={"status":"FAIL", "problems":[type(exc).__name__ + ": invalid or missing staging configuration"],
                "production_activation": False, "oauth_execution_verified":False,
                "workboard_resumption_verified":False}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
