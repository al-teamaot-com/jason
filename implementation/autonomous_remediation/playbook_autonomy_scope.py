"""Canonical source-controlled scope for playbook autonomy review/promotion.

The source registry nominates an exact playbook version and capability set.  This
module turns one registry entry into a canonical, fingerprinted scope suitable for
human review.  It creates no authority by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


class PlaybookAutonomyScopeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RegisteredAutonomyScope:
    playbook_id: str
    name: str
    playbook_version: str
    policy_id: str
    allowed_capabilities: tuple[str, ...]
    review_status: str
    source: str
    entry_sha256: str

    def requested_mode(self) -> str:
        return f"promote:{self.playbook_id}@{self.playbook_version}"


def registered_autonomy_scope(
    *, registry_path: str | Path, playbook_id: str
) -> RegisteredAutonomyScope:
    path = Path(registry_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    playbooks = document.get("playbooks")
    if not isinstance(playbooks, list):
        raise PlaybookAutonomyScopeError("PLAYBOOK_REGISTRY_INVALID")

    normalized_id = str(playbook_id or "").strip()
    matches = [
        item
        for item in playbooks
        if isinstance(item, Mapping)
        and str(item.get("id") or "").strip() == normalized_id
    ]
    if len(matches) != 1:
        raise PlaybookAutonomyScopeError("PLAYBOOK_REGISTRY_EXACT_MATCH_REQUIRED")
    entry = matches[0]

    if str(entry.get("lifecycle") or "").strip().casefold() != "production":
        raise PlaybookAutonomyScopeError("PLAYBOOK_NOT_PRODUCTION")
    if entry.get("enabled") is not True:
        raise PlaybookAutonomyScopeError("PLAYBOOK_NOT_ENABLED")

    autonomy = entry.get("autonomy")
    if not isinstance(autonomy, Mapping):
        raise PlaybookAutonomyScopeError("PLAYBOOK_AUTONOMY_METADATA_REQUIRED")
    if str(autonomy.get("activation") or "").strip().casefold() != "autonomous":
        raise PlaybookAutonomyScopeError("PLAYBOOK_AUTONOMY_NOT_ACTIVATED")

    version = str(entry.get("version") or "").strip()
    policy_id = str(autonomy.get("policy_id") or "").strip()
    capabilities = autonomy.get("allowed_capabilities")
    if not version or not policy_id:
        raise PlaybookAutonomyScopeError("PLAYBOOK_AUTONOMY_SCOPE_INCOMPLETE")
    if not isinstance(capabilities, list) or not capabilities:
        raise PlaybookAutonomyScopeError("PLAYBOOK_AUTONOMY_CAPABILITIES_REQUIRED")

    normalized_capabilities = tuple(str(item).strip() for item in capabilities)
    if any(
        not item or any(token in item for token in ("*", "?", "[", "]"))
        for item in normalized_capabilities
    ):
        raise PlaybookAutonomyScopeError("PLAYBOOK_AUTONOMY_EXACT_CAPABILITIES_REQUIRED")
    if len(set(normalized_capabilities)) != len(normalized_capabilities):
        raise PlaybookAutonomyScopeError("PLAYBOOK_AUTONOMY_CAPABILITIES_DUPLICATE")

    canonical_entry = json.dumps(
        entry,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    fingerprint = sha256(canonical_entry).hexdigest()

    return RegisteredAutonomyScope(
        playbook_id=normalized_id,
        name=str(entry.get("name") or normalized_id).strip(),
        playbook_version=version,
        policy_id=policy_id,
        allowed_capabilities=normalized_capabilities,
        review_status=str(entry.get("review_status") or "").strip(),
        source=str(entry.get("source") or "").strip(),
        entry_sha256=fingerprint,
    )
