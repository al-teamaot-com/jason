#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_JSON = Path("docs/control/AUTOMATED-CHANGE-STATE.json")
DEFAULT_MD = Path("docs/control/AUTOMATED-CHANGE-STATE.md")
HOST_UNITS = (
    "jason-client-posture-exporter.service",
    "jason-playbook-exporter.service",
    "jason-production-health-exporter.service",
    "jason-resolution-memory-exporter.service",
    "jason-security-control-exporter.service",
    "jason-status-exporter.service",
    "jason-usage-attribution-exporter.service",
    "jason-usage-exporter.service",
    "jason-delegation-maintenance.timer",
    "jason-openclaw-authority-health.timer",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run(*args: str) -> str:
    result = subprocess.run(args, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION}
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("unsupported automated documentation state schema")
    return state


def update_source(state: dict[str, Any], *, revision: str, run_id: str, run_url: str) -> None:
    state["validated_source"] = {
        "revision": revision,
        "status": "ci_passed",
        "workflow": "Validate Jason",
        "workflow_run_id": run_id,
        "workflow_url": run_url,
        "observed_at": now_iso(),
    }


def docker_field(container: str, template: str) -> str:
    return run("docker", "inspect", container, "--format", template)


def collect_production(revision: str) -> dict[str, Any]:
    runtime_revision = docker_field(
        "jason-runtime", '{{index .Config.Labels "com.teamaot.jason.source_revision"}}'
    )
    runtime_health = docker_field(
        "jason-runtime", "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}"
    )
    runtime_restarts = docker_field("jason-runtime", "{{.RestartCount}}")
    mcp_revision = docker_field(
        "jason-mcp-pilot", '{{index .Config.Labels "com.teamaot.jason.source_revision"}}'
    )
    mcp_state = docker_field("jason-mcp-pilot", "{{.State.Status}}")
    mcp_restart_policy = docker_field("jason-mcp-pilot", "{{.HostConfig.RestartPolicy.Name}}")
    current_release = str(Path("/opt/jason/current").resolve())

    if runtime_revision != revision or runtime_health != "healthy":
        raise RuntimeError("runtime is not healthy on requested revision")
    if mcp_revision != revision or mcp_state != "running":
        raise RuntimeError("MCP is not running on requested revision")
    if Path(current_release).name != revision:
        raise RuntimeError("/opt/jason/current is not aligned to requested revision")

    units: dict[str, str] = {}
    for unit in HOST_UNITS:
        state = run("systemctl", "is-active", unit)
        if state != "active":
            raise RuntimeError(f"required host unit is not active: {unit}={state}")
        units[unit] = state
    failed = run("systemctl", "--failed", "--no-legend", "--plain")
    if failed.strip():
        raise RuntimeError("failed systemd units are present after production reconciliation")

    return {
        "revision": revision,
        "status": "aligned_and_healthy",
        "observed_at": now_iso(),
        "runtime": {
            "source_revision": runtime_revision,
            "health": runtime_health,
            "restart_count": int(runtime_restarts),
        },
        "mcp": {
            "source_revision": mcp_revision,
            "state": mcp_state,
            "restart_policy": mcp_restart_policy,
        },
        "host_release": current_release,
        "host_units": units,
        "failed_systemd_units": 0,
    }


def render_markdown(state: dict[str, Any]) -> str:
    source = state.get("validated_source") or {}
    production = state.get("production") or {}
    lines = [
        "# Automated Change State",
        "",
        "**Status:** Generated; do not hand-edit",
        "**Authority:** Derived evidence only; this file does not grant authority or replace governing architecture or runbooks.",
        "**Canonical structured source:** `docs/control/AUTOMATED-CHANGE-STATE.json`",
        "",
        "This record is updated by Jason's post-success documentation reconciliation process. It deliberately separates validated source from production-deployed state.",
        "",
        "## Latest validated source",
        "",
    ]
    if source:
        lines.extend(
            [
                f"- Revision: `{source.get('revision', '')}`",
                f"- Status: `{source.get('status', '')}`",
                f"- Workflow: `{source.get('workflow', '')}`",
                f"- Workflow run: `{source.get('workflow_run_id', '')}`",
                f"- Observed: `{source.get('observed_at', '')}`",
            ]
        )
    else:
        lines.append("- No successful source validation has been recorded yet.")
    lines.extend(["", "## Latest production alignment", ""])
    if production:
        runtime = production.get("runtime") or {}
        mcp = production.get("mcp") or {}
        lines.extend(
            [
                f"- Revision: `{production.get('revision', '')}`",
                f"- Status: `{production.get('status', '')}`",
                f"- Runtime: `{runtime.get('health', '')}`; restarts `{runtime.get('restart_count', '')}`",
                f"- MCP: `{mcp.get('state', '')}`; restart policy `{mcp.get('restart_policy', '')}`",
                f"- Host release: `{production.get('host_release', '')}`",
                f"- Required host units active: `{len(production.get('host_units') or {})}`",
                f"- Failed systemd units: `{production.get('failed_systemd_units', '')}`",
                f"- Observed: `{production.get('observed_at', '')}`",
            ]
        )
    else:
        lines.append("- No production alignment has been recorded by this automation yet.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A validated source revision is not proof of production deployment. Production is recorded only after the runtime, MCP, immutable host release, and required host services independently match the requested revision and are healthy.",
            "",
        ]
    )
    return "\n".join(lines)


def write_state(json_path: Path, markdown_path: Path, state: dict[str, Any]) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    state["schema_version"] = SCHEMA_VERSION
    json_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(state), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("source", "production"))
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--workflow-run-id", default="")
    parser.add_argument("--workflow-url", default="")
    parser.add_argument("--state-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--state-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    state = load_state(args.state_json)
    if args.mode == "source":
        if not args.workflow_run_id or not args.workflow_url:
            raise SystemExit("source mode requires workflow run id and url")
        update_source(
            state,
            revision=args.source_revision,
            run_id=args.workflow_run_id,
            run_url=args.workflow_url,
        )
    else:
        state["production"] = collect_production(args.source_revision)
    write_state(args.state_json, args.state_md, state)
    print(f"DOCUMENTATION_SUCCESS_RECONCILIATION=PASS mode={args.mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
