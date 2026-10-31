from __future__ import annotations

import os
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from .config import ComponentConfig, PMV2Config
from .store import PMV2Store
from .resources import wrap_subprocess_command


@dataclass(frozen=True, slots=True)
class ComponentResult:
    component: str
    return_code: int
    state: str


class ComponentRunner:
    """Run independent reusable maintenance components without serial chaining."""

    def __init__(self, *, config: PMV2Config, store: PMV2Store, repo: Path):
        self.config = config
        self.store = store
        self.repo = repo
        self.pool = ThreadPoolExecutor(
            max_workers=config.max_concurrent_components,
            thread_name_prefix="pm-v2-component",
        )
        self._running: dict[Future[ComponentResult], ComponentConfig] = {}
        self._lock = Lock()
        for component in config.components:
            store.register_component(
                component=component.name,
                owner=component.owner,
            )

    @staticmethod
    def _iso_after(seconds: int) -> str:
        return (
            datetime.now(timezone.utc) + timedelta(seconds=seconds)
        ).isoformat(timespec="seconds")

    def dispatch_due(self) -> int:
        count = 0
        with self._lock:
            capacity = self.config.max_concurrent_components - len(self._running)
            if capacity <= 0:
                return 0
            for component in self.config.components:
                if capacity <= 0:
                    break
                if component.owner != "pm_v2":
                    continue
                if any(cfg.name == component.name for cfg in self._running.values()):
                    continue
                lease = component.timeout_seconds + 30
                if not self.store.claim_due_component(
                    component=component.name,
                    instance_id=self.config.instance_id,
                    lease_seconds=lease,
                ):
                    continue
                future = self.pool.submit(self._run, component)
                self._running[future] = component
                capacity -= 1
                count += 1
        return count

    def reap(self) -> list[ComponentResult]:
        results: list[ComponentResult] = []
        with self._lock:
            done = [future for future in self._running if future.done()]
            for future in done:
                component = self._running.pop(future)
                try:
                    result = future.result()
                except Exception:
                    # Executor failures are bounded like process failures.
                    result = self._persist_failure(component, 126)
                results.append(result)
        return results

    def _persist_failure(self, component: ComponentConfig, code: int) -> ComponentResult:
        snapshot = {
            row["component"]: row for row in self.store.component_snapshot()
        }.get(component.name, {})
        failures = int(snapshot.get("consecutive_failures") or 0) + 1
        if failures >= component.max_attempts:
            state = "blocked_recheck"
            delay = component.blocked_recheck_seconds
        else:
            state = "retry_wait"
            delay = component.retry_delay_seconds
        self.store.finish_component(
            component=component.name,
            return_code=code,
            next_due_at=self._iso_after(delay),
            state=state,
            consecutive_failures=failures,
        )
        self.store.record_health(
            component="periodic:" + component.name,
            instance_id=self.config.instance_id,
            status="degraded",
            details={
                "owner": "pm_v2",
                "return_code": code,
                "state": state,
                "consecutive_failures": failures,
                "next_recheck_seconds": delay,
            },
        )
        return ComponentResult(component.name, code, state)

    def _run(self, component: ComponentConfig) -> ComponentResult:
        values = {
            "repo": str(self.repo),
            "legacy_spool": str(self.config.legacy_spool),
            "release_state": str(self.config.release_state),
        }
        command = [part.format(**values) for part in component.command]
        command = wrap_subprocess_command(self.config, command)
        try:
            result = subprocess.run(
                command,
                cwd=str(self.repo),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=component.timeout_seconds,
                check=False,
                env={**os.environ, "JASON_PM_V2_COMPONENT": component.name},
            )
            code = int(result.returncode)
        except subprocess.TimeoutExpired:
            code = 124
        except OSError:
            code = 126

        if code != 0:
            return self._persist_failure(component, code)

        self.store.finish_component(
            component=component.name,
            return_code=0,
            next_due_at=self._iso_after(component.interval_seconds),
            state="healthy_wait",
            consecutive_failures=0,
        )
        self.store.record_health(
            component="periodic:" + component.name,
            instance_id=self.config.instance_id,
            status="healthy",
            details={
                "owner": "pm_v2",
                "return_code": 0,
                "next_interval_seconds": component.interval_seconds,
            },
        )
        return ComponentResult(component.name, 0, "healthy_wait")

    def shutdown(self) -> None:
        self.pool.shutdown(wait=True, cancel_futures=False)
