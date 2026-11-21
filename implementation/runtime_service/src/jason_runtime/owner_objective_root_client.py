"""Typed spool transport to the separately installed objective Root executor."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import time
import secrets

from orchestrator.teams_plan_request_repository import request_material, scope_material


def encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


class ObjectiveRootRequestDenied(PermissionError):
    def __init__(self, reason, execution_state):
        super().__init__("objective Root executor: " + reason)
        self.reason_code = reason
        self.execution_state = execution_state


@dataclass(frozen=True)
class ObjectiveRootClient:
    spool: Path
    timeout_seconds: float = 300
    expected_root_uid: int = 0

    def call(self, operation: str, **payload) -> dict:
        if operation not in {"stage", "deliver", "delivery", "execute", "readback", "status"}:
            raise PermissionError("unregistered objective Root operation")
        message = {"schema_version": "1.0", "operation": operation, **payload}
        if operation in {"readback", "status"}:
            message["observation_id"] = secrets.token_hex(16)
        raw = encoded(message)
        if len(raw) > 196608:
            raise ValueError("objective request exceeds size bound")
        identifier = sha256(raw).hexdigest()
        path = self.spool / "requests" / (identifier + ".json")
        # Stage outside the watched queue, then publish complete immutable
        # request bytes. DirectoryNotEmpty must never observe a partial write.
        staging = self.spool / "staging" / (identifier + "." + secrets.token_hex(16))
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            if os.path.lexists(path):
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as stream:
                    m = os.fstat(stream.fileno())
                    if (not stat.S_ISREG(m.st_mode) or m.st_uid != os.geteuid()
                            or m.st_nlink != 1 or stat.S_IMODE(m.st_mode) != 0o600
                            or stream.read(196609) != raw):
                        raise PermissionError("existing request changed")
            else:
                os.rename(staging, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            try: staging.unlink()
            except FileNotFoundError: pass
        result = self.spool / "results" / (identifier + ".json")
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            try:
                fd = os.open(result, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                time.sleep(0.2)
                continue
            with os.fdopen(fd, "rb") as stream:
                m = os.fstat(stream.fileno())
                if (not stat.S_ISREG(m.st_mode) or m.st_uid != self.expected_root_uid
                        or m.st_nlink != 1 or stat.S_IMODE(m.st_mode) != 0o444
                        or not 0 < m.st_size <= 196608):
                    raise PermissionError("objective result is not an installed Root receipt")
                body = stream.read(196609)
            if len(body) != m.st_size:
                raise PermissionError("objective result changed during read")
            data = json.loads(body)
            if data.get("request_id") != identifier:
                raise PermissionError("objective Root result belongs to another request")
            if data.get("status") != "succeeded" or not isinstance(data.get("result"), dict):
                reason = data.get("reason_code", "UNVERIFIED_ROOT_RESULT")
                if not isinstance(reason, str) or len(reason) > 120 or not all(
                        c.isalnum() or c == "_" for c in reason):
                    reason = "UNVERIFIED_ROOT_RESULT"
                raise ObjectiveRootRequestDenied(reason, data.get("execution_state", "unknown"))
            return data["result"]
        raise TimeoutError("objective execution outcome is unknown; native readback is required")

    def stage(self, *, proposal, requests, pending):
        return self.call("stage", approval_id=proposal.approval_id,
            material={"requests": [request_material(r) for r in requests],
                      "scope": scope_material(proposal.scope)})

    def record_delivery(self, *, approval_id, receipt):
        if receipt.channel != "microsoft_teams":
            raise PermissionError("objective delivery must use the existing Teams transport")
        return self.call("delivery", approval_id=approval_id,
                         provider_message_id=receipt.channel_reference_id)
