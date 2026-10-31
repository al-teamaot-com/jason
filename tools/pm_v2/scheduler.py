from __future__ import annotations

import os
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from .config import PMV2Config, WorkerConfig
from .store import Assignment, PMV2Store


@dataclass(frozen=True, slots=True)
class WorkResult:
    assignment_id: str
    worker: str
    return_code: int
    outcome: str


class Scheduler:
    def __init__(self, *, config: PMV2Config, store: PMV2Store, repo: Path):
        self.config = config
        self.store = store
        self.repo = repo
        self.pool = ThreadPoolExecutor(max_workers=config.max_concurrent_jobs, thread_name_prefix="pm-v2")
        self._running: dict[Future[WorkResult], tuple[Assignment, WorkerConfig]] = {}
        self._lock = Lock()

    def _count_worker(self, worker_name: str) -> int:
        return sum(1 for _, worker in self._running.values() if worker.name == worker_name)

    def reap(self) -> list[WorkResult]:
        completed = []
        with self._lock:
            done = [future for future in self._running if future.done()]
            for future in done:
                assignment, worker = self._running.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    self.store.update_state(
                        assignment.assignment_id,
                        state="retry_ready",
                        runnable=True,
                        completion_percent=assignment.completion_percent,
                        reason=f"worker_exception:{type(exc).__name__}",
                    )
                    result = WorkResult(assignment.assignment_id, worker.name, 1, "retry_ready")
                completed.append(result)
        return completed

    def dispatch_available(self) -> int:
        dispatched = 0
        self.store.release_expired_leases()
        with self._lock:
            available_global = self.config.max_concurrent_jobs - len(self._running)
            if available_global <= 0:
                return 0
            for worker in self.config.workers:
                if not worker.enabled:
                    continue
                worker_slots = worker.max_concurrency - self._count_worker(worker.name)
                while available_global > 0 and worker_slots > 0:
                    assignment = self.store.claim_next(
                        instance_id=self.config.instance_id,
                        lease_seconds=self.config.lease_seconds,
                        work_type=worker.name,
                    )
                    if assignment is None:
                        break
                    future = self.pool.submit(self._run, assignment, worker)
                    self._running[future] = (assignment, worker)
                    dispatched += 1
                    available_global -= 1
                    worker_slots -= 1
        return dispatched

    def _run(self, assignment: Assignment, worker: WorkerConfig) -> WorkResult:
        values = {
            "repo": str(self.repo),
            "legacy_spool": str(self.config.legacy_spool),
            "release_state": str(self.config.release_state),
            "assignment_id": assignment.assignment_id,
            "source_ref": assignment.source_ref,
        }
        command = [part.format(**values) for part in worker.command]
        idem_key = f"pmv2:{assignment.assignment_id}:{worker.name}:{assignment.scope_hash}"
        if not self.store.begin_idempotent_action(
            key=idem_key,
            assignment_id=assignment.assignment_id,
            action="worker_dispatch",
        ):
            self.store.update_state(
                assignment.assignment_id,
                state="blocked",
                runnable=False,
                completion_percent=assignment.completion_percent,
                reason="duplicate_dispatch_suppressed",
            )
            return WorkResult(assignment.assignment_id, worker.name, 0, "duplicate_suppressed")

        self.store.event(assignment.assignment_id, "worker_started", {
            "worker": worker.name,
            "command_executable": command[0],
        })
        try:
            result = subprocess.run(
                command,
                cwd=str(self.repo),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(self.config.lease_seconds - 5, 1),
                check=False,
                env={**os.environ, "JASON_PM_V2_ASSIGNMENT_ID": assignment.assignment_id},
            )
            code = int(result.returncode)
        except subprocess.TimeoutExpired:
            code = 124
        except OSError:
            code = 126

        if code == 0:
            state = "validation_ready"
            runnable = False
            percent = max(assignment.completion_percent, 50)
            reason = None
        else:
            state = "retry_ready"
            runnable = True
            percent = assignment.completion_percent
            reason = f"worker_return_code:{code}"

        self.store.finish_idempotent_action(key=idem_key, result={"return_code": code, "state": state})
        self.store.update_state(
            assignment.assignment_id,
            state=state,
            runnable=runnable,
            completion_percent=percent,
            reason=reason,
            payload={"worker": worker.name, "return_code": code},
        )
        return WorkResult(assignment.assignment_id, worker.name, code, state)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=True, cancel_futures=False)
