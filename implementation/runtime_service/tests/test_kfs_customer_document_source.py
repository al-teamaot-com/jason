from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from openpyxl import Workbook

from connectors.core.contracts import ConnectorResult
from jason_runtime.kfs_customer_document_source import (
    ApprovedAotCopierEvidenceSnapshot,
    ApprovedAotCopierSource,
    GovernedAotCopierSourceLoader,
    GovernedAotCopierEvidenceCache,
)

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)
TENANT = "aot-tenant"
SOURCE = ApprovedAotCopierSource(TENANT, "aot-admin-site", "copier-library", "document-1")


def workbook_bytes(customer="Marcella Operator LLC", serial="1G55503749"):
    book = Workbook()
    sheet = book.active
    sheet.append(("CO. NAME:", customer))
    sheet.append(("S/N:", serial))
    stream = BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


class FakeGovernedReader:
    def __init__(self, *, allowed=("document-1",), rejected=()):
        self.allowed = set(allowed)
        self.rejected = set(rejected)
        self.events = []
        self.content = workbook_bytes()
        self.etag = '"v3"'

    def execute(self, request):
        context, args = request.context, request.arguments
        self.events.append((context, dict(args)))
        assert context.organization_id == "aot"
        assert context.client_id is None
        assert context.principal_id == "trusted-kfs-evidence-service"
        assert context.mode == "observe"
        assert context.capability in {
            "knowledge.document.metadata.read", "knowledge.document.content.read"
        }
        assert set(args) == {"site_id", "drive_id", "item_id"}
        if args["item_id"] not in self.allowed or args["item_id"] in self.rejected:
            raise PermissionError("source is not approved")
        metadata = {
            "id": args["item_id"],
            "site_id": args["site_id"],
            "drive_id": args["drive_id"],
            "eTag": self.etag,
            "name": "AOT Copier Delivery Receipt.xlsx",
            "size": len(self.content),
            "lastModifiedDateTime": "2026-10-29T12:00:00Z",
            "webUrl": "https://aot.sharepoint.com/copier/document-1",
            "file": {
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            },
        }
        data = (
            {"item": metadata}
            if context.capability == "knowledge.document.metadata.read"
            else {
                "encoding": "base64",
                "content_b64": base64.b64encode(self.content).decode("ascii"),
                "byte_length": len(self.content),
                "sha256": hashlib.sha256(self.content).hexdigest(),
            }
        )
        return ConnectorResult(
            capability=context.capability, provider="microsoft_graph", data=data,
        )


def loader(reader, *sources):
    return GovernedAotCopierSourceLoader(
        connector=reader,
        principal_id="trusted-kfs-evidence-service",
        sources=sources or (SOURCE,),
    )


def test_one_document_refresh_has_metadata_content_metadata_ledger():
    reader = FakeGovernedReader()
    evidence = loader(reader).refresh(now=NOW)
    match = evidence.match(serial_number="1G55503749")
    assert match.status == "verified"
    assert match.customer_name == "Marcella Operator LLC"
    assert [event[0].capability for event in reader.events] == [
        "knowledge.document.metadata.read",
        "knowledge.document.content.read",
        "knowledge.document.metadata.read",
    ]
    assert match.evidence[0].source_item_id == "document-1"
    assert match.evidence[0].source_etag == '"v3"'


def test_explicit_unauthorized_document_blocks_entire_refresh():
    reader = FakeGovernedReader(allowed=("document-1",), rejected=("document-2",))
    source_two = replace(SOURCE, item_id="document-2")
    with pytest.raises(PermissionError, match="not approved"):
        loader(reader, SOURCE, source_two).refresh(now=NOW)


def test_refresh_fails_on_changed_document_version():
    reader = FakeGovernedReader()
    original = reader.execute
    def drift(request):
        result = original(request)
        if len(reader.events) == 3:
            data = dict(result.data)
            data["item"] = {**data["item"], "eTag": '"v4"'}
            return replace(result, data=data)
        return result
    reader.execute = drift
    with pytest.raises(ValueError, match="changed during read"):
        loader(reader).refresh(now=NOW)


def test_untrusted_source_manifest_denied_before_provider_call():
    reader = FakeGovernedReader()
    with pytest.raises(ValueError, match="exact"):
        loader(reader, replace(SOURCE, item_id="*"))
    assert reader.events == []


def test_source_loader_refuses_cross_tenant_batch():
    reader = FakeGovernedReader()
    with pytest.raises(ValueError, match="AOT tenant"):
        loader(reader, SOURCE, replace(SOURCE, tenant_id="another-tenant", item_id="other"))
    assert reader.events == []


def test_fresh_cached_snapshot_is_offline_and_expires_closed():
    reader = FakeGovernedReader()
    index = loader(reader).refresh(now=NOW)
    count = len(reader.events)
    snapshot = ApprovedAotCopierEvidenceSnapshot(
        index=index, refreshed_at=NOW, max_age_hours=24,
    )
    assert snapshot.usable_at(NOW + timedelta(hours=23)).match(
        serial_number="1G55503749",
    ).status == "verified"
    assert len(reader.events) == count
    with pytest.raises(PermissionError, match="stale"):
        snapshot.usable_at(NOW + timedelta(hours=25))
    assert len(reader.events) == count


def test_no_unauthorized_client_scope_or_mutation_in_source_manifest():
    reader = FakeGovernedReader()
    loader(reader).refresh(now=NOW)
    assert all(context.client_id is None for context, _ in reader.events)
    assert all(context.mode == "observe" for context, _ in reader.events)



def test_customer_evidence_cache_refreshes_only_when_expired():
    reader = FakeGovernedReader()
    cache = GovernedAotCopierEvidenceCache(
        loader=loader(reader), max_age_hours=24,
    )
    first = cache.index_for_rank(NOW)
    assert first.match(serial_number="1G55503749").status == "verified"
    assert len(reader.events) == 3
    second = cache.index_for_rank(NOW + timedelta(hours=2))
    assert second is first
    assert len(reader.events) == 3
    third = cache.index_for_rank(NOW + timedelta(hours=25))
    assert third is not first
    assert len(reader.events) == 6


def test_customer_evidence_cache_fails_closed_when_refresh_is_denied():
    reader = FakeGovernedReader()
    cache = GovernedAotCopierEvidenceCache(loader=loader(reader))
    cache.index_for_rank(NOW)
    reader.rejected.add("document-1")
    with pytest.raises(PermissionError, match="not approved"):
        cache.index_for_rank(NOW + timedelta(hours=25))
    # Prior identity evidence must not remain usable after failed refresh.
    with pytest.raises(PermissionError, match="not approved"):
        cache.index_for_rank(NOW + timedelta(hours=25))


def test_customer_evidence_cache_rejects_invalid_time_and_ttl():
    reader = FakeGovernedReader()
    with pytest.raises(ValueError, match="TTL"):
        GovernedAotCopierEvidenceCache(loader=loader(reader), max_age_hours=0)
    cache = GovernedAotCopierEvidenceCache(loader=loader(reader))
    with pytest.raises(ValueError, match="timezone"):
        cache.index_for_rank(NOW.replace(tzinfo=None))
    assert reader.events == []



def test_cached_customer_claims_expire_with_document_authorization_not_cache_ttl():
    reader = FakeGovernedReader()
    approved_until = NOW + timedelta(minutes=15)
    cache = GovernedAotCopierEvidenceCache(
        loader=loader(reader), max_age_hours=24,
        authorization_expires_at=approved_until,
    )
    assert cache.index_for_rank(NOW).match(
        serial_number="1G55503749",
    ).status == "verified"
    assert len(reader.events) == 3
    # The local cache would still be fresh, but the underlying authorization
    # is now expired. Do not attempt a network refresh or return old claims.
    with pytest.raises(PermissionError, match="authorization has expired"):
        cache.index_for_rank(approved_until)
    assert cache._snapshot is None
    assert len(reader.events) == 3
    with pytest.raises(PermissionError, match="authorization has expired"):
        cache.index_for_rank(approved_until + timedelta(seconds=1))
    assert len(reader.events) == 3


def test_snapshot_rejects_expired_document_grant_even_when_fresh():
    reader = FakeGovernedReader()
    idx = loader(reader).refresh(now=NOW)
    snapshot = ApprovedAotCopierEvidenceSnapshot(
        index=idx, refreshed_at=NOW, max_age_hours=24,
        authorization_expires_at=NOW + timedelta(minutes=1),
    )
    assert snapshot.usable_at(NOW + timedelta(seconds=40)) is idx
    with pytest.raises(PermissionError, match="authorization has expired"):
        snapshot.usable_at(NOW + timedelta(minutes=1))


def test_cache_rejects_naive_document_authorization_expiration():
    reader = FakeGovernedReader()
    with pytest.raises(ValueError, match="timezone"):
        GovernedAotCopierEvidenceCache(
            loader=loader(reader),
            authorization_expires_at=NOW.replace(tzinfo=None),
        )
