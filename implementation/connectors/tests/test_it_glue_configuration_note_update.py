"""Contract tests for source-only IT Glue notes mutation adapter."""
from dataclasses import replace

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError, ConnectorContext, ConnectorRequest,
    ConnectorTransportError,
)
from connectors.it_glue.configuration_note_update import (
    CAPABILITY, PROFILE_ENV, PROFILE_VALUE, WRITE_SECRET,
    ItGlueConfigurationNoteUpdateConnector,
)


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class FakeScope:
    allowed = True
    organization_id = 81
    def require_authorized(self, context):
        if not self.allowed or context.principal_id != "tech":
            raise ConnectorAuthorizationError("TEST_UNAUTHORIZED")
    def organization_id_for_client(self, *, client_id):
        if client_id != "client-17":
            raise ConnectorAuthorizationError("TEST_CLIENT_BOUNDARY_DENIED")
        return self.organization_id


class FakeSecrets:
    available = True
    def __init__(self):
        self.resolved = []
    def resolve(self, logical_name, context):
        self.resolved.append(logical_name)
        return {"api_key": "supersecret-private-write-key" if self.available else ""}


class FakeTransport:
    notes = "original internal notes"
    org_id = 81
    restricted = False
    revision = "2026-10-28T00:00:00.000Z"
    include_notes = True
    stale_readback = False
    forbidden_patch = False

    def __init__(self):
        self.calls = []
        self.patches = 0

    def request(self, *, method, url, headers, params=None, json=None,
                timeout_seconds=30.0, **kwargs):
        self.calls.append((method, url, json))
        if method == "GET":
            attributes = {
                "organization-id": self.org_id,
                "restricted": self.restricted,
                "updated-at": self.revision,
            }
            if self.include_notes:
                attributes["notes"] = self.notes
            if self.stale_readback and self.patches:
                attributes["notes"] = "not actually updated"
            return {
                "data": {"id": "101", "type": "configurations",
                         "attributes": attributes}
            }
        assert method == "PATCH"
        assert url == "https://api.itglue.com/configurations/101"
        if self.forbidden_patch:
            raise ConnectorTransportError("Unauthorized", status_code=403)
        assert json["data"]["type"] == "configurations"
        assert set(json["data"]["attributes"]) == {"notes"}
        self.patches += 1
        self.notes = json["data"]["attributes"]["notes"]
        self.revision = "2026-10-28T00:01:00.000Z"
        return {"data": {"id": "101", "type": "configurations"}}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv(PROFILE_ENV, PROFILE_VALUE)


def harness():
    transport, scope, secrets, audit = (
        FakeTransport(), FakeScope(), FakeSecrets(), FakeAudit()
    )
    connector = ItGlueConfigurationNoteUpdateConnector(
        transport=transport, credentials=secrets,
        authorization=scope, audit=audit,
    )
    return connector, transport, scope, secrets, audit


def req(*, client="client-17", principal="tech", org="aot",
        mode="execute", **args):
    context = ConnectorContext(
        correlation_id="corr-test", principal_id=principal,
        organization_id=org, client_id=client,
        capability=CAPABILITY, mode=mode,
    )
    return ConnectorRequest(context, {
        "configuration_id": 101, "notes": "approved updated notes", **args,
    })


def test_normal_notes_update_exact_plan_single_patch_with_readback(env):
    connector, t, scope, secrets, audit = harness()
    planned = connector.prepare_governed_execution(req())
    assert planned.provider_capability == CAPABILITY
    assert planned.action_method == "PATCH"
    assert planned.normalized_path == "/configurations/101"
    assert planned.resource_identifier == "101"
    assert planned.payload["attributes"]["notes_length"] == 22
    assert "approved updated notes" not in str(planned.payload)
    assert "supersecret-private-write-key" not in repr(planned)
    assert secrets.resolved == [WRITE_SECRET]
    assert t.patches == 0

    result = connector.execute_governed_execution(planned)
    assert t.patches == 1
    assert t.notes == "approved updated notes"
    assert result.data["jasonVerification"]["readbackVerified"] is True
    assert result.data["mutation_performed"] is True
    assert "approved updated notes" not in str(result.data)
    assert "supersecret" not in str(audit.events)
    assert [x[0] for x in audit.events] == [
        "connector.mutation.requested", "connector.mutation.verified",
    ]


def test_repeated_same_notes_is_verified_without_second_patch(env):
    connector, t, *_ = harness()
    plan = connector.prepare_governed_execution(req())
    connector.execute_governed_execution(plan)
    second = connector.prepare_governed_execution(req())
    result = connector.execute_governed_execution(second)
    assert t.patches == 1
    assert result.data["mutation_performed"] is False


@pytest.mark.parametrize("arg", [
    {"configuration_id": 0},
    {"configuration_id": True},
    {"configuration_id": "abc"},
    {"notes": ""},
    {"notes": " "},
    {"notes": None},
    {"notes": "a"*8001},
    {"serial_number": "new serial"},
    {"name": "rename"},
])
def test_input_rejects_invalid_or_extra_mutation_fields_before_network(env, arg):
    connector, t, *_ = harness()
    with pytest.raises(ValueError):
        connector.prepare_governed_execution(req(**arg))
    assert t.calls == []


@pytest.mark.parametrize("kwargs", [
    {"principal": "autonomy"},
    {"org": "another"},
    {"client": "different"},
    {"client": None},
    {"mode": "observe"},
])
def test_request_identity_and_scope_rejected_before_provider_write(env, kwargs):
    connector, t, *_ = harness()
    with pytest.raises((PermissionError, ConnectorAuthorizationError)):
        connector.prepare_governed_execution(req(**kwargs))
    assert t.patches == 0


@pytest.mark.parametrize("kind", ["cross_client", "restricted", "unknown_restriction", "no_notes"])
def test_provider_object_scope_and_restrictions_fail_closed(env, kind):
    connector, t, *_ = harness()
    if kind == "cross_client":
        t.org_id = 82
    elif kind == "restricted":
        t.restricted = True
    elif kind == "unknown_restriction":
        t.restricted = None
    else:
        t.include_notes = False
    with pytest.raises(ConnectorAuthorizationError):
        connector.prepare_governed_execution(req())
    assert t.patches == 0


def test_durable_client_binding_changes_before_execution_rejected(env):
    connector, t, scope, *_ = harness()
    plan = connector.prepare_governed_execution(req())
    scope.organization_id = 99
    with pytest.raises(ConnectorAuthorizationError, match="BOUNDARY_CHANGED"):
        connector.execute_governed_execution(plan)
    assert t.patches == 0


def test_preimage_change_before_execution_rejected_without_overwriting(env):
    connector, t, *_ = harness()
    plan = connector.prepare_governed_execution(req())
    t.notes = "newer technician work"
    t.revision = "2026-10-28T00:03:00.000Z"
    with pytest.raises(ConnectorAuthorizationError, match="STALE_CONFIGURATION"):
        connector.execute_governed_execution(plan)
    assert t.patches == 0


def test_plan_mutation_rejected_before_patch(env):
    connector, t, *_ = harness()
    plan = connector.prepare_governed_execution(req())
    plan.payload["attributes"]["notes_length"] = 9
    with pytest.raises(ConnectorAuthorizationError, match="APPROVED_PLAN_MISMATCH"):
        connector.execute_governed_execution(plan)
    assert t.patches == 0


def test_mutation_fail_without_existing_write_secret_not_readonly_fallback(env):
    connector, t, _, secrets, _ = harness()
    secrets.available = False
    with pytest.raises(PermissionError, match="RW_CREDENTIAL_UNAVAILABLE"):
        connector.prepare_governed_execution(req())
    assert secrets.resolved == [WRITE_SECRET]
    assert t.calls == []


def test_verification_failure_cannot_claim_success(env):
    connector, t, _, _, audit = harness()
    plan = connector.prepare_governed_execution(req())
    t.stale_readback = True
    with pytest.raises(RuntimeError, match="READBACK_FAILED"):
        connector.execute_governed_execution(plan)
    assert t.patches == 1
    assert audit.events[-1][0] == "connector.mutation.verification_failed"


def test_denied_provider_write_does_not_fallback_or_retry(env):
    connector, t, *_ = harness()
    plan = connector.prepare_governed_execution(req())
    t.forbidden_patch = True
    with pytest.raises(ConnectorTransportError) as error:
        connector.execute_governed_execution(plan)
    assert error.value.status_code == 403
    assert t.patches == 0
    assert len([x for x in t.calls if x[0] == "PATCH"]) == 1


def test_revoked_profile_before_execution_rejected(env, monkeypatch):
    connector, t, *_ = harness()
    plan = connector.prepare_governed_execution(req())
    monkeypatch.delenv(PROFILE_ENV)
    with pytest.raises(PermissionError, match="DISABLED"):
        connector.execute_governed_execution(plan)
    assert t.patches == 0


def test_direct_execute_api_never_runs_provider_write(env):
    connector, t, *_ = harness()
    with pytest.raises(ConnectorAuthorizationError, match="GOVERNED_PLAN_REQUIRED"):
        connector.execute(req())
    assert t.calls == []


def test_disabled_by_default(env, monkeypatch):
    connector, t, *_ = harness()
    monkeypatch.setenv(PROFILE_ENV, "false")
    with pytest.raises(PermissionError, match="DISABLED"):
        connector.prepare_governed_execution(req())
    assert t.calls == []


def test_auth_revoked_after_prepare_is_reevaluated(env):
    connector, t, scope, *_ = harness()
    plan = connector.prepare_governed_execution(req())
    scope.allowed = False
    with pytest.raises(ConnectorAuthorizationError, match="UNAUTHORIZED"):
        connector.execute_governed_execution(plan)
    assert t.patches == 0
