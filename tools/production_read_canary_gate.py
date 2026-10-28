"""Live authenticated MCP read acceptance before *new* Autotask profiles close.

A successful HTTP health check, CCC PASS or a mocked unit test is not proof
that a real Microsoft-bound user can use provider records. This requires fresh
post-deployment evidence from successful, normally authorized MCP tools.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import time
from uuid import uuid4

_SHA = re.compile(r"[a-f0-9]{40}\Z")
_NONCE = re.compile(r"[a-f0-9]{32}\Z")
_AOT_HUMAN = re.compile(r"(?:person-al|person-entra-[a-f0-9]{12,64})\Z")
PROFILE_V11 = "itglue-autotask-entra-comprehensive-entity-read-catalog-v11"
PROFILE_V13 = "itglue-autotask-entra-dynamic-schema-read-catalog-v13"
_RELEASE_PROFILES = frozenset({PROFILE_V11, PROFILE_V13})
_DIR = "functional-canary"


class LiveReadAcceptanceError(RuntimeError):
    pass


def _owned_private_json(path: Path) -> dict | None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            meta = os.fstat(fd)
            if (not stat.S_ISREG(meta.st_mode)
                    or meta.st_uid != os.geteuid()
                    or stat.S_IMODE(meta.st_mode) != 0o600
                    or not 0 < meta.st_size <= 4096):
                return None
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                payload = json.load(stream)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def begin_authenticated_read_canary(state_root: Path, *, candidate_sha: str, profile: str,
                                    ttl_seconds: int = 360, now: float | None = None) -> dict:
    if not isinstance(candidate_sha, str) or not _SHA.fullmatch(candidate_sha):
        raise LiveReadAcceptanceError("read canary candidate must be exact SHA")
    if profile not in _RELEASE_PROFILES or not 60 <= ttl_seconds <= 600:
        raise LiveReadAcceptanceError("read canary profile/expiry unsupported")
    root = state_root / _DIR
    root.mkdir(mode=0o700, parents=False, exist_ok=True)
    folder = root.lstat()
    if (not stat.S_ISDIR(folder.st_mode) or folder.st_uid != os.geteuid()
            or stat.S_IMODE(folder.st_mode) != 0o700):
        raise LiveReadAcceptanceError("canary root directory trust boundary changed")
    event_dir = root / "events"
    event_dir.mkdir(mode=0o700, exist_ok=True)
    events = event_dir.lstat()
    if (not stat.S_ISDIR(events.st_mode) or events.st_uid != os.geteuid()
            or stat.S_IMODE(events.st_mode) != 0o700):
        raise LiveReadAcceptanceError("canary event directory trust boundary changed")
    created = time.time() if now is None else now
    nonce = uuid4().hex
    payload = {
        "schema_version": "1.0", "candidate_sha": candidate_sha,
        "profile": profile, "nonce": nonce,
        "issued_at": float(created), "expires_at": float(created + ttl_seconds),
    }
    intent = root / "intent.json"
    previous = _owned_private_json(intent)
    if previous and previous.get("expires_at", 0) > created:
        raise LiveReadAcceptanceError("an earlier pending owner canary is active")
    data = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode()
    tmp = root / ("." + nonce + ".tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, intent)
    return payload


def _proofs(state_root: Path, session: dict) -> list[dict]:
    root = state_root / _DIR / "events"
    nonce = session.get("nonce")
    if not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
        return []
    results = []
    for path in sorted(root.glob(nonce + "-*.json"))[:64]:
        evidence = _owned_private_json(path)
        if not evidence:
            continue
        observed = evidence.get("observed_at")
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            continue
        if not (session["issued_at"] <= observed < session["expires_at"]):
            continue
        if any(evidence.get(k) != session.get(k) for k in
               ("candidate_sha", "profile", "nonce")):
            continue
        identity = evidence.get("principal_id")
        if (evidence.get("schema_version") != "1.0"
                or not isinstance(identity, str)
                or not _AOT_HUMAN.fullmatch(identity)):
            continue
        proof = evidence.get("proof")
        if isinstance(proof, dict):
            # Never mix one person's count with another person's pages.
            # Keep identity inside trusted local verification, not customer
            # output or the final release success response.
            results.append({**proof, "_authenticated_principal": identity})
    return results


def verify_authenticated_read_canary(state_root: Path, session: dict) -> dict | None:
    """Cross-check one real owner ticket count, exact multi-page and exact ID.

    No service-only synthetic health canary can satisfy these records. Metadata
    never contains the ticket title, customer name, note or project details.
    """
    proofs = _proofs(state_root, session)
    for count in (p for p in proofs if p.get("kind") == "ticket_count"):
        total = count.get("total")
        scope = count.get("scope")
        if type(total) is not int or not 1 <= total <= 100 or not isinstance(scope, dict):
            continue
        identity = count.get("_authenticated_principal")
        pages = [p for p in proofs if p.get("kind") == "ticket_page"
                 and p.get("scope") == scope and p.get("_authenticated_principal") == identity]
        for first in (p for p in pages if p.get("after") is None):
            ids = first.get("ids")
            if not isinstance(ids, list) or not ids or len(ids) != min(total, 50):
                continue
            if any(type(i) is not int or i <= 0 for i in ids) or ids != sorted(set(ids)):
                continue
            eligible_seconds = [None] if total <= 50 else [
                p for p in pages if p.get("after") == ids[-1]
            ]
            for second in eligible_seconds:
                second_ids = [] if second is None else second.get("ids")
                if (not isinstance(second_ids, list)
                        or len(ids) + len(second_ids) != total
                        or any(type(i) is not int or i <= ids[-1] for i in second_ids)
                        or second_ids != sorted(set(second_ids))):
                    continue
                reads = [p for p in proofs if p.get("kind") == "ticket_exact_read"
                         and p.get("_authenticated_principal") == identity]
                if not any(p.get("id") in ids for p in reads):
                    continue
                if not any(p.get("kind") == "project_search"
                           and p.get("_authenticated_principal") == identity
                           and type(p.get("items")) is int and p["items"] in (0, 1)
                           for p in proofs):
                    continue
                if (session.get("profile") == PROFILE_V13
                        and not any(
                            p.get("kind") == "dynamic_schema_search"
                            and p.get("_authenticated_principal") == identity
                            and type(p.get("items")) is int and p["items"] in (0, 1)
                            for p in proofs
                        )):
                    # v13's actual feature must be tested by the SAME Entra
                    # requester, not inferred from v11's existing Projects.
                    continue
                return {
                    "status": "PASS",
                    "source_revision": session["candidate_sha"],
                    "identity": "authenticated-aot-human-jason-managed",
                    "ticket_count": total,
                    "ticket_pages": 2 if second_ids else 1,
                    "ticket_page_sum": len(ids) + len(second_ids),
                    "exact_id_readback": True,
                    "generic_project_read": True,
                    **({"dynamic_schema_search": True} if session.get("profile") == PROFILE_V13 else {}),
                    "customer_data_in_receipt": False,
                }
    return None


def require_authenticated_read_canary(state_root: Path, session: dict, *,
                                      max_wait_seconds: int = 240) -> dict:
    if not 0 <= max_wait_seconds <= 600:
        raise LiveReadAcceptanceError("read canary wait bound unsupported")
    deadline = time.monotonic() + max_wait_seconds
    while True:
        result = verify_authenticated_read_canary(state_root, session)
        if result is not None:
            return result
        if time.monotonic() >= deadline or time.time() >= session["expires_at"]:
            raise LiveReadAcceptanceError(
                "real authenticated MCP ticket count, complete pages, exact read, "
                "and Projects query not verified; rollback required"
            )
        time.sleep(0.5)
