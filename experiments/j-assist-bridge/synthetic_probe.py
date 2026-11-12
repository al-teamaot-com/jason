"""Test-only J-Assist -> Jason synthetic request/response exercise.

This is a local in-process protocol proof; no HTTP listener, actual Chrome
extension connection, screenshots, Datto data, model calls, or ticket writes.
It intentionally uses the existing SessionGate's revalidated identity and
native Datto authorization for every exchange.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass

from session_gate import Denied, SessionGate

MARKER = "JASSIST_SYNTHETIC_TEST_FRAME_V1"
MAX_REQUEST_BYTES = 2048


@dataclass(frozen=True)
class ProbeResponse:
    session_id: str
    sequence: int
    reply_id: str
    observation: str
    evidence_sha256: str


class SyntheticProbe:
    """A small, fail-closed test contract before introducing sensitive data."""

    def __init__(self, gate: SessionGate):
        self._gate = gate
        self._seen: set[tuple[str, str]] = set()

    def exchange(
        self, *, trusted_context: object, session_id: str, token: str,
        device_uid: str, request: bytes,
    ) -> ProbeResponse:
        if not isinstance(request, bytes) or not 0 < len(request) <= MAX_REQUEST_BYTES:
            raise Denied("invalid synthetic probe request size")
        try:
            decoded = json.loads(request.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Denied("invalid probe JSON") from exc
        if not isinstance(decoded, dict) or set(decoded) != {
            "version", "kind", "marker", "request_id"
        }:
            raise Denied("invalid synthetic probe schema")
        if (type(decoded["version"]) is not int or decoded["version"] != 1
                or decoded["kind"] != "synthetic_probe"
                or decoded["marker"] != MARKER
                or not isinstance(decoded["request_id"], str)
                or not 8 <= len(decoded["request_id"]) <= 96
                or not decoded["request_id"].isascii()
                or not decoded["request_id"].isalnum()):
            raise Denied("probe is not a valid synthetic-only test")
        key = session_id, decoded["request_id"]
        if key in self._seen:
            raise Denied("replayed probe")
        # Recheck trusted identity, grant/provider permission, token, expiry,
        # and exact device. Metadata-only event means NO content intake.
        seq = self._gate.acknowledge_metadata(
            trusted_context=trusted_context, session_id=session_id, token=token,
            device_uid=device_uid, event="heartbeat", bytes_sent=0,
        )
        self._seen.add(key)
        digest = hashlib.sha256(request).hexdigest()
        return ProbeResponse(
            session_id=session_id, sequence=seq,
            reply_id=secrets.token_hex(12),
            observation="Synthetic test acknowledged; no screen was analyzed.",
            evidence_sha256=digest,
        )


def make_probe_request(request_id: str) -> bytes:
    return json.dumps(
        {"version": 1, "kind": "synthetic_probe",
         "marker": MARKER, "request_id": request_id},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
