"""Read-only inventory of existing source-declared ticket mutation workflows.

This module recognizes governed playbook registrations already present in
Jason rather than creating competing handlers. It NEVER determines whether a
playbook has independently been promoted by the owner's durable authority.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

_ID = re.compile(r"[a-z][a-z0-9_-]{1,127}\Z")
_CAP = re.compile(r"service[.]ticket[.][a-z][a-z0-9_.]{1,128}\Z")
_VERSION = re.compile(r"[0-9]{1,4}[.][0-9]{1,4}[.][0-9]{1,4}\Z")
_MAX_PLAYBOOKS = 300
_MAX_CAPABILITIES = 100


def inventory_ticket_workflows(
    registry: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Extract source-declared *potential reuse*, not live authorization.

    Registrations such as #2144 may be lifecycle='production' and enabled
    while the exact scope remains deliberately NOT owner-promoted.
    """
    if not isinstance(registry, Mapping) or registry.get("schema_version") != 2:
        raise ValueError("source registry v2 required")
    books = registry.get("playbooks")
    if not isinstance(books, list) or not 1 <= len(books) <= _MAX_PLAYBOOKS:
        raise ValueError("invalid playbook registry collection")
    scopes: list[dict[str, Any]] = []
    ids: set[str] = set()
    for entry in books:
        if not isinstance(entry, Mapping):
            raise ValueError("invalid playbook registration")
        name = entry.get("id")
        if not isinstance(name, str) or not _ID.fullmatch(name):
            raise ValueError("invalid playbook id")
        if name in ids:
            raise ValueError("duplicate playbook id")
        ids.add(name)
        autonomy = entry.get("autonomy")
        if not isinstance(autonomy, Mapping):
            continue
        capabilities = autonomy.get("allowed_capabilities", [])
        if not isinstance(capabilities, list) or len(capabilities) > _MAX_CAPABILITIES:
            raise ValueError("invalid playbook capability declaration")
        if not all(isinstance(x, str) for x in capabilities):
            raise ValueError("invalid playbook capability name")
        ticket_actions = sorted({x for x in capabilities if _CAP.fullmatch(x)})
        if not ticket_actions:
            continue
        version = entry.get("version")
        source = entry.get("source")
        policy_id = autonomy.get("policy_id")
        if (not isinstance(version, str) or not _VERSION.fullmatch(version)
                or not isinstance(source, str) or not source.startswith(
                    ("docs/playbooks/", "implementation/")
                )
                or ".." in source or len(source) > 255
                or not isinstance(policy_id, str)
                or policy_id != f"playbook-autonomy:{name}"):
            raise ValueError("invalid ticket workflow source identity")
        pilot_ids = autonomy.get("pilot_ticket_ids")
        if pilot_ids is not None and (
            not isinstance(pilot_ids, list)
            or len(pilot_ids) > 50
            or any(type(x) is not int or x < 1 for x in pilot_ids)
            or len(set(pilot_ids)) != len(pilot_ids)
        ):
            raise ValueError("invalid pilot ticket allowlist")
        required = autonomy.get("required_gates", [])
        if not isinstance(required, list) or any(
            not isinstance(x, str) or not x.strip() for x in required
        ):
            raise ValueError("invalid workflow gates")
        scopes.append({
            "playbook_id": name,
            "version": version,
            "source": source,
            "source_lifecycle": entry.get("lifecycle"),
            "source_enabled": entry.get("enabled") is True,
            "source_review_status": str(entry.get("review_status") or "unverified"),
            "ticket_capabilities": ticket_actions,
            "policy_id": policy_id,
            "pilot_ticket_ids": pilot_ids if pilot_ids is not None else [],
            "required_gates": list(required),
            "status": "source_registered_promotion_unverified",
            "live_promotion_verified": False,
        })
    return sorted(scopes, key=lambda item: item["playbook_id"])


def action_reuse_index(workflows: list[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Capability -> existing reviewed owner-scope IDs. Not action routing."""
    index: dict[str, set[str]] = {}
    for row in workflows:
        capabilities = row["ticket_capabilities"]
        playbook_id = row["playbook_id"]
        for name in capabilities:
            if not isinstance(name, str) or not _CAP.fullmatch(name):
                raise ValueError("invalid ticket capability")
            index.setdefault(name, set()).add(playbook_id)
    return {name: sorted(ids) for name, ids in sorted(index.items())}
