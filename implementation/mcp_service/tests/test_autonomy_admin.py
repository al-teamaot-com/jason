from __future__ import annotations

import json
from pathlib import Path

import pytest

from autonomous_remediation.playbook_autonomy_approval import (
    SQLitePlaybookAutonomyApprovalStore,
)
from jason_mcp.autonomy_admin import (
    AutonomyPromotionAdminError,
    promote_registered_playbook,
    registered_autonomy_scope,
)


def _registry(path: Path, *, activation: str = "autonomous") -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "playbooks": [
                    {
                        "id": "dns_agent_diagnostic",
                        "version": "1.0.0",
                        "lifecycle": "production",
                        "enabled": True,
                        "autonomy": {
                            "activation": activation,
                            "policy_id": "playbook-autonomy:dns_agent_diagnostic",
                            "allowed_capabilities": [
                                "automation.component.execute",
                                "service.ticket.note.create",
                                "service.ticket.update",
                            ],
                        },
                    }
                ],
            }
        )
    )
    return path


def test_registered_scope_requires_source_autonomous_activation(tmp_path: Path):
    path = _registry(tmp_path / "registry.json", activation="shadow")
    with pytest.raises(
        AutonomyPromotionAdminError, match="PLAYBOOK_AUTONOMY_NOT_ACTIVATED"
    ):
        registered_autonomy_scope(
            registry_path=path,
            playbook_id="dns_agent_diagnostic",
        )


def test_owner_can_promote_exact_registered_scope(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES", "person-al")
    path = _registry(tmp_path / "registry.json")
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotion.sqlite3")
    try:
        record, created, scope = promote_registered_playbook(
            store=store,
            registry_path=path,
            playbook_id="dns_agent_diagnostic",
            approved_by="person-al",
        )
        assert created is True
        assert record.playbook_id == "dns_agent_diagnostic"
        assert record.playbook_version == "1.0.0"
        assert record.policy_id == "playbook-autonomy:dns_agent_diagnostic"
        assert record.allowed_capabilities == (
            "automation.component.execute",
            "service.ticket.note.create",
            "service.ticket.update",
        )
        assert len(scope["registry_sha256"]) == 64

        again, created_again, _ = promote_registered_playbook(
            store=store,
            registry_path=path,
            playbook_id="dns_agent_diagnostic",
            approved_by="person-al",
        )
        assert created_again is False
        assert again.approval_id == record.approval_id
    finally:
        store.close()


def test_nonowner_cannot_promote(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES", "person-al")
    path = _registry(tmp_path / "registry.json")
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotion.sqlite3")
    try:
        with pytest.raises(
            AutonomyPromotionAdminError, match="PLAYBOOK_AUTONOMY_OWNER_REQUIRED"
        ):
            promote_registered_playbook(
                store=store,
                registry_path=path,
                playbook_id="dns_agent_diagnostic",
                approved_by="person-other",
            )
    finally:
        store.close()
