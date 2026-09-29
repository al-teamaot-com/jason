from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


APPROVED_CLIENT_MESSAGE_REGISTRY_VERSION = 1
DEFAULT_APPROVED_CLIENT_MESSAGE_REGISTRY = (
    Path(__file__).resolve().parents[4]
    / "config"
    / "client_communications"
    / "approved.json"
)


class ApprovedClientMessageRegistryError(RuntimeError):
    """Fail-closed approved client-message registry error."""


@dataclass(frozen=True, slots=True)
class ApprovedClientMessage:
    template_id: str
    workflow_id: str
    title: str
    body: str
    recipient_policy: str
    require_email_notifications: bool

    @property
    def fingerprint(self) -> str:
        material = "|".join(
            (
                self.workflow_id,
                self.template_id,
                self.title,
                self.body,
                self.recipient_policy,
                "1" if self.require_email_notifications else "0",
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _nonempty_text(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ApprovedClientMessageRegistryError(
            f"approved client-message {field} is required"
        )
    return text


def _parse_template(raw: Mapping[str, Any]) -> ApprovedClientMessage | None:
    enabled = raw.get("enabled")
    if not isinstance(enabled, bool):
        raise ApprovedClientMessageRegistryError(
            "approved client-message enabled must be boolean"
        )
    if not enabled:
        return None

    recipient_policy = _nonempty_text(
        raw.get("recipient_policy"),
        field="recipient_policy",
    )
    if recipient_policy != "ticket_contact":
        raise ApprovedClientMessageRegistryError(
            "approved client-message recipient_policy must be ticket_contact"
        )

    require_email_notifications = raw.get("require_email_notifications")
    if not isinstance(require_email_notifications, bool):
        raise ApprovedClientMessageRegistryError(
            "approved client-message require_email_notifications must be boolean"
        )

    return ApprovedClientMessage(
        template_id=_nonempty_text(raw.get("template_id"), field="template_id"),
        workflow_id=_nonempty_text(raw.get("workflow_id"), field="workflow_id"),
        title=_nonempty_text(raw.get("title"), field="title"),
        body=_nonempty_text(raw.get("body"), field="body"),
        recipient_policy=recipient_policy,
        require_email_notifications=require_email_notifications,
    )


def load_approved_client_messages(
    path: Path | None = None,
) -> tuple[ApprovedClientMessage, ...]:
    registry_path = path or DEFAULT_APPROVED_CLIENT_MESSAGE_REGISTRY
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApprovedClientMessageRegistryError(
            "approved client-message registry could not be loaded"
        ) from exc

    if not isinstance(payload, Mapping):
        raise ApprovedClientMessageRegistryError(
            "approved client-message registry root must be an object"
        )
    if payload.get("version") != APPROVED_CLIENT_MESSAGE_REGISTRY_VERSION:
        raise ApprovedClientMessageRegistryError(
            "approved client-message registry version is unsupported"
        )

    raw_templates = payload.get("templates")
    if not isinstance(raw_templates, list):
        raise ApprovedClientMessageRegistryError(
            "approved client-message templates must be a list"
        )

    templates: list[ApprovedClientMessage] = []
    seen_ids: set[str] = set()
    for raw in raw_templates:
        if not isinstance(raw, Mapping):
            raise ApprovedClientMessageRegistryError(
                "approved client-message template entry must be an object"
            )
        template = _parse_template(raw)
        if template is None:
            continue
        if template.template_id in seen_ids:
            raise ApprovedClientMessageRegistryError(
                "approved client-message template_id must be unique"
            )
        seen_ids.add(template.template_id)
        templates.append(template)

    return tuple(templates)


def resolve_approved_client_message(
    *,
    workflow_id: str,
    template_id: str,
    path: Path | None = None,
) -> ApprovedClientMessage:
    wanted_workflow = _nonempty_text(workflow_id, field="workflow_id")
    wanted_template = _nonempty_text(template_id, field="template_id")

    matches = tuple(
        item
        for item in load_approved_client_messages(path)
        if item.workflow_id == wanted_workflow
        and item.template_id == wanted_template
    )
    if len(matches) != 1:
        raise ApprovedClientMessageRegistryError(
            "client message is not approved for the exact workflow/template pair"
        )
    return matches[0]
