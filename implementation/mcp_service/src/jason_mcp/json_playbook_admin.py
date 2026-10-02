"""MCP-facing administration for durable JSON playbooks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from autonomous_remediation.playbook_document import (
    PlaybookValidationError,
    validate_playbook_document,
)
from autonomous_remediation.playbook_store import SQLitePlaybookRegistry


JSON_PLAYBOOK_DB_ENV = "JASON_JSON_PLAYBOOK_DB"
JSON_PLAYBOOK_DB_DEFAULT = "/var/lib/jason/openclaw/json-playbooks.sqlite3"


def registry_path() -> Path:
    return Path(os.environ.get(JSON_PLAYBOOK_DB_ENV, JSON_PLAYBOOK_DB_DEFAULT).strip())


def open_registry() -> SQLitePlaybookRegistry:
    return SQLitePlaybookRegistry(registry_path())


def parse_payload(payload_json: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(str(payload_json))
    except (TypeError, json.JSONDecodeError) as exc:
        raise PlaybookValidationError(("PLAYBOOK_JSON_INVALID",)) from exc
    if not isinstance(payload, Mapping):
        raise PlaybookValidationError(("PLAYBOOK_JSON_OBJECT_REQUIRED",))
    return payload


def validate_payload(
    payload_json: str,
    *,
    known_capabilities: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    document = validate_playbook_document(
        parse_payload(payload_json),
        known_capabilities=known_capabilities,
    )
    return {
        "status": "valid",
        "playbook_id": document.playbook_id,
        "name": document.name,
        "version": document.version,
        "lifecycle": document.lifecycle,
        "target_type": document.target_type,
        "fingerprint": document.fingerprint,
        "capabilities": list(document.capabilities),
        "autonomy_activation": document.autonomy_activation,
    }
