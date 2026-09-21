from __future__ import annotations

from types import SimpleNamespace

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from jason_runtime import datto_site_variable_management as module


SITE = "11111111-1111-1111-1111-111111111111"
VARIABLE = "22222222-2222-2222-2222-222222222222"


class Secrets:
    def resolve(self, logical_name, context):
        assert logical_name == module.DATTO_SITE_VARIABLE_LOGICAL_SECRET
        return {
            "api_url": "https://example.invalid",
            "api_key": "key",
            "api_secret": "secret",
        }


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, details))


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected transport call")
        return self.responses.pop(0)


def request(capability, arguments):
    return ConnectorRequest(
        ConnectorContext(
            correlation_id="corr-test",
            principal_id="person-owner",
            organization_id="aot",
            client_id=None,
            capability=capability,
            mode="execute",
        ),
        arguments,
    )


def test_create_uses_put_and_never_returns_or_audits_secret(monkeypatch):
    monkeypatch.setattr(
        module,
        "acquire_access_token",
        lambda credentials: SimpleNamespace(token_type="Bearer", access_token="token"),
    )
    transport = Transport(
        [
            {"variables": []},
            {},
            {
                "variables": [
                    {"id": VARIABLE, "name": "BackupKey", "value": "super-secret", "masked": True}
                ]
            },
        ]
    )
    audit = Audit()
    connector = module.DattoSiteVariableManagementConnector(
        secrets=Secrets(), transport=transport, audit=audit
    )

    result = connector.execute(
        request(
            module.DATTO_SITE_VARIABLE_CREATE,
            {"site_uid": SITE, "name": "BackupKey", "value": "super-secret", "masked": True},
        )
    )

    assert transport.calls[1]["method"] == "PUT"
    assert transport.calls[1]["url"].endswith(f"/api/v2/site/{SITE}/variable")
    assert result.data["value_disclosed"] is False
    assert "super-secret" not in repr(result.data)
    assert "super-secret" not in repr(audit.events)


def test_update_uses_current_plural_endpoint_and_requires_exact_variable(monkeypatch):
    monkeypatch.setattr(
        module,
        "acquire_access_token",
        lambda credentials: SimpleNamespace(token_type="Bearer", access_token="token"),
    )
    before = {"variables": [{"id": VARIABLE, "name": "BackupKey", "masked": True}]}
    after = {"variables": [{"id": VARIABLE, "name": "BackupKey", "masked": True}]}
    transport = Transport([before, {}, after])
    connector = module.DattoSiteVariableManagementConnector(
        secrets=Secrets(), transport=transport, audit=Audit()
    )

    result = connector.execute(
        request(
            module.DATTO_SITE_VARIABLE_UPDATE,
            {
                "site_uid": SITE,
                "variable_id": VARIABLE,
                "name": "BackupKey",
                "value": "rotated-secret",
            },
        )
    )

    assert transport.calls[1]["method"] == "POST"
    assert transport.calls[1]["url"].endswith(
        f"/api/v2/site/{SITE}/variables/{VARIABLE}"
    )
    assert result.data["readback_verified"] is True


def test_delete_capability_is_not_exposed():
    connector = module.DattoSiteVariableManagementConnector(
        secrets=Secrets(), transport=Transport([]), audit=Audit()
    )
    assert "management.site.variable.delete" not in {
        module.SITE_VARIABLE_CREATE,
        module.SITE_VARIABLE_UPDATE,
    }
    assert "datto_rmm.site.variable.delete" not in connector.capabilities


def test_site_variable_management_reuses_existing_datto_execution_identity():
    assert module.DATTO_SITE_VARIABLE_LOGICAL_SECRET == "datto_rmm.execution"
    assert str(module.DEFAULT_ROLE_ID_PATH) == (
        "/run/jason-secrets/openbao/datto-rmm-execution/role_id"
    )
    assert str(module.DEFAULT_SECRET_ID_PATH) == (
        "/run/jason-secrets/openbao/datto-rmm-execution/secret_id"
    )
    assert module.SITE_VARIABLE_ROLE_ID_ENV == (
        "JASON_DATTO_EXECUTION_OPENBAO_ROLE_ID_PATH"
    )
    assert module.SITE_VARIABLE_SECRET_ID_ENV == (
        "JASON_DATTO_EXECUTION_OPENBAO_SECRET_ID_PATH"
    )
