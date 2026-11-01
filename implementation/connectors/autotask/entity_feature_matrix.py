"""Fail-closed, read-only Autotask feature coverage matrix from entityInformation.

Each record comes from an externally authorized `service.entity.describe` read.
The matrix does not call Autotask, change authorization, or grant execution.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .operations import AUTOTASK_OPERATIONS

_ENTITY_NAME = re.compile(r"[A-Z][A-Za-z0-9]{1,79}\Z")
_ACTION_SPECS = (
    ("query", "GET", "canQuery", "userAccessForQuery"),
    ("create", "POST", "canCreate", "userAccessForCreate"),
    ("update", "PATCH", "canUpdate", "userAccessForUpdate"),
    ("delete", "DELETE", "canDelete", "userAccessForDelete"),
)
_ACCESS = frozenset({"All", "Restricted", "None"})
_MAX_ENTITIES = 500

# Explicit existing nested provider routes. These are known adapter mappings,
# not invented generic CRUD endpoints or execution authority.
_NESTED_ROUTES = {
    ("TicketNotes", "query"): ("autotask.ticket.notes.list",),
    ("TicketNotes", "create"): ("autotask.ticket.note.create",),
    ("TicketNotes", "update"): ("autotask.ticket.note.update",),
    ("TicketCharges", "create"): ("autotask.ticket.charge.create",),
    ("TicketCharges", "update"): ("autotask.ticket.charge.update",),
    ("TicketAttachments", "query"): ("autotask.ticket.attachments.list",),
    ("TicketAttachments", "create"): ("autotask.ticket.attachment.create",),
}


def _registered_routes(entity: str, action: str, method: str) -> list[str]:
    """Match only known generic route shapes, never infer an API route from flags."""
    suffix = "/query" if action == "query" else ""
    candidate = f"/V1.0/{entity}{suffix}".casefold()
    matches = []
    for name, definition in AUTOTASK_OPERATIONS.items():
        if definition.method != method:
            continue
        template = definition.path_template.casefold()
        # This is *route registration*, not credential or requester permission.
        if template == candidate:
            matches.append(name)
        # The generic {entity} GET compiler is intentionally excluded: its
        # per-entity activation and schema proof are independent and may be off.
    matches.extend(
        name for name in _NESTED_ROUTES.get((entity, action), ())
        if name in AUTOTASK_OPERATIONS
        and AUTOTASK_OPERATIONS[name].method == method
    )
    return sorted(set(matches))


def project_entity_metadata(
    snapshots: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Project supported actions and observed API-user access without executing.

    Expected input:
        [{"entity": "Tickets", "data": {"info": {...}},
          "evidence_ref": "governed-read-correlation-id"}]

    Missing/malformed metadata fails closed rather than defaulting to access.
    The vendor's `info.name` may be singular (Ticket vs Tickets); the
    authenticated entity selector is the route name, not the display name.
    """
    if isinstance(snapshots, (str, bytes)) or not isinstance(snapshots, Sequence):
        raise ValueError("entity snapshots must be a sequence")
    if not 1 <= len(snapshots) <= _MAX_ENTITIES:
        raise ValueError("entity snapshot count outside bounds")
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping):
            raise ValueError("invalid entity snapshot")
        entity = snapshot.get("entity")
        if not isinstance(entity, str) or not _ENTITY_NAME.fullmatch(entity):
            raise ValueError("invalid entity selector")
        if entity in seen:
            raise ValueError("duplicate entity snapshot")
        seen.add(entity)
        evidence_ref = snapshot.get("evidence_ref")
        if not isinstance(evidence_ref, str) or not 1 <= len(evidence_ref) <= 160:
            raise ValueError("governed read evidence reference required")
        envelope = snapshot.get("data")
        if not isinstance(envelope, Mapping):
            raise ValueError("entity metadata envelope missing")
        info = envelope.get("info")
        if not isinstance(info, Mapping):
            raise ValueError("entity metadata info missing")
        display_name = info.get("name")
        if not isinstance(display_name, str) or not _ENTITY_NAME.fullmatch(display_name):
            raise ValueError("entity metadata name invalid")
        for action, method, capability_field, access_field in _ACTION_SPECS:
            supported = info.get(capability_field)
            access = info.get(access_field)
            if type(supported) is not bool or type(access) is not str or access not in _ACCESS:
                raise ValueError(f"incomplete/invalid entity action metadata: {entity}.{action}")
            if not supported:
                status = "unsupported_by_rest"
            elif access == "None":
                status = "api_identity_denied"
            elif access == "Restricted":
                status = "api_identity_restricted"
            else:
                status = "api_identity_all"
            findings.append({
                "entity": entity,
                "action": action,
                "method": method,
                "provider_supported": supported,
                "api_user_access": access,
                "provider_route_names": _registered_routes(entity, action, method),
                "status": status,
                "evidence_ref": evidence_ref,
            })
    return sorted(findings, key=lambda v: (v["entity"], v["action"]))


def diff_entity_metadata(
    previous: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Detect new/removed/changed REST features without promoting capabilities.

    Input is previously generated feature matrices, not unverified UI guesses.
    """
    def indexed(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
        found: dict[tuple[str, str], Mapping[str, Any]] = {}
        if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
            raise ValueError("matrix must be a sequence")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("invalid matrix row")
            entity = row.get("entity")
            action = row.get("action")
            if (not isinstance(entity, str) or not _ENTITY_NAME.fullmatch(entity)
                    or action not in {spec[0] for spec in _ACTION_SPECS}):
                raise ValueError("invalid matrix key")
            key = (entity, action)
            if key in found:
                raise ValueError("duplicate matrix key")
            found[key] = row
        return found

    old, new = indexed(previous), indexed(current)
    changes = []
    for entity, action in sorted(set(old) | set(new)):
        before, after = old.get((entity, action)), new.get((entity, action))
        material_fields = ("provider_supported", "api_user_access", "provider_route_names")
        prior = None if before is None else {key: before.get(key) for key in material_fields}
        latest = None if after is None else {key: after.get(key) for key in material_fields}
        if prior != latest:
            changes.append({
                "entity": entity,
                "action": action,
                "change": "added" if before is None else ("removed" if after is None else "changed"),
                "before": prior,
                "after": latest,
                "status": "candidate_requires_review",
            })
    return changes
