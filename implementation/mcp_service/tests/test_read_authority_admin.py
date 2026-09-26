from __future__ import annotations

from types import SimpleNamespace

import pytest

import jason_mcp.read_authority_admin as admin


class FakeRepo:
    def __init__(self):
        self.rows = {}

    def get(self, grant_id):
        return self.rows.get(grant_id)

    def put(self, grant):
        self.rows[grant.grant_id] = grant


class FakeAudit:
    def __init__(self):
        self.events = []

    def append_authority_audit(self, **kwargs):
        self.events.append(kwargs)


class FakeCapabilities:
    def __init__(self, read_only=True):
        self.read_only = read_only

    def list_all(self):
        return (
            SimpleNamespace(
                capability_name="endpoint.alert.history.search",
                lifecycle_status=SimpleNamespace(value="active"),
                metadata={"read_only": "true" if self.read_only else "false"},
            ),
        )


def fake_runtime(*, read_only=True):
    repo = FakeRepo()
    audit = FakeAudit()
    identity = SimpleNamespace(status="active", organization_id="aot")
    app = SimpleNamespace(
        capabilities=FakeCapabilities(read_only=read_only),
        identity_authority=SimpleNamespace(
            identities={"jason-autonomy-worker": identity},
            grants=repo,
            audit=audit,
        ),
    )
    return app, repo, audit


def test_owner_can_grant_exact_active_read(monkeypatch):
    app, repo, audit = fake_runtime()
    monkeypatch.setattr(admin, "_runtime", lambda: app)
    monkeypatch.setattr(
        admin,
        "approval_owner_identities",
        lambda: frozenset({"person-al"}),
    )

    grant, created = admin.grant_exact_read_authority(
        subject_id="jason-autonomy-worker",
        capability="endpoint.alert.history.search",
        approved_by="person-al",
    )

    assert created is True
    assert grant.permission.value == "observe"
    assert grant.approval_required is False
    assert repo.get(grant.grant_id) == grant
    assert [event["event_type"] for event in audit.events] == [
        "authority.grant.create.requested",
        "authority.grant.created",
    ]

    again, created_again = admin.grant_exact_read_authority(
        subject_id="jason-autonomy-worker",
        capability="endpoint.alert.history.search",
        approved_by="person-al",
    )
    assert created_again is False
    assert again.grant_id == grant.grant_id


def test_nonowner_is_rejected(monkeypatch):
    app, _, _ = fake_runtime()
    monkeypatch.setattr(admin, "_runtime", lambda: app)
    monkeypatch.setattr(
        admin,
        "approval_owner_identities",
        lambda: frozenset({"person-al"}),
    )

    with pytest.raises(
        admin.ReadAuthorityAdminError,
        match="AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED",
    ):
        admin.grant_exact_read_authority(
            subject_id="jason-autonomy-worker",
            capability="endpoint.alert.history.search",
            approved_by="person-other",
        )


def test_write_capability_cannot_be_granted(monkeypatch):
    app, _, _ = fake_runtime(read_only=False)
    monkeypatch.setattr(admin, "_runtime", lambda: app)
    monkeypatch.setattr(
        admin,
        "approval_owner_identities",
        lambda: frozenset({"person-al"}),
    )

    with pytest.raises(
        admin.ReadAuthorityAdminError,
        match="AUTHORITY_GRANT_READ_ONLY_REQUIRED",
    ):
        admin.grant_exact_read_authority(
            subject_id="jason-autonomy-worker",
            capability="endpoint.alert.history.search",
            approved_by="person-al",
        )
