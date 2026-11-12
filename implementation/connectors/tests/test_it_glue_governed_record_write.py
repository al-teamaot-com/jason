"""Source-only governed IT Glue record writer: positive and negative J-102 tests."""
from dataclasses import replace

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError, ConnectorContext, ConnectorRequest,
    ConnectorTransportError,
)
from connectors.it_glue.governed_record_write import (
    CAPABILITIES, PROFILE_ENV, PROFILE_VALUE, WRITE_SECRET,
    ItGlueGovernedRecordWriter,
)


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event, ctx, payload):
        self.events.append((event, payload))


class TrustedScope:
    allowed = True
    org_id = 81

    def require_authorized(self, ctx):
        if not self.allowed or ctx.principal_id != "technician":
            raise ConnectorAuthorizationError("REQUESTER_DENIED")

    def organization_id_for_client(self, *, client_id):
        if client_id != "client-17":
            raise ConnectorAuthorizationError("CLIENT_DENIED")
        return self.org_id


class Secrets:
    def __init__(self):
        self.used = []
        self.api_key = "test-private-key"

    def resolve(self, secret_name, ctx):
        self.used.append(secret_name)
        return {"api_key": self.api_key}


class Claims:
    def __init__(self):
        self.seen = {}

    def claim_once(self, *, key, payload_sha256):
        if key in self.seen:
            return False
        self.seen[key] = payload_sha256
        return True


class Transport:
    def __init__(self, kind="flexible-assets"):
        self.kind = kind
        self.calls = []
        self.next_id = 201
        self.writes = 0
        self.restrict = False
        self.revision = "v1"
        self.org_id = 81
        self.readback_corrupt = False
        self.raise_after_write = False
        self.folder_org = 81
        self.existing = {
            "id": "101",
            "type": kind,
            "attributes": {
                "organization-id": 81, "restricted": False,
                "updated-at": self.revision,
                "traits": {"domain": "example.com", "backup-server": "old"},
                "name": "original",
            },
        }

    def request(self, *, method, url, headers, params=None, json=None,
                timeout_seconds=20.0):
        assert headers["x-api-key"] == "test-private-key"
        self.calls.append((method, url, json))
        if method == "GET":
            if url == "https://api.itglue.com/organizations/81":
                return {"data": {"type": "organizations", "id": "81"}}
            if url == "https://api.itglue.com/document_folders/32":
                return {"data": {"type": "document-folders", "id": "32",
                                 "attributes": {"organization-id": self.folder_org}}}
            data = {
                "id": self.existing["id"],
                "type": self.existing["type"],
                "attributes": dict(self.existing["attributes"]),
            }
            data["attributes"]["restricted"] = self.restrict
            data["attributes"]["organization-id"] = self.org_id
            if self.readback_corrupt and self.writes:
                data["attributes"]["name"] = "bad readback"
                data["attributes"]["traits"] = {"domain": "bad readback"}
            return {"data": data}
        assert method in ("POST", "PATCH")
        self.writes += 1
        attrs = json["data"]["attributes"]
        if method == "POST":
            self.existing["id"] = str(self.next_id)
            self.existing["type"] = json["data"]["type"]
        self.existing["attributes"].update({k.replace("_", "-"): v
                                            for k, v in attrs.items()})
        self.existing["attributes"]["updated-at"] = "v2"
        if self.raise_after_write:
            raise ConnectorTransportError("ambiguous transport failure")
        return {"data": {"type": json["data"]["type"],
                         "id": self.existing["id"]}}


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setenv(PROFILE_ENV, PROFILE_VALUE)


def request(cap, *, client="client-17", principal="technician",
            org="aot", mode="execute", **args):
    return ConnectorRequest(
        ConnectorContext(correlation_id="corr-test", principal_id=principal,
                         organization_id=org, client_id=client,
                         capability=cap, mode=mode),
        args,
    )


def harness(kind="flexible-assets", *, claims=True):
    transport = Transport(kind)
    secrets, scope, audit = Secrets(), TrustedScope(), Audit()
    ledger = Claims() if claims else None
    writer = ItGlueGovernedRecordWriter(
        transport=transport, credentials=secrets,
        authorization=scope, audit=audit, creation_claims=ledger,
    )
    return writer, transport, secrets, scope, audit, ledger


def test_capability_inventory_is_explicit_and_no_unapproved_delete():
    assert CAPABILITIES == {
        "it_glue.flexible_asset.create", "it_glue.flexible_asset.update",
        "it_glue.document.create", "it_glue.document.update",
        "it_glue.configuration.create",
    }


def test_update_flexible_assets_merges_traits_and_verifies(ready):
    writer, t, secrets, _, audit, _ = harness()
    req = request("it_glue.flexible_asset.update", resource_id=101,
                  traits={"backup-server": "new"})
    plan = writer.prepare_governed_execution(req)
    assert t.writes == 0
    assert plan.action_method == "PATCH"
    assert plan.normalized_path == "/flexible_assets/101"
    assert "new" not in repr(plan)
    assert "test-private-key" not in repr(plan)
    assert secrets.used == [WRITE_SECRET]
    result = writer.execute_governed_execution(plan)
    assert t.writes == 1
    assert t.existing["attributes"]["traits"] == {
        "domain": "example.com", "backup-server": "new"}
    assert result.data["jasonVerification"]["readbackVerified"] is True
    assert result.data["mutation_performed"] is True
    assert "test-private-key" not in str(audit.events)
    assert "example.com" not in str(audit.events)


@pytest.mark.parametrize("cap,kwargs,kind", [
    ("it_glue.flexible_asset.create", {
        "flexible_asset_type_id": 42, "traits": {"backup-server": "server1"},
        "request_id": "approved-create-20261112-0001",
    }, "flexible-assets"),
    ("it_glue.document.create", {
        "name": "New network procedure", "folder_id": 32,
        "request_id": "approved-create-20261112-0002",
    }, "documents"),
    ("it_glue.configuration.create", {
        "name": "Device-001", "configuration_type_id": 24,
        "request_id": "approved-create-20261112-0003",
    }, "configurations"),
])
def test_creates_only_once_with_durable_claim_and_get_readback(ready, cap, kwargs, kind):
    writer, t, _, _, _, ledger = harness(kind)
    req = request(cap, **kwargs)
    plan = writer.prepare_governed_execution(req)
    assert t.writes == 0
    assert plan.action_method == "POST"
    result = writer.execute_governed_execution(plan)
    assert result.data["resource_id"] == 201
    assert result.data["jasonVerification"]["readbackVerified"] is True
    assert t.writes == 1
    assert len(ledger.seen) == 1
    with pytest.raises(ConnectorAuthorizationError, match="ALREADY_CLAIMED"):
        writer.execute_governed_execution(plan)
    assert t.writes == 1


def test_document_metadata_update_does_not_change_restriction_or_public(ready):
    writer, t, *_ = harness("documents")
    req = request("it_glue.document.update", resource_id=101, name="Renamed SOP")
    result = writer.execute_governed_execution(writer.prepare_governed_execution(req))
    assert result.data["mutation_performed"] is True
    patch = [x for x in t.calls if x[0] == "PATCH"][0]
    assert patch[2] == {"data": {"type": "documents",
                                  "attributes": {"name": "Renamed SOP"}}}


def test_noop_update_does_not_issue_patch(ready):
    writer, t, *_ = harness()
    req = request("it_glue.flexible_asset.update", resource_id=101,
                  traits={"backup-server": "old"})
    result = writer.execute_governed_execution(writer.prepare_governed_execution(req))
    assert result.data["mutation_performed"] is False
    assert t.writes == 0


def test_stale_preimage_blocks_write(ready):
    writer, t, *_ = harness()
    plan = writer.prepare_governed_execution(request(
        "it_glue.flexible_asset.update", resource_id=101,
        traits={"backup-server": "new"}))
    t.existing["attributes"]["traits"] = {"domain": "elsewhere"}
    with pytest.raises(ConnectorAuthorizationError, match="STALE_RESOURCE_PREIMAGE"):
        writer.execute_governed_execution(plan)
    assert t.writes == 0


@pytest.mark.parametrize("kind,cap,args", [
    ("flexible-assets", "it_glue.flexible_asset.update",
     {"resource_id": 101, "traits": {"backup-server": "new"}}),
    ("documents", "it_glue.document.update",
     {"resource_id": 101, "name": "New title"}),
])
def test_cross_client_and_restricted_fail_before_write(ready, kind, cap, args):
    writer, t, *_ = harness(kind)
    t.org_id = 99
    with pytest.raises(ConnectorAuthorizationError, match="CROSS_CLIENT"):
        writer.prepare_governed_execution(request(cap, **args))
    t.org_id = 81
    t.restrict = True
    with pytest.raises(ConnectorAuthorizationError, match="RESTRICTED"):
        writer.prepare_governed_execution(request(cap, **args))
    assert t.writes == 0


@pytest.mark.parametrize("args", [
    {"resource_id": 101, "traits": {"password": "sensitive"}},
    {"resource_id": 101, "traits": {"api-key": "sensitive"}},
    {"resource_id": 101, "traits": {"domain": None}},
    {"resource_id": 101, "traits": {"domain": {"nested": "bad"}}},
    {"resource_id": 101, "traits": {}},
    {"resource_id": -1, "traits": {"domain": "example.com"}},
    {"resource_id": 101, "traits": {"domain": "new"}, "danger": True},
])
def test_invalid_or_sensitive_fields_fail_closed(ready, args):
    writer, t, *_ = harness()
    with pytest.raises(ValueError):
        writer.prepare_governed_execution(request(
            "it_glue.flexible_asset.update", **args))
    assert t.writes == 0


@pytest.mark.parametrize("overrides", [
    {"client": "another"},
    {"principal": "autonomy"},
    {"org": "another"},
    {"mode": "observe"},
])
def test_invalid_scope_blocks_before_provider_call(ready, overrides):
    writer, t, *_ = harness()
    with pytest.raises((PermissionError, ConnectorAuthorizationError)):
        writer.prepare_governed_execution(request(
            "it_glue.flexible_asset.update",
            resource_id=101, traits={"domain": "new"}, **overrides))
    assert t.calls == []


def test_create_requires_durable_ledger(ready):
    writer, t, *_ = harness(claims=False)
    plan = writer.prepare_governed_execution(request(
        "it_glue.flexible_asset.create",
        flexible_asset_type_id=42, traits={"domain": "example.org"},
        request_id="approved-create-20261112-0004"))
    with pytest.raises(ConnectorAuthorizationError, match="CLAIM_MISSING"):
        writer.execute_governed_execution(plan)
    assert t.writes == 0


def test_creation_ambiguous_failure_is_claimed_and_never_retried(ready):
    writer, t, *_ = harness()
    plan = writer.prepare_governed_execution(request(
        "it_glue.configuration.create", name="Test",
        configuration_type_id=2,
        request_id="approved-create-20261112-0005"))
    t.raise_after_write = True
    with pytest.raises(ConnectorTransportError):
        writer.execute_governed_execution(plan)
    with pytest.raises(ConnectorAuthorizationError, match="ALREADY_CLAIMED"):
        writer.execute_governed_execution(plan)
    assert t.writes == 1


def test_plan_tampering_and_missing_write_key_fail_closed(ready):
    writer, t, secrets, *_ = harness()
    plan = writer.prepare_governed_execution(request(
        "it_glue.flexible_asset.update", resource_id=101,
        traits={"backup-server": "new"}))
    with pytest.raises(ConnectorAuthorizationError, match="TAMPERED"):
        writer.execute_governed_execution(replace(plan, normalized_path="/other"))
    assert t.writes == 0
    secrets.api_key = ""
    with pytest.raises(PermissionError, match="WRITE_KEY"):
        writer.prepare_governed_execution(request(
            "it_glue.flexible_asset.update", resource_id=101,
            traits={"backup-server": "new"}))
    assert secrets.used[-1] == WRITE_SECRET


def test_disabled_profile_blocks_write(ready, monkeypatch):
    monkeypatch.delenv(PROFILE_ENV)
    writer, t, *_ = harness()
    with pytest.raises(PermissionError, match="DISABLED"):
        writer.prepare_governed_execution(request(
            "it_glue.document.update", resource_id=101, name="No"))
    assert t.calls == []


def test_verification_failure_is_not_reported_as_success(ready):
    writer, t, *_ = harness("documents")
    plan = writer.prepare_governed_execution(
        request("it_glue.document.update", resource_id=101, name="Updated"))
    t.readback_corrupt = True
    with pytest.raises(RuntimeError, match="READBACK_MISMATCH"):
        writer.execute_governed_execution(plan)
    assert t.writes == 1


def test_existing_secret_trait_blocks_merge_before_write(ready):
    writer, t, *_ = harness()
    t.existing["attributes"]["traits"]["api-key"] = "secret"
    with pytest.raises(ConnectorAuthorizationError, match="SENSITIVE_TRAITS"):
        writer.prepare_governed_execution(request(
            "it_glue.flexible_asset.update", resource_id=101,
            traits={"backup-server": "new"}))
    assert t.writes == 0


def test_cross_client_document_folder_blocks_creation(ready):
    writer, t, *_ = harness("documents")
    t.folder_org = 999
    with pytest.raises(ConnectorAuthorizationError, match="CROSS_CLIENT_DOCUMENT_FOLDER"):
        writer.prepare_governed_execution(request(
            "it_glue.document.create", name="New SOP", folder_id=32,
            request_id="approved-create-20261112-0006"))
    assert t.writes == 0
