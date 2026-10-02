from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time
from typing import Callable, Mapping, Protocol


class ProcessHandle(Protocol):
    def start(self) -> None: ...
    def is_alive(self) -> bool: ...
    def terminate(self) -> None: ...
    def join(self, timeout: float | None = None) -> None: ...


def read_worker_heartbeat(path: str | Path) -> Mapping[str, object] | None:
    db_path = Path(path)
    if not db_path.exists():
        return None
    connection = sqlite3.connect(str(db_path), timeout=1.0)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM autonomy_worker_heartbeat WHERE singleton_id=1"
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return None if row is None else dict(row)


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class TicketWorkerSupervisor:
    """Supervise the ticket worker independently from all auxiliary maintenance."""

    def __init__(
        self,
        *,
        process_factory: Callable[[], ProcessHandle],
        heartbeat_reader: Callable[[], Mapping[str, object] | None],
        interval_seconds: int,
        stale_after_seconds: int | None = None,
        startup_grace_seconds: int | None = None,
        restart_window_seconds: int = 600,
        max_restarts_per_window: int = 3,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.process_factory = process_factory
        self.heartbeat_reader = heartbeat_reader
        self.interval_seconds = max(30, int(interval_seconds))
        self.stale_after_seconds = int(
            stale_after_seconds
            if stale_after_seconds is not None
            else max(120, self.interval_seconds * 2)
        )
        self.startup_grace_seconds = int(
            startup_grace_seconds
            if startup_grace_seconds is not None
            else max(120, self.interval_seconds * 2)
        )
        self.restart_window_seconds = max(60, int(restart_window_seconds))
        self.max_restarts_per_window = max(1, int(max_restarts_per_window))
        self.monotonic = monotonic
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.process: ProcessHandle | None = None
        self.process_started_at: float | None = None
        self.restart_times: deque[float] = deque()
        self.last_restart_reason: str | None = None
        self.restart_budget_exhausted = False

    def start(self) -> None:
        if self.process is not None and self.process.is_alive():
            return
        self._spawn("startup")

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is None:
            return
        if process.is_alive():
            process.terminate()
        process.join(timeout=5)

    def poll(self) -> bool:
        """Return True when the worker is healthy enough to remain running."""

        process = self.process
        if process is None:
            return self._restart("missing_process")
        if not process.is_alive():
            return self._restart("process_exit")

        started_at = self.process_started_at
        if started_at is None:
            self.process_started_at = self.monotonic()
            return True
        if self.monotonic() - started_at < self.startup_grace_seconds:
            return True

        heartbeat = self.heartbeat_reader()
        if heartbeat is None:
            return self._restart("heartbeat_missing")

        timestamps = [
            _parse_timestamp(heartbeat.get("last_started_at")),
            _parse_timestamp(heartbeat.get("last_completed_at")),
        ]
        latest = max((item for item in timestamps if item is not None), default=None)
        if latest is None:
            return self._restart("heartbeat_empty")

        age = (self.now().astimezone(timezone.utc) - latest).total_seconds()
        if age > self.stale_after_seconds:
            return self._restart("heartbeat_stale")
        return True

    def health_status(self) -> Mapping[str, object]:
        process = self.process
        if process is None or not process.is_alive():
            return {
                "status": "degraded",
                "ticket_worker": "process_not_alive",
                "last_restart_reason": self.last_restart_reason,
            }
        if self.restart_budget_exhausted:
            return {
                "status": "degraded",
                "ticket_worker": "restart_budget_exhausted",
                "last_restart_reason": self.last_restart_reason,
            }

        started_at = self.process_started_at
        if started_at is not None and (
            self.monotonic() - started_at < self.startup_grace_seconds
        ):
            return {
                "status": "ok",
                "ticket_worker": "starting",
                "last_restart_reason": self.last_restart_reason,
            }

        heartbeat = self.heartbeat_reader()
        if heartbeat is None:
            return {
                "status": "degraded",
                "ticket_worker": "heartbeat_missing",
                "last_restart_reason": self.last_restart_reason,
            }
        timestamps = [
            _parse_timestamp(heartbeat.get("last_started_at")),
            _parse_timestamp(heartbeat.get("last_completed_at")),
        ]
        latest = max((item for item in timestamps if item is not None), default=None)
        if latest is None:
            return {
                "status": "degraded",
                "ticket_worker": "heartbeat_empty",
                "last_restart_reason": self.last_restart_reason,
            }
        age = max(
            0.0,
            (self.now().astimezone(timezone.utc) - latest).total_seconds(),
        )
        if age > self.stale_after_seconds:
            return {
                "status": "degraded",
                "ticket_worker": "heartbeat_stale",
                "heartbeat_age_seconds": int(age),
                "last_restart_reason": self.last_restart_reason,
            }
        return {
            "status": "ok",
            "ticket_worker": "healthy",
            "heartbeat_age_seconds": int(age),
            "last_completed_at": heartbeat.get("last_completed_at"),
            "consecutive_failures": heartbeat.get("consecutive_failures", 0),
            "last_restart_reason": self.last_restart_reason,
        }

    def monitor_forever(self, stop_event, *, poll_seconds: float = 5.0) -> None:
        while not stop_event.wait(max(0.5, float(poll_seconds))):
            self.poll()

    def _restart(self, reason: str) -> bool:
        process = self.process
        if process is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        self.process = None

        now = self.monotonic()
        while self.restart_times and now - self.restart_times[0] > self.restart_window_seconds:
            self.restart_times.popleft()
        if len(self.restart_times) >= self.max_restarts_per_window:
            self.restart_budget_exhausted = True
            self.last_restart_reason = f"restart_budget_exhausted:{reason}"
            return False

        self.restart_times.append(now)
        self.restart_budget_exhausted = False
        self._spawn(reason)
        return True

    def _spawn(self, reason: str) -> None:
        process = self.process_factory()
        process.start()
        self.process = process
        self.process_started_at = self.monotonic()
        self.last_restart_reason = reason
