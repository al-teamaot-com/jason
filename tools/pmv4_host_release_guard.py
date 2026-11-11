#!/usr/bin/env python3
"""Independent PMv4 host safety guard and cross-release transaction lock.

Read-only attestation and a *shared* lease gate, not a PMV3 release runner.
During transition the PMv3 transaction inode is locked for the full PMv4
shadow transaction; the new root-owned PMv4 control inode is locked too.
No production host mutation happens when this module is imported.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
from typing import Any, Callable, Iterator, Mapping

CURRENT = Path("/opt/jason/current")
RELEASES = Path("/opt/jason/releases")
OLD_RELEASE_LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
NEW_RELEASE_LOCK = Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock")
LEDGER = Path("/var/lib/jason/openclaw/autonomy-operational-work.sqlite3")
PROTECTED_CONTROL = Path(
    "/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json"
)
PROTECTED_DRIFT = Path(
    "/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json"
)
SHA = re.compile(r"\A[0-9a-f]{40}\Z")


class HostGateDenied(PermissionError):
    pass


class IndependentHostGuard:
    """Trusted host-installed callbacks for a separate PMv4 shadow release.

    Only independently read Docker/image state and the ticket-worker ledger.
    Cannot read production AI/provider credentials, modify provider state,
    or interpret a PMv3 PASS file as independent health evidence.
    """

    def __init__(
        self, *, current: Path = CURRENT, releases: Path = RELEASES,
        ledger: Path = LEDGER,
        old_lock: Path = OLD_RELEASE_LOCK, new_lock: Path = NEW_RELEASE_LOCK,
        control_path: Path = PROTECTED_CONTROL, drift_path: Path = PROTECTED_DRIFT,
        runner: Callable[..., Any] = subprocess.run,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        production: bool = True,
        max_scan_age_seconds: int = 360,
        enforce_protected_control: bool | None = None,
    ):
        if production and (
            Path(current) != CURRENT or Path(releases) != RELEASES
            or Path(ledger) != LEDGER
            or Path(old_lock) != OLD_RELEASE_LOCK or Path(new_lock) != NEW_RELEASE_LOCK
            or Path(control_path) != PROTECTED_CONTROL or Path(drift_path) != PROTECTED_DRIFT
        ):
            raise HostGateDenied("PMV4_TRUSTED_HOST_PATH_OVERRIDE")
        if not 60 <= max_scan_age_seconds <= 900:
            raise HostGateDenied("PMV4_HOST_TICKET_FRESHNESS_INVALID")
        self.current = Path(current)
        self.releases = Path(releases)
        self.ledger = Path(ledger)
        self.old_lock = Path(old_lock)
        self.new_lock = Path(new_lock)
        self.control_path = Path(control_path)
        self.drift_path = Path(drift_path)
        self.runner = runner
        self.now = now
        self.production = production
        if production and enforce_protected_control is False:
            raise HostGateDenied("PMV4_PROTECTED_BREAKER_CANNOT_BE_DISABLED")
        self.enforce_protected_control = (
            production if enforce_protected_control is None
            else bool(enforce_protected_control)
        )
        self.max_scan_age_seconds = max_scan_age_seconds
        self._held = False

    @staticmethod
    def _open_lock(path: Path) -> int:
        # Never create either control file during preflight/observability.
        if path.is_symlink() or not path.is_file():
            raise HostGateDenied("PMV4_HOST_TRANSACTION_LOCK_NOT_PROVISIONED")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
            or meta.st_uid not in (0, os.geteuid())
            or stat.S_IMODE(meta.st_mode) & 0o002):
            os.close(fd)
            raise HostGateDenied("PMV4_HOST_TRANSACTION_LOCK_UNTRUSTED")
        return fd

    @contextmanager
    def host_release_transaction(self) -> Iterator[None]:
        """Hold both PMv3 and PMv4 locks until promotion/rollback finishes.

        The legacy lock is temporary backward-compatible synchronization.
        Remove only after independently proving no legacy publisher can write.
        Fixed acquisition order, nonblocking, always released.
        """
        if self._held:
            raise HostGateDenied("PMV4_NESTED_HOST_TRANSACTION")
        handles: list[int] = []
        try:
            for path in (self.old_lock, self.new_lock):
                fd = self._open_lock(path)
                handles.append(fd)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise HostGateDenied("PMV4_HOST_TRANSACTION_BUSY") from exc
            self._held = True
            yield
        except HostGateDenied:
            raise
        except OSError as exc:
            raise HostGateDenied("PMV4_HOST_TRANSACTION_UNAVAILABLE") from exc
        finally:
            self._held = False
            for fd in reversed(handles):
                os.close(fd)

    def host_mutation_quiescent(self) -> bool:
        """Require both the shared host lease and a CLOSED protected breaker.

        Fresh drift PASS alone is NOT proof that the prior incident breaker
        has been revalidated. Never permit a parallel PMv4 release through
        an open PMv3 protected circuit breaker.
        """
        try:
            if self._held:
                self._assert_protected_release_state()
                return True
            with self.host_release_transaction():
                self._assert_protected_release_state()
                return True
        except (HostGateDenied, OSError, ValueError, TypeError):
            return False

    def _assert_protected_release_state(self) -> None:
        if not self.enforce_protected_control:
            return
        for path in (self.control_path, self.drift_path):
            if path.is_symlink() or not path.is_file():
                raise HostGateDenied("PMV4_PROTECTED_RELEASE_READBACK_MISSING")
        try:
            control = json.loads(self.control_path.read_text(encoding="utf-8"))
            drift = json.loads(self.drift_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError) as exc:
            raise HostGateDenied("PMV4_PROTECTED_RELEASE_READBACK_UNAVAILABLE") from exc
        if not isinstance(control, dict) or not isinstance(drift, dict):
            raise HostGateDenied("PMV4_PROTECTED_RELEASE_READBACK_INVALID")
        source = self._source_sha()
        manifest = (control.get("last_known_good") or {}).get("manifest") or {}
        breaker = control.get("circuit_breaker") or {}
        if (
            manifest.get("revision") != source
            or manifest.get("runtime_revision") != source
            or manifest.get("mcp_revision") != source
            or manifest.get("complete") is not True
        ):
            raise HostGateDenied("PMV4_ROOT_LAST_KNOWN_GOOD_NOT_VERIFIED")
        if (
            breaker.get("state") != "closed"
            or breaker.get("revalidated_revision") != source
        ):
            raise HostGateDenied("PMV4_PROTECTED_PRODUCTION_BREAKER_OPEN")
        if drift.get("status") != "pass" or drift.get("problems") != []:
            raise HostGateDenied("PMV4_PRODUCTION_DRIFT_NOT_CLEAR")
        try:
            observed = datetime.fromisoformat(
                str(drift["observed_at"]).replace("Z", "+00:00")
            )
            now = self.now()
            if observed.tzinfo is None or now.tzinfo is None:
                raise ValueError("timezone")
            age = (now - observed).total_seconds()
            if not 0 <= age <= 120:
                raise ValueError("stale")
        except (KeyError, TypeError, ValueError) as exc:
            raise HostGateDenied("PMV4_PRODUCTION_DRIFT_NOT_FRESH") from exc

    def protected_release_status(self) -> dict[str, Any]:
        """Safe, read-only breaker readiness report without private payload."""
        try:
            self._assert_protected_release_state()
            return {"ready": True, "reason": "verified"}
        except (HostGateDenied, OSError, TypeError, ValueError) as exc:
            return {"ready": False, "reason": str(exc)}

    def _source_sha(self) -> str:
        if not self.current.is_symlink():
            raise HostGateDenied("PMV4_PRODUCTION_SOURCE_POINTER_INVALID")
        destination = self.current.resolve(strict=True)
        if destination.parent != self.releases or not SHA.fullmatch(destination.name):
            raise HostGateDenied("PMV4_PRODUCTION_SOURCE_NOT_PINNED")
        return destination.name

    def _container(self, name: str) -> Mapping[str, Any]:
        if name not in ("jason-runtime", "jason-mcp-pilot"):
            raise HostGateDenied("PMV4_CONTAINER_NOT_ALLOWLISTED")
        proc = self.runner(
            ["/usr/bin/docker", "inspect", name],
            shell=False, capture_output=True, text=True, timeout=15,
            check=False,
        )
        if (proc.returncode != 0 or not isinstance(proc.stdout, str)
            or len(proc.stdout) > 2 * 1024 * 1024):
            raise HostGateDenied("PMV4_DOCKER_INSPECT_UNAVAILABLE")
        try:
            decoded = json.loads(proc.stdout)
        except (ValueError, TypeError) as exc:
            raise HostGateDenied("PMV4_DOCKER_INSPECT_INVALID") from exc
        if not isinstance(decoded, list) or len(decoded) != 1 or not isinstance(decoded[0], dict):
            raise HostGateDenied("PMV4_DOCKER_INSPECT_INVALID")
        return decoded[0]

    def _ticket_scan(self) -> str:
        path = self.ledger
        if path.is_symlink() or not path.is_file():
            raise HostGateDenied("PMV4_TICKET_LEDGER_UNAVAILABLE")
        uri = "file:" + str(path) + "?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True, timeout=2.0)) as connection:
                row = connection.execute(
                    "SELECT last_started_at,last_completed_at,state "
                    "FROM autonomy_ticket_worker_heartbeat WHERE singleton_id=1"
                ).fetchone()
                if row is None or row[2] not in ("completed", "running", "idle"):
                    raise HostGateDenied("PMV4_TICKET_SCAN_HEARTBEAT_MISSING")
                latest = row[1]
                started = row[0]
                if row[2] == "running":
                    # A still-running scan is allowed within its bounded SLA.
                    fresh_start = self._scan_age(started)
                    if fresh_start > self.max_scan_age_seconds:
                        raise HostGateDenied("PMV4_TICKET_SCAN_IN_PROGRESS_STALE")
                completed_age = self._scan_age(latest)
                if completed_age > self.max_scan_age_seconds:
                    raise HostGateDenied("PMV4_TICKET_SCAN_STALE")
                return str(latest)
        except sqlite3.Error as exc:
            raise HostGateDenied("PMV4_TICKET_LEDGER_READ_FAILED") from exc

    def _scan_age(self, value: Any) -> float:
        if not isinstance(value, str) or not value:
            raise HostGateDenied("PMV4_TICKET_TIME_MISSING")
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            now = self.now()
            if stamp.tzinfo is None or now.tzinfo is None:
                raise ValueError("naive")
            age = (now - stamp).total_seconds()
        except (TypeError, ValueError) as exc:
            raise HostGateDenied("PMV4_TICKET_TIME_INVALID") from exc
        if age < -30:
            raise HostGateDenied("PMV4_TICKET_TIME_IN_FUTURE")
        return max(0, age)

    def core_health_evidence(self) -> dict[str, Any]:
        revision = self._source_sha()
        for name in ("jason-runtime", "jason-mcp-pilot"):
            data = self._container(name)
            labels = (data.get("Config") or {}).get("Labels")
            state = data.get("State")
            if (data.get("Name") != "/" + name
                or not isinstance(state, dict) or state.get("Running") is not True
                or not isinstance(labels, dict)
                or labels.get("com.teamaot.jason.source_revision") != revision):
                raise HostGateDenied("PMV4_PROTECTED_CORE_SOURCE_OR_LIVENESS_MISMATCH")
            if name == "jason-runtime":
                health = state.get("Health")
                if not isinstance(health, dict) or health.get("Status") != "healthy":
                    raise HostGateDenied("PMV4_TICKET_CORE_HEALTH_NOT_VERIFIED")
        scan = self._ticket_scan()
        return {
            "status": "verified", "source_sha": revision,
            "ticket_scan_completed_at": scan,
            "runtime_healthy": True, "mcp_running": True,
            "worker_scan_fresh": True,
            "preexisting_core_unchanged_by_probe": True,
        }

    def preexisting_core_health(self) -> bool:
        try:
            return self.core_health_evidence()["status"] == "verified"
        except (HostGateDenied, OSError, ValueError, TypeError):
            return False


if __name__ == "__main__":
    raise SystemExit("Library only: a trusted installer must provision locks and probes.")
