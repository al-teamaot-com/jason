from __future__ import annotations

import pytest

from connectors.core.contracts import ConnectorAuthorizationError, ConnectorContext, ConnectorRequest
from connectors.datto_rmm.connector import DattoRmmConnector
from connectors.datto_rmm.mutations import DattoRmmMutationConnector
from connectors.datto_rmm.site_variables import (
    require_site_variable_value_disclosure,
    sanitize_site_variables_for_principal,
)


class MemoryAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, context, details))


def context(capability: str, mode: str = "propose") -> ConnectorContext:
    return ConnectorContext(
        correlation_id="corr-site-variable",
        principal_id="person-tech",
        organization_id="aot",
        client_id="client-1",
        capability=capability,
        mode=mode,
    )


def test_site_variable_read_maps_to_documented_datto_endpoint():
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.site.variables.list",
        {"site_uid": "site-123"},
    )
    assert path == "/api/v2/site/site-123/variables"
    assert params is None


def test_non_admin_can_see_presence_but_not_value():
    payload = {"variables": [{"name": "BackupKey", "value": "super-secret"}]}
    governed = sanitize_site_variables_for_principal(payload, permission_mode="observe")
    assert governed == {
        "name_disclosure": "blocked",
        "value_disclosure": "blocked",
        "variable_count": 1,
    }




def test_non_admin_exact_name_query_returns_presence_without_enumerating_secrets():
    payload = {"variables": [{"name": "BackupKey", "value": "super-secret"}]}
    governed = sanitize_site_variables_for_principal(
        payload,
        permission_mode="observe",
        requested_name="BackupKey",
    )
    assert governed["requested_variable"] == {
        "requested_name": "BackupKey",
        "present": True,
        "configured": True,
    }
    assert "variables" not in governed

def test_admin_can_receive_value():
    payload = {"variables": [{"name": "BackupKey", "value": "super-secret"}]}
    governed = sanitize_site_variables_for_principal(payload, permission_mode="administer")
    assert governed["variables"][0]["value"] == "super-secret"
    assert governed["value_disclosure"] == "allowed"


def test_non_admin_explicit_value_disclosure_is_denied():
    with pytest.raises(ConnectorAuthorizationError, match="restricted to administrators"):
        require_site_variable_value_disclosure("observe")


def test_create_plan_redacts_value_from_returned_plan():
    connector = DattoRmmMutationConnector(audit=MemoryAudit())
    result = connector.execute(
        ConnectorRequest(
            context("datto_rmm.site.variable.create"),
            {
                "site_uid": "site-123",
                "name": "BackupKey",
                "value": "super-secret",
                "reason": "Configure approved backup deployment variable",
            },
        )
    )
    assert result.data["status"] == "proposed"
    assert result.data["plan"]["proposed_changes"]["value"] == "<redacted>"
    assert result.data["plan"]["proposed_changes"]["masked"] is True


def test_update_plan_redacts_value_from_returned_plan():
    connector = DattoRmmMutationConnector(audit=MemoryAudit())
    result = connector.execute(
        ConnectorRequest(
            context("datto_rmm.site.variable.update"),
            {
                "site_uid": "site-123",
                "variable_id": "variable-456",
                "value": "new-secret",
                "reason": "Rotate approved site variable",
            },
        )
    )
    assert result.data["plan"]["proposed_changes"]["value"] == "<redacted>"
    assert result.data["plan"]["target"]["variable_id"] == "variable-456"


def test_delete_capability_is_not_registered():
    assert "datto_rmm.site.variable.delete" not in DattoRmmMutationConnector.capabilities


def test_admin_exact_name_query_returns_only_requested_variable():
    payload = {
        "variables": [
            {"name": "BackupKey", "value": "value-a"},
            {"name": "OtherKey", "value": "value-b"},
        ]
    }
    governed = sanitize_site_variables_for_principal(
        payload,
        permission_mode="administer",
        requested_name="BackupKey",
    )
    assert governed["variables"] == [
        {"name": "BackupKey", "configured": True, "value": "value-a"}
    ]
