#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping
from urllib import parse, request


PASS = "PASS"
DRIFTED = "DRIFTED"
NOT_PROVEN = "NOT_PROVEN"


@dataclass(frozen=True, slots=True)
class Check:
    check_id: str
    status: str
    detail: str
    evidence: Mapping[str, Any] | None = None


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _http_json(url: str, *, headers: Mapping[str, str] | None = None, timeout: int = 10) -> Any:
    req = request.Request(url, headers=dict(headers or {}))
    with request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def _docker_grafana_auth() -> tuple[str, str]:
    completed = subprocess.run(
        ["docker", "inspect", "jason-grafana", "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError("unable to inspect jason-grafana environment")
    env = {}
    for line in (completed.stdout or "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    user = env.get("GF_SECURITY_ADMIN_USER", "admin")
    password = env.get("GF_SECURITY_ADMIN_PASSWORD", "")
    if not password:
        raise RuntimeError("Grafana admin credential is unavailable")
    return user, password


def _grafana_headers() -> Mapping[str, str]:
    user, password = _docker_grafana_auth()
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _docker_mounts() -> tuple[dict[str, Any], ...]:
    completed = subprocess.run(
        ["docker", "inspect", "jason-grafana", "--format", "{{json .Mounts}}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError("unable to inspect jason-grafana mounts")
    value = json.loads((completed.stdout or "[]").strip())
    return tuple(item for item in value if isinstance(item, dict))


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def overall_status(checks: list[Check]) -> str:
    statuses = {item.status for item in checks}
    if DRIFTED in statuses:
        return DRIFTED
    if NOT_PROVEN in statuses:
        return NOT_PROVEN
    return PASS


def file_checks(release_root: Path, manifest: Mapping[str, Any]) -> list[Check]:
    checks: list[Check] = []
    dashboards = manifest.get("dashboards", [])
    for item in dashboards:
        path = release_root / str(item["path"])
        uid = str(item["uid"])
        if not path.is_file():
            checks.append(Check(f"file:{uid}", DRIFTED, f"dashboard source missing: {path}"))
            continue
        actual_hash = _sha256(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            checks.append(Check(f"file:{uid}", DRIFTED, f"dashboard JSON invalid: {type(exc).__name__}"))
            continue
        matches = (
            actual_hash == item.get("sha256")
            and payload.get("uid") == uid
            and payload.get("title") == item.get("title")
        )
        checks.append(Check(
            f"file:{uid}",
            PASS if matches else DRIFTED,
            "dashboard source hash/identity matches manifest" if matches else "dashboard source hash or identity differs from manifest",
            {"path": str(path), "expected_sha256": item.get("sha256"), "actual_sha256": actual_hash},
        ))
    return checks


def mount_check(release_root: Path) -> Check:
    expected_showcase = (release_root / "infrastructure/showcase").resolve()
    expected = {
        "/etc/grafana/provisioning": (expected_showcase / "grafana/provisioning").resolve(),
        "/var/lib/grafana/dashboards": (expected_showcase / "grafana/dashboards").resolve(),
    }
    try:
        mounts = _docker_mounts()
    except Exception as exc:
        return Check("grafana-mount-source", NOT_PROVEN, f"{type(exc).__name__}: {exc}")
    actual = {str(item.get("Destination")): Path(str(item.get("Source", ""))).resolve() for item in mounts}
    mismatches = {
        destination: {"expected": str(source), "actual": str(actual.get(destination, ""))}
        for destination, source in expected.items()
        if actual.get(destination) != source
    }
    return Check(
        "grafana-mount-source",
        PASS if not mismatches else DRIFTED,
        "Grafana provisioning/dashboard mounts originate from immutable observability release" if not mismatches else "Grafana bind mounts do not match immutable observability release",
        {"mismatches": mismatches},
    )


def grafana_checks(manifest: Mapping[str, Any], grafana_url: str) -> list[Check]:
    checks: list[Check] = []
    try:
        headers = _grafana_headers()
        health = _http_json(f"{grafana_url.rstrip('/')}/api/health", headers=headers)
        health_ok = isinstance(health, dict) and health.get("database") == "ok"
        checks.append(Check("grafana-health", PASS if health_ok else DRIFTED, json.dumps(health, sort_keys=True)))
        datasources = _http_json(f"{grafana_url.rstrip('/')}/api/datasources", headers=headers)
        ds_by_uid = {item.get("uid"): item for item in datasources if isinstance(item, dict)}
        for required in manifest.get("required_datasources", []):
            uid = required.get("uid")
            actual = ds_by_uid.get(uid)
            ok = actual is not None and actual.get("type") == required.get("type")
            checks.append(Check(f"datasource:{uid}", PASS if ok else DRIFTED, "required datasource present" if ok else "required datasource missing or wrong type"))
        for item in manifest.get("dashboards", []):
            uid = str(item["uid"])
            try:
                payload = _http_json(f"{grafana_url.rstrip('/')}/api/dashboards/uid/{parse.quote(uid)}", headers=headers)
                dash = payload.get("dashboard", {}) if isinstance(payload, dict) else {}
                ok = dash.get("uid") == uid and dash.get("title") == item.get("title")
                checks.append(Check(f"grafana-dashboard:{uid}", PASS if ok else DRIFTED, "dashboard provisioned with expected identity" if ok else "dashboard identity mismatch"))
            except Exception as exc:
                checks.append(Check(f"grafana-dashboard:{uid}", DRIFTED, f"dashboard not readable: {type(exc).__name__}: {exc}"))
    except Exception as exc:
        checks.append(Check("grafana-api", NOT_PROVEN, f"{type(exc).__name__}: {exc}"))
    return checks


def metric_checks(manifest: Mapping[str, Any], prometheus_url: str) -> list[Check]:
    checks: list[Check] = []
    for item in manifest.get("required_metrics", []):
        check_id = str(item.get("id") or item.get("query"))
        query = str(item["query"])
        url = f"{prometheus_url.rstrip('/')}/api/v1/query?{parse.urlencode({'query': query})}"
        try:
            payload = _http_json(url)
            result = payload.get("data", {}).get("result", []) if isinstance(payload, dict) else []
            ok = payload.get("status") == "success" and bool(result)
            checks.append(Check(
                f"metric:{check_id}",
                PASS if ok else DRIFTED,
                "required Prometheus dependency is present" if ok else "required Prometheus dependency returned no series",
                {"query": query, "series": len(result)},
            ))
        except Exception as exc:
            checks.append(Check(f"metric:{check_id}", NOT_PROVEN, f"{type(exc).__name__}: {exc}", {"query": query}))
    return checks


def run(args: argparse.Namespace) -> int:
    release_root = args.release_root.resolve()
    manifest_path = args.manifest or release_root / "config/observability/grafana-dashboard-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks: list[Check] = []
    checks.extend(file_checks(release_root, manifest))
    checks.append(mount_check(release_root))
    checks.extend(grafana_checks(manifest, args.grafana_url))
    checks.extend(metric_checks(manifest, args.prometheus_url))
    status = overall_status(checks)
    now = datetime.now(timezone.utc)
    source_revision = release_root.name if len(release_root.name) == 40 else str(manifest.get("source_revision", "unknown"))
    dashboard_checks = [c for c in checks if c.check_id.startswith("grafana-dashboard:")]
    file_dashboard_checks = [c for c in checks if c.check_id.startswith("file:")]
    metric_dependency_checks = [c for c in checks if c.check_id.startswith("metric:")]
    report = {
        "schema_version": "1.0",
        "status": status,
        "checked_at": now.isoformat(),
        "source_revision": source_revision,
        "release_root": str(release_root),
        "summary": {
            "required_dashboards": len(manifest.get("dashboards", [])),
            "grafana_dashboards_pass": sum(c.status == PASS for c in dashboard_checks),
            "source_files_pass": sum(c.status == PASS for c in file_dashboard_checks),
            "metric_dependencies": len(metric_dependency_checks),
            "metric_dependencies_pass": sum(c.status == PASS for c in metric_dependency_checks),
        },
        "checks": [
            {"check_id": c.check_id, "status": c.status, "detail": c.detail, **({"evidence": dict(c.evidence)} if c.evidence is not None else {})}
            for c in checks
        ],
    }
    _atomic_json(args.output, report)
    print(f"GRAFANA_ASSURANCE_STATUS={status}")
    print(f"GRAFANA_ASSURANCE_REPORT={args.output}")
    return 0 if status == PASS else 1 if status == DRIFTED else 2


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Verify immutable Grafana/Prometheus observability configuration and dependencies.")
    p.add_argument("--release-root", type=Path, default=Path("/opt/jason/observability/current"))
    p.add_argument("--manifest", type=Path)
    p.add_argument("--output", type=Path, default=Path("/var/lib/jason/observability/grafana-assurance.json"))
    p.add_argument("--grafana-url", default="http://127.0.0.1:3000")
    p.add_argument("--prometheus-url", default="http://127.0.0.1:9090")
    return p


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
