from datetime import datetime, timedelta, timezone

import pytest

from connectors.core.contracts import ConnectorAuthorizationError, ConnectorContext
from connectors.microsoft_graph.standard_user_create import TrustedCloudUserScope
from kernel.client_boundaries import (
    BoundaryStatus, ClientBoundary, InMemoryClientBoundaryRepository,
)
from kernel.identity_authority import (
    ApprovalRecord, IdentityRecord, InMemoryApprovalRepository,
    InMemoryIdentityRepository,
)
from jason_runtime.routine_rw_scope import AotEntraOnboardingScope, AotItGlueWriteScope


def ctx(*, principal="tech", org="aot", client="xyz"):
    return ConnectorContext(
        correlation_id="corr-1", principal_id=principal,
        organization_id=org, client_id=client,
        capability="identity.user.create", mode="execute",
    )


def boundary(*, provider, profile, tenant, scope=()):
    now = datetime.now(timezone.utc)
    return ClientBoundary(
        id=f"{provider}-xyz", client_id="xyz", provider=provider,
        external_tenant_id=tenant,
        primary_domain="xyz.example", profile=profile,
        application_id="00000000-0000-0000-0000-000000000010",
        status=BoundaryStatus.VALIDATED,
        consent_transaction_id="consent-123",
        created_at=now, validated_at=now,
        external_scope_ids=scope,
    )


def fixture():
    identities = InMemoryIdentityRepository()
    identities.put(IdentityRecord("tech", "human", "aot"))
    identities.put(IdentityRecord("autonomy", "service", "aot"))
    identities.put(IdentityRecord("disabled", "human", "aot", status="disabled"))
    boundaries = InMemoryClientBoundaryRepository()
    boundaries.add(boundary(
        provider="it_glue", profile="configuration-notes-v1",
        tenant="77",
    ))
    boundaries.add(boundary(
        provider="microsoft_graph", profile="directory-read",
        tenant="22222222-2222-2222-2222-222222222222",
    ))
    boundaries.add(boundary(
        provider="microsoft_graph_user_create", profile="user-create",
        tenant="22222222-2222-2222-2222-222222222222",
        scope=("source:entra_cloud",),
    ))
    approvals = InMemoryApprovalRepository()
    now = datetime.now(timezone.utc)
    approvals.put(ApprovalRecord(
        approval_id="REQ-12345", request_id="upn:test.user@xyz.example",
        capability="identity.user.create", organization_id="aot",
        client_id="xyz", requested_by="tech",
        status="approved", decided_by="approved-aot-authority",
        decided_at=now,
        expires_at=now+timedelta(minutes=20),
    ))
    return identities, boundaries, approvals


def test_it_glue_exact_client_mapping_requires_validated_boundary():
    ids, bounds, _ = fixture()
    scope = AotItGlueWriteScope(ids, bounds)
    scope.require_authorized(ctx())
    assert scope.organization_id_for_client(client_id="xyz") == 77
    with pytest.raises(ConnectorAuthorizationError):
        scope.organization_id_for_client(client_id="another")


@pytest.mark.parametrize("principal,org,client", [
    ("autonomy", "aot", "xyz"),
    ("disabled", "aot", "xyz"),
    ("missing", "aot", "xyz"),
    ("tech", "foreign", "xyz"),
    ("tech", "aot", "other"),
    ("tech", "aot", None),
])
def test_no_wrong_identity_or_client(principal, org, client):
    ids, bounds, approvals = fixture()
    for adapter in (
        AotItGlueWriteScope(ids, bounds),
        AotEntraOnboardingScope(ids, approvals, bounds),
    ):
        with pytest.raises(ConnectorAuthorizationError):
            if hasattr(adapter, "require_authorized"):
                adapter.require_authorized(ctx(principal=principal, org=org, client=client))
            else:
                adapter.require_approved_request(
                    context=ctx(principal=principal, org=org, client=client),
                    request_id="REQ-12345",
                )


def test_approved_cloud_only_onboarding_requires_two_matching_tenant_boundaries():
    ids, bounds, approvals = fixture()
    adapter = AotEntraOnboardingScope(ids, approvals, bounds)
    assert adapter.require_approved_request(
        context=ctx(), request_id="REQ-12345",
    ) == TrustedCloudUserScope(
        client_id="xyz",
        tenant_id="22222222-2222-2222-2222-222222222222",
        managed_domains=frozenset({"xyz.example"}),
        source_authority="entra_cloud",
        approved_user_principal_name="test.user@xyz.example",
    )
    with pytest.raises(ConnectorAuthorizationError, match="APPROVAL_NOT_VALID"):
        adapter.require_approved_request(
            context=ctx(), request_id="not-an-approved-request",
        )


def test_no_implicit_onboarding_without_approved_request():
    ids, bounds, approvals = fixture()
    adapter = AotEntraOnboardingScope(ids, approvals, bounds)
    with pytest.raises(ConnectorAuthorizationError, match="ACTIVE_AOT_TECHNICIAN_REQUIRED"):
        adapter.require_approved_request(
            context=ctx(principal="autonomy"), request_id="REQ-12345",
        )


def test_approval_does_not_cover_unauthorized_client():
    ids, bounds, approvals = fixture()
    adapter = AotEntraOnboardingScope(ids, approvals, bounds)
    with pytest.raises(ConnectorAuthorizationError):
        adapter.require_approved_request(
            context=ctx(client="another"), request_id="REQ-12345",
        )
