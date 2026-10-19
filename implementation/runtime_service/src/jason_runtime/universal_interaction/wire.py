"""Portable cross-channel presentation JSON; no user/approver authority claims."""
from __future__ import annotations

from datetime import timezone
from typing import Any

from .contracts import Interaction


def to_wire(spec: Interaction) -> dict[str, Any]:
    result: dict[str, Any] = {
        "contract_version": spec.contract_version,
        "interaction_id": spec.interaction_id,
        "workflow": spec.workflow,
        "correlation_id": spec.correlation_id,
        "organization_id": spec.organization_id,
        "requester_identity_id": spec.requester_identity_id,
        "kind": spec.kind.value,
        "title": spec.title,
        "summary": spec.summary,
        "visual_intent": spec.visual_intent.value,
    }
    if spec.client_id is not None:
        result["client_id"] = spec.client_id
    if spec.facts:
        result["facts"] = [{"label": x.label, "value": x.value} for x in spec.facts]
    if spec.fields:
        result["fields"] = []
        for field in spec.fields:
            data = {
                "key": field.key, "label": field.label, "field_type": field.field_type.value,
                "required": field.required, "max_length": field.max_length,
            }
            if field.options:
                data["options"] = [{"value": x.value, "label": x.label} for x in field.options]
            if field.currency is not None:
                data["currency"] = field.currency
            if field.minimum is not None:
                data["minimum"] = field.minimum
            if field.maximum is not None:
                data["maximum"] = field.maximum
            if field.show_when is not None:
                data["show_when"] = {
                    "depends_on": field.show_when.depends_on,
                    "equals": field.show_when.equals,
                }
            result["fields"].append(data)
    if spec.actions:
        result["actions"] = [
            {"key": a.key, "label": a.label, "intent": a.intent.value}
            for a in spec.actions
        ]
    if spec.approval_id is not None:
        result["approval_id"] = spec.approval_id
    if spec.expires_at is not None:
        result["expires_at"] = spec.expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return result
