"""Evidence-only witness from genuinely authenticated, successfully released MCP reads.

Never executes a provider read, grants authority or sends customer data. A
pending root-controlled Production Manager transaction enables recording; no
existing or regular MCP request is changed by a missing/invalid intent.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
import stat
import time
from uuid import uuid4

ROOT = Path("/var/lib/jason/openclaw/release-manager/functional-canary")
PROFILE_V11 = "itglue-autotask-entra-comprehensive-entity-read-catalog-v11"
_CAPABILITIES = frozenset({
    "service.ticket.count", "service.ticket.search",
    "service.ticket.read", "service.entity.search",
})
_SHA = re.compile(r"[a-f0-9]{40}\Z")
_NONCE = re.compile(r"[a-f0-9]{32}\Z")
_AOT_HUMAN = re.compile(r"(?:person-al|person-entra-[a-f0-9]{12,64})\Z")
_TIMESTAMP = re.compile(r"[0-9TZ:+.\-]{16,40}\Z")


def _private_json(path: Path, *, max_size: int = 4096) -> dict | None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            meta = os.fstat(fd)
            if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
                    or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_size > max_size):
                return None
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as f:
                data = json.load(f)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _ids(items: object, *, maximum: int) -> list[int] | None:
    if not isinstance(items, list) or len(items) > maximum:
        return None
    ids = [i.get("id") for i in items if isinstance(i, Mapping)]
    if len(ids) != len(items) or any(type(i) is not int or i <= 0 for i in ids):
        return None
    if ids != sorted(set(ids)):
        return None
    return ids


def _scope(arguments: Mapping[str, object]) -> dict | None:
    result = {}
    for key in ("created_after", "created_before"):
        raw = arguments.get(key)
        if not isinstance(raw, str) or not _TIMESTAMP.fullmatch(raw):
            return None
        result[key] = raw
    if result["created_after"] >= result["created_before"]:
        return None
    if set(arguments) - {"created_after", "created_before", "page_size", "after_resource_id"}:
        return None
    return result


def _safe_event(
    capability: str, arguments: Mapping[str, object], result: Mapping[str, object],
) -> dict | None:
    if capability not in _CAPABILITIES or result.get("status") != "succeeded":
        return None
    evidence = result.get("evidence")
    if not isinstance(evidence, Mapping):
        return None
    data = evidence.get("data")
    if not isinstance(data, Mapping):
        return None
    if capability == "service.entity.search":
        if set(arguments) != {"entity", "page_size"} or arguments.get("entity") != "Projects" or arguments.get("page_size") != 1:
            return None
        items = _ids(data.get("items"), maximum=1)
        if items is None:
            return None
        return {"kind": "project_search", "items": len(items)}
    if capability == "service.ticket.read":
        if set(arguments) != {"resource_id"}:
            return None
        # Jason's real service.ticket.read returns one row under data.items,
        # not necessarily data.item. Demand exactly one exact-ID row; a
        # multi-row or wrong-ID answer must never certify exact readback.
        rows = data.get("items")
        if isinstance(rows, list):
            record = rows[0] if len(rows) == 1 else None
        else:
            record = data.get("item")
        requested = arguments.get("resource_id")
        if (not isinstance(record, Mapping) or type(requested) is not int
                or requested <= 0 or record.get("id") != requested):
            return None
        return {"kind": "ticket_exact_read", "id": requested}
    scope = _scope(arguments)
    if scope is None:
        return None
    if capability == "service.ticket.count":
        if set(arguments) != {"created_after", "created_before"}:
            return None
        n = data.get("queryCount")
        if type(n) is not int or not 1 <= n <= 100:
            return None
        return {"kind": "ticket_count", "scope": scope, "total": n}
    if capability == "service.ticket.search":
        page_size = arguments.get("page_size")
        if type(page_size) is not int or page_size != 50:
            return None
        after = arguments.get("after_resource_id")
        if after is not None and (type(after) is not int or after <= 0):
            return None
        ids = _ids(data.get("items"), maximum=50)
        if ids is None or not ids or (after is not None and ids[0] <= after):
            return None
        return {"kind": "ticket_page", "scope": scope, "after": after, "ids": ids}
    return None


def record_authenticated_owner_read(
    *,
    capability: str,
    arguments: Mapping[str, object],
    result: Mapping[str, object],
    principal_id: str,
    organization_id: str,
    client_id: str | None,
    live_profile: str,
    now: float | None = None,
    root: Path = ROOT,
) -> bool:
    """Write metadata ONLY after the ordinary governed read has succeeded.

    The caller must derive the principal from the validated Entra OAuth
    context, never from tool arguments or provider output.
    """
    # The connected MCP authenticates active AOT Entra users as
    # person-entra-<object-id>; the historical person-al release approver
    # is NOT necessarily a live OAuth/Jason binding. Trust only the validated
    # OAuth-derived principal, not a caller-supplied owner alias.
    if (not isinstance(principal_id, str) or not _AOT_HUMAN.fullmatch(principal_id)
            or organization_id != "aot"
            or client_id is not None or live_profile != PROFILE_V11):
        return False
    if not isinstance(arguments, Mapping) or not isinstance(result, Mapping):
        return False
    event = _safe_event(capability, arguments, result)
    if event is None:
        return False
    intent = _private_json(root / "intent.json")
    if not intent or intent.get("schema_version") != "1.0":
        return False
    sha = intent.get("candidate_sha")
    nonce = intent.get("nonce")
    current = time.time() if now is None else now
    if (not isinstance(sha, str) or not _SHA.fullmatch(sha)
            or not isinstance(nonce, str) or not _NONCE.fullmatch(nonce)
            or intent.get("profile") != live_profile
            or type(intent.get("issued_at")) not in (float, int)
            or type(intent.get("expires_at")) not in (float, int)
            or not intent["issued_at"] <= current < intent["expires_at"]):
        return False
    directory = root / "events"
    try:
        meta = directory.lstat()
        if (not stat.S_ISDIR(meta.st_mode) or meta.st_uid != os.geteuid()
                or stat.S_IMODE(meta.st_mode) != 0o700):
            return False
        payload = {
            "schema_version": "1.0", "candidate_sha": sha, "nonce": nonce,
            "profile": live_profile, "principal_id": principal_id,
            "observed_at": current, "capability": capability, "proof": event,
        }
        data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if len(data) > 4096:
            return False
        path = directory / (nonce + "-" + uuid4().hex + ".json")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    except OSError:
        return False
