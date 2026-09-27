from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Mapping, Sequence

from tools.ccc_checkpoint import LastKnownCompliantPromoter


class CCCRunnerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CheckResult:
    check_id: str
    status: str
    detail: str
    evidence: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CCCConfig:
    enabled: bool
    cadence_days: int
    repository_root: Path
    evidence_root: Path
    recovery_root: Path
    state_root: Path
    openclaw_health_path: Path
    max_openclaw_health_age_seconds: int
    prometheus_url: str
    minimum_healthy_prometheus_targets: int
    ccc_principal_id: str
    organization_id: str
    material_path_prefixes: tuple[str, ...]
    checker_sensitive_prefixes: tuple[str, ...]
    runtime_sensitive_prefixes: tuple[str, ...]
    provider_canaries: tuple[Mapping[str, Any], ...]

    @classmethod
    def load(cls, path: Path) -> "CCCConfig":
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise CCCRunnerError("CCC configuration must be a JSON object")
        cadence = int(value.get("cadence_days", 30))
        if cadence < 1 or cadence > 366:
            raise CCCRunnerError("cadence_days must be between 1 and 366")
        return cls(
            enabled=bool(value.get("enabled", True)),
            cadence_days=cadence,
            repository_root=Path(value.get("repository_root", "/home/al/projects/jason")),
            evidence_root=Path(value.get("evidence_root", "/home/al/Jason-Evidence/CCC")),
            recovery_root=Path(value.get("recovery_root", "/home/al/Jason-Recovery/CCC")),
            state_root=Path(value.get("state_root", "/var/lib/jason/ccc")),
            openclaw_health_path=Path(value.get("openclaw_health_path", "/var/lib/jason/openclaw/operational-health.json")),
            max_openclaw_health_age_seconds=int(value.get("max_openclaw_health_age_seconds", 900)),
            prometheus_url=str(value.get("prometheus_url", "http://127.0.0.1:9090/api/v1/targets")),
            minimum_healthy_prometheus_targets=int(value.get("minimum_healthy_prometheus_targets", 11)),
            ccc_principal_id=str(value.get("ccc_principal_id", "jason-ccc-worker")),
            organization_id=str(value.get("organization_id", "aot")),
            material_path_prefixes=tuple(str(x) for x in value.get("material_path_prefixes", ())),
            checker_sensitive_prefixes=tuple(str(x) for x in value.get("checker_sensitive_prefixes", ())),
            runtime_sensitive_prefixes=tuple(str(x) for x in value.get("runtime_sensitive_prefixes", ())),
            provider_canaries=tuple(x for x in value.get("provider_canaries", ()) if isinstance(x, dict)),
        )


@dataclass(frozen=True, slots=True)
class CCCRunResult:
    status: str
    trigger: str
    source_revision: str | None
    runtime_revision: str | None
    report_path: Path | None
    checkpoint_id: str | None = None


def _run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update({str(k): str(v) for k, v in env.items()})
    return subprocess.run(
        tuple(str(x) for x in command),
        cwd=None if cwd is None else str(cwd),
        env=merged,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def _git(repo: Path, *args: str, timeout: int = 120) -> str:
    result = _run(("git", *args), cwd=repo, timeout=timeout)
    if result.returncode != 0:
        raise CCCRunnerError(f"git {' '.join(args)} failed: {(result.stdout or '').strip()}")
    return (result.stdout or "").strip()


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


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone aware")
    return parsed.astimezone(timezone.utc)


def _matches(path: str, prefixes: Sequence[str]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


class CCCRunner:
    def __init__(
        self,
        config: CCCConfig,
        *,
        checker_revision: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.checker_revision = checker_revision.strip()
        self.now = now or (lambda: datetime.now(timezone.utc))

    def run(self, *, force: bool = False, trigger: str = "scheduled") -> CCCRunResult:
        if not self.config.enabled and not force:
            return CCCRunResult("DISABLED", trigger, None, None, None)

        source_revision = self._authoritative_source_revision()
        runtime_revision = self._runtime_revision()
        changed_from_lkc = self._changed_from_last_compliant(source_revision)
        material_changes = tuple(path for path in changed_from_lkc if _matches(path, self.config.material_path_prefixes))
        schedule_due = self._schedule_due()
        if not force and not schedule_due and not material_changes:
            return CCCRunResult("NOT_DUE", "not_due", source_revision, runtime_revision, None)

        effective_trigger = trigger
        if material_changes and trigger == "scheduled":
            effective_trigger = "material_change"
        elif schedule_due and trigger == "scheduled":
            effective_trigger = "cadence"

        started = self.now().astimezone(timezone.utc)
        run_id = f"ccc-run-{started.strftime('%Y%m%dT%H%M%SZ')}-{source_revision[:12]}"
        run_dir = self.config.evidence_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        checks: list[CheckResult] = []
        checker_delta = self._changed_paths(self.checker_revision, source_revision)
        checker_sensitive = tuple(path for path in checker_delta if _matches(path, self.config.checker_sensitive_prefixes))
        if checker_sensitive:
            checks.append(CheckResult(
                "checker-currentness",
                "NOT_PROVEN",
                "Installed CCC checker is older than governance-sensitive source changes.",
                {"paths": list(checker_sensitive)},
            ))
        else:
            checks.append(CheckResult("checker-currentness", "PASS", "Installed checker remains valid for current source revision."))

        runtime_delta = self._changed_paths(runtime_revision, source_revision)
        runtime_sensitive = tuple(path for path in runtime_delta if _matches(path, self.config.runtime_sensitive_prefixes))
        if runtime_sensitive:
            checks.append(CheckResult(
                "runtime-source-alignment",
                "NOT_PROVEN",
                "Authoritative source contains runtime-sensitive changes not present in live runtime.",
                {"paths": list(runtime_sensitive)},
            ))
        else:
            checks.append(CheckResult(
                "runtime-source-alignment",
                "PASS",
                "Source/runtime differences do not include configured runtime-sensitive paths.",
                {"changed_paths": list(runtime_delta)},
            ))

        if material_changes:
            review = self._material_review(source_revision)
            if review is None:
                checks.append(CheckResult(
                    "material-change-owner-review",
                    "NOT_PROVEN",
                    "Material change requires an exact owner review record for this source revision.",
                    {"paths": list(material_changes)},
                ))
            else:
                checks.append(CheckResult(
                    "material-change-owner-review",
                    "PASS",
                    "Exact source revision has a durable material-change owner review.",
                    review,
                ))

        worktree: Path | None = None
        try:
            worktree = self._temporary_worktree(source_revision)
            checks.extend(self._source_checks(worktree, run_dir))
            checks.extend(self._host_checks(runtime_revision))
            checks.append(self._provider_canary_check())
        except Exception as exc:
            checks.append(CheckResult(
                "runner-exception",
                "NOT_PROVEN",
                f"{type(exc).__name__}: {str(exc)[:800]}",
            ))
        finally:
            if worktree is not None:
                self._remove_worktree(worktree)

        final_status = self._overall_status(checks)
        finished = self.now().astimezone(timezone.utc)
        report = {
            "schema_version": "1.0",
            "status": final_status,
            "run_id": run_id,
            "trigger": effective_trigger,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "source_revision": source_revision,
            "runtime_revision": runtime_revision,
            "checker_revision": self.checker_revision,
            "cadence_days": self.config.cadence_days,
            "material_changes": list(material_changes),
            "checks": [
                {
                    "check_id": c.check_id,
                    "status": c.status,
                    "detail": c.detail,
                    **({"evidence": dict(c.evidence)} if c.evidence is not None else {}),
                }
                for c in checks
            ],
        }
        report_path = run_dir / "ccc-report.json"
        _atomic_json(report_path, report)
        runtime_manifest_path = run_dir / "runtime-manifest.json"
        _atomic_json(runtime_manifest_path, self._runtime_manifest(runtime_revision))
        _atomic_json(self.config.state_root / "latest.json", report)

        checkpoint_id = None
        if final_status == "PASS":
            worktree = self._temporary_worktree(source_revision)
            try:
                promoter = LastKnownCompliantPromoter(
                    worktree,
                    self.config.recovery_root,
                    self.config.evidence_root,
                )
                promoted = promoter.promote(report_path, runtime_manifest_path)
                checkpoint_id = promoted.checkpoint_id
            finally:
                self._remove_worktree(worktree)

        return CCCRunResult(
            final_status,
            effective_trigger,
            source_revision,
            runtime_revision,
            report_path,
            checkpoint_id,
        )

    def _authoritative_source_revision(self) -> str:
        repo = self.config.repository_root
        fetched = _run(("git", "fetch", "origin", "main"), cwd=repo, timeout=120)
        if fetched.returncode != 0:
            raise CCCRunnerError("Unable to refresh authoritative origin/main")
        return _git(repo, "rev-parse", "origin/main")

    def _runtime_revision(self) -> str:
        result = _run((
            "docker", "inspect", "jason-mcp-pilot", "--format",
            '{{index .Config.Labels "com.teamaot.jason.source_revision"}}',
        ), timeout=30)
        value = (result.stdout or "").strip()
        if result.returncode != 0 or len(value) != 40:
            raise CCCRunnerError("Unable to determine live MCP source revision")
        return value

    def _last_compliant(self) -> Mapping[str, Any] | None:
        path = self.config.evidence_root / "last-known-compliant.json"
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None

    def _schedule_due(self) -> bool:
        pointer = self._last_compliant()
        if pointer is None:
            return True
        promoted_at = str(pointer.get("promoted_at", ""))
        try:
            age = self.now().astimezone(timezone.utc) - _parse_time(promoted_at)
        except Exception:
            return True
        return age.total_seconds() >= self.config.cadence_days * 86400

    def _changed_from_last_compliant(self, source_revision: str) -> tuple[str, ...]:
        pointer = self._last_compliant()
        if pointer is None:
            return ()
        previous = str(pointer.get("source_revision", "")).strip()
        if len(previous) != 40 or previous == source_revision:
            return ()
        return self._changed_paths(previous, source_revision)

    def _changed_paths(self, older: str, newer: str) -> tuple[str, ...]:
        if older == newer:
            return ()
        output = _git(self.config.repository_root, "diff", "--name-only", f"{older}..{newer}")
        return tuple(line.strip() for line in output.splitlines() if line.strip())

    def _material_review(self, source_revision: str) -> Mapping[str, Any] | None:
        path = self.config.state_root / "material-review.json"
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return None
        if value.get("source_revision") != source_revision or value.get("status") != "approved":
            return None
        return value

    def _temporary_worktree(self, source_revision: str) -> Path:
        root = Path(tempfile.mkdtemp(prefix="jason-ccc-worktree-"))
        shutil.rmtree(root)
        added = _run(("git", "worktree", "add", "--detach", str(root), source_revision), cwd=self.config.repository_root, timeout=120)
        if added.returncode != 0:
            raise CCCRunnerError(f"Unable to create CCC worktree: {(added.stdout or '').strip()}")
        exclude = Path(_git(root, "rev-parse", "--git-path", "info/exclude"))
        if not exclude.is_absolute():
            exclude = root / exclude
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as handle:
            for name in (".venv-test", ".venv-docs"):
                source = self.config.repository_root / name
                target = root / name
                if source.is_dir() and not target.exists():
                    target.symlink_to(source, target_is_directory=True)
                    handle.write(f"/{name}\n")
        return root

    def _remove_worktree(self, worktree: Path) -> None:
        _run(("git", "worktree", "remove", "--force", str(worktree)), cwd=self.config.repository_root, timeout=120)
        shutil.rmtree(worktree, ignore_errors=True)

    def _source_checks(self, worktree: Path, run_dir: Path) -> list[CheckResult]:
        results: list[CheckResult] = []
        cert = (worktree / "docs/governance/CONSTITUTIONAL-CERTIFICATION-2026-09-26.md").read_text(encoding="utf-8")
        proven_rows = [line for line in cert.splitlines() if line.startswith("| ") and "| PROVEN |" in line or line.startswith("| XIX") and "PROVEN" in line]
        article_rows = [line for line in cert.splitlines() if line.startswith("| ") and any(line.startswith(f"| {roman} ") for roman in ("I","II","III","IV","V","VI","VII","VIII","IX","X","XI","XII","XIII","XIV","XV","XVI","XVII","XVIII","XIX"))]
        matrix_ok = len(article_rows) == 19 and all("PROVEN" in row for row in article_rows) and "100% CONSTITUTIONALLY CERTIFIED AGAINST J-002" in cert
        results.append(CheckResult(
            "j002-article-matrix",
            "PASS" if matrix_ok else "FAIL",
            f"Constitutional matrix has {len(article_rows)} article rows; all must be PROVEN and final certification decision present.",
        ))

        python = worktree / ".venv-test/bin/python"
        py = str(python if python.is_file() else Path("/usr/bin/python3"))
        registry = _run((py, "tools/system_registry_verify.py", "--validate-only"), cwd=worktree, env={"PYTHONPATH":"implementation"}, timeout=180)
        registry_ok = registry.returncode == 0 and '"status": "valid"' in (registry.stdout or "")
        results.append(CheckResult("system-registry", "PASS" if registry_ok else "FAIL", (registry.stdout or "")[-1200:]))

        release = _run((py, "tools/validate_release.py"), cwd=worktree, timeout=1800)
        results.append(CheckResult("j900-release-validation", "PASS" if release.returncode == 0 else "FAIL", (release.stdout or "")[-1500:]))

        mcp_evidence = run_dir / "mcp-constitutional.json"
        mcp = _run(("bash", "tools/run_mcp_constitutional_certification.sh"), cwd=worktree, env={"JASON_MCP_CERT_EVIDENCE_PATH": str(mcp_evidence)}, timeout=1800)
        mcp_ok = mcp.returncode == 0 and "MCP_CONSTITUTIONAL_CERTIFICATION=PASS" in (mcp.stdout or "")
        results.append(CheckResult("mcp-constitutional-production-equivalent", "PASS" if mcp_ok else "FAIL", (mcp.stdout or "")[-1500:]))
        return results

    def _host_checks(self, runtime_revision: str) -> list[CheckResult]:
        results: list[CheckResult] = []
        failed = _run(("systemctl", "--failed", "--no-legend"), timeout=30)
        lines = [line for line in (failed.stdout or "").splitlines() if line.strip()]
        external_failed = [line for line in lines if "jason-ccc.service" not in line]
        results.append(CheckResult(
            "systemd-failed-units",
            "PASS" if failed.returncode == 0 and not external_failed else "FAIL",
            f"external_failed_units={len(external_failed)},self_failed_present={any('jason-ccc.service' in line for line in lines)}",
            {"failed_units": external_failed},
        ))

        prom = _run(("curl", "-fsS", self.config.prometheus_url), timeout=30)
        try:
            targets = json.loads(prom.stdout or "{}").get("data", {}).get("activeTargets", [])
            healthy = sum(1 for item in targets if item.get("health") == "up")
            prom_ok = prom.returncode == 0 and healthy >= self.config.minimum_healthy_prometheus_targets and healthy == len(targets)
        except Exception:
            healthy, targets, prom_ok = 0, [], False
        results.append(CheckResult("prometheus-targets", "PASS" if prom_ok else "FAIL", f"healthy={healthy},total={len(targets)}"))

        health_path = self.config.openclaw_health_path
        try:
            health = json.loads(health_path.read_text(encoding="utf-8"))
            age = self.now().astimezone(timezone.utc).timestamp() - health_path.stat().st_mtime
            health_ok = health.get("status") == "pass" and age <= self.config.max_openclaw_health_age_seconds
            detail = f"status={health.get('status')},age_seconds={int(age)}"
        except Exception as exc:
            health_ok, detail = False, f"{type(exc).__name__}: {exc}"
        results.append(CheckResult("openclaw-authority-health", "PASS" if health_ok else "FAIL", detail))

        current = Path("/opt/jason/current")
        try:
            current_target = current.resolve()
            release_ok = current_target.name == runtime_revision
            detail = str(current_target)
        except Exception as exc:
            release_ok, detail = False, str(exc)
        results.append(CheckResult("immutable-runtime-release", "PASS" if release_ok else "FAIL", detail))

        status_script = "import json,jason_mcp.server as s; print(json.dumps(s.jason_mcp_status(),sort_keys=True))"
        mcp = _run(("docker", "exec", "jason-mcp-pilot", "python", "-c", status_script), timeout=60)
        try:
            value = json.loads((mcp.stdout or "").splitlines()[-1])
            mcp_ok = value.get("status") == "ok" and value.get("governed_execution") == "central-orchestrator" and value.get("direct_provider_access") is False
            detail = json.dumps({k:value.get(k) for k in ("status","mode","governed_execution","direct_provider_access")}, sort_keys=True)
        except Exception as exc:
            mcp_ok, detail = False, str(exc)
        results.append(CheckResult("mcp-governance-boundary", "PASS" if mcp_ok else "FAIL", detail))
        return results

    def _provider_canary_check(self) -> CheckResult:
        payload = json.dumps(list(self.config.provider_canaries), separators=(",", ":"))
        script = r'''
import json,sys
from jason_runtime.composition import RuntimeSettings, build_runtime_application
from autonomous_remediation.autonomous_principal import AutonomousPrincipal, AutonomousRequestFactory
from jason_runtime.autonomy_shadow_runtime import GovernedAutonomyReadPort
canaries=json.loads(sys.argv[1]); principal_id=sys.argv[2]; organization_id=sys.argv[3]
app=build_runtime_application(RuntimeSettings.from_env())
factory=AutonomousRequestFactory(principal=AutonomousPrincipal(principal_id=principal_id,organization_id=organization_id),authority=app.identity_authority,capabilities=app.capabilities,approvals=None,execution_ledger=None,promotion_store=None)
port=GovernedAutonomyReadPort(request_factory=factory,orchestrator=app.governed_orchestrator,policy_id='ccc-provider-canary-v1')
out=[]
for item in canaries:
    try:
        result=port.execute(item['capability'],item.get('arguments',{}))
        out.append({'name':item['name'],'capability':item['capability'],'status':result.get('status'),'stage':result.get('stage'),'provider':result.get('provider'),'error_code':result.get('error_code'),'reason_codes':result.get('reason_codes',[]),'correlation_id':result.get('correlation_id')})
    except Exception as exc:
        out.append({'name':item.get('name','unknown'),'capability':item.get('capability'),'status':'exception','error_type':type(exc).__name__,'error':str(exc)[:500]})
print(json.dumps(out,sort_keys=True))
'''
        result = _run(("docker", "exec", "jason-runtime", "python", "-c", script, payload, self.config.ccc_principal_id, self.config.organization_id), timeout=300)
        try:
            values = json.loads((result.stdout or "").splitlines()[-1])
        except Exception:
            return CheckResult("governed-provider-canaries", "NOT_PROVEN", f"Unable to parse canary output: {(result.stdout or '')[-800:]}")
        failures = []
        summary = []
        expected_by_name = {str(item.get("name")): item for item in self.config.provider_canaries}
        for value in values:
            expected = expected_by_name.get(str(value.get("name")), {})
            expected_status = str(expected.get("expected_status", "succeeded"))
            expected_provider_present = "expected_provider" in expected
            expected_provider = expected.get("expected_provider")
            expected_error_present = "expected_error_code" in expected
            expected_error = expected.get("expected_error_code")
            expected_reasons = tuple(str(x) for x in expected.get("expected_reason_codes_contains", ()))
            actual_reasons = tuple(str(x) for x in value.get("reason_codes", ()))
            matches = value.get("status") == expected_status
            if expected_provider_present:
                matches = matches and value.get("provider") == expected_provider
            if expected_error_present:
                matches = matches and value.get("error_code") == expected_error
            if expected_reasons:
                matches = matches and all(reason in actual_reasons for reason in expected_reasons)
            record = {
                "name": value.get("name"),
                "status": value.get("status"),
                "provider": value.get("provider"),
                "error_code": value.get("error_code"),
                "reason_codes": list(actual_reasons),
                "correlation_id": value.get("correlation_id"),
                "expected_status": expected_status,
            }
            summary.append(record)
            if not matches:
                failures.append({**record, "expected": dict(expected)})
        if not failures and len(values) == len(self.config.provider_canaries):
            return CheckResult(
                "governed-provider-boundary-canaries",
                "PASS",
                f"{len(values)} governed provider boundary canaries matched expected positive/negative outcomes.",
                {"results": summary},
            )
        encoded = json.dumps(failures, sort_keys=True)
        status = "NOT_PROVEN" if "NO_MATCHING_AUTHORITY_GRANT" in encoded else "FAIL"
        return CheckResult(
            "governed-provider-boundary-canaries",
            status,
            f"{len(failures)} canaries did not match their expected governed outcomes.",
            {"failures": failures, "results": summary},
        )

    def _runtime_manifest(self, runtime_revision: str) -> Mapping[str, Any]:
        return {
            "schema_version": "1.0",
            "runtime_revision": runtime_revision,
            "immutable_release_path": str(Path("/opt/jason/current").resolve()),
            "mcp_mode": "governed-read-plus-actions",
            "governed_execution": "central-orchestrator",
            "direct_provider_access": False,
        }

    @staticmethod
    def _overall_status(checks: Sequence[CheckResult]) -> str:
        statuses = {item.status for item in checks}
        if "FAIL" in statuses:
            return "FAIL"
        if "NOT_PROVEN" in statuses:
            return "NOT_PROVEN"
        return "PASS"
