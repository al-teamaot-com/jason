from dataclasses import dataclass, field
from uuid import UUID
import pytest

from connectors.microsoft_graph.sharepoint_reader import MicrosoftGraphSharePointReader

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"

@dataclass
class Tokens:
    seen: str | None = None
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str:
        UUID(microsoft_tenant_id)
        self.seen = microsoft_tenant_id
        return "sample-token"

@dataclass
class Transport:
    result: dict = field(default_factory=lambda: {"value": [{"id": "drive-id", "name": "Docs"}]})
    calls: list = field(default_factory=list)
    def request(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["url"].endswith("/drives"):
            return {"value": [{"id": "drive-id", "name": "Docs"}]}
        if kwargs["url"].endswith("/children"):
            return {"value": [{"id": "file-id", "name": "report.pdf",
                               "parentReference": {"driveId": "drive-id"}}]}
        if kwargs["url"].endswith("/items/file-id"):
            return {"id": "file-id", "name": "report.pdf", "size": 8,
                    "file": {"mimeType": "application/pdf"},
                    "parentReference": {"driveId": "drive-id"}}
        return self.result
    def request_bytes(self, **kwargs):
        self.calls.append(kwargs)
        return b"%PDF-1.4"

def test_list_children_binds_tenant_validates_drive_and_get_only():
    tr, tokens = Transport(), Tokens()
    reader = MicrosoftGraphSharePointReader(tokens, tr)
    result = reader.list_children(tenant_id=TENANT, site_id="site-id", drive_id="drive-id")
    assert tokens.seen == TENANT
    assert result["items"][0]["name"] == "report.pdf"
    assert all(call["method"] == "GET" for call in tr.calls)
    assert tr.calls[0]["url"] == "https://graph.microsoft.com/v1.0/sites/site-id/drives"
    assert tr.calls[1]["url"] == "https://graph.microsoft.com/v1.0/drives/drive-id/root/children"

def test_content_checks_verified_drive_file_and_length():
    tr = Transport()
    result = MicrosoftGraphSharePointReader(Tokens(), tr, max_content_bytes=2048).read_bytes(
        tenant_id=TENANT, site_id="site-id", drive_id="drive-id", item_id="file-id")
    assert result.startswith(b"%PDF")
    assert tr.calls[-1]["max_bytes"] == 2048

@pytest.mark.parametrize("bad", ["../etc", "abc/def", "a?x", "a%2fb", ""])
def test_rejects_untrusted_path_selectors(bad):
    tr = Transport()
    with pytest.raises(ValueError):
        MicrosoftGraphSharePointReader(Tokens(), tr).list_children(
            tenant_id=TENANT, site_id="site-id", drive_id=bad)
    assert tr.calls == []

def test_rejects_wrong_tenant():
    with pytest.raises(ValueError):
        MicrosoftGraphSharePointReader(Tokens(), Transport()).list_libraries(
            tenant_id="user-provided-name", site_id="site-id")

def test_rejects_unapproved_drive_before_item_read():
    tr = Transport()
    with pytest.raises(PermissionError):
        MicrosoftGraphSharePointReader(Tokens(), tr).read_metadata(
            tenant_id=TENANT, site_id="site-id", drive_id="not-in-site", item_id="file-id")
    assert len(tr.calls) == 1

def test_rejects_id_mismatch():
    tr = Transport()
    old = tr.request
    def response(**kwargs):
        if kwargs["url"].endswith("/items/file-id"):
            return {"id": "wrong", "file": {}, "parentReference": {"driveId": "drive-id"}}
        return old(**kwargs)
    tr.request = response
    with pytest.raises(Exception):
        MicrosoftGraphSharePointReader(Tokens(), tr).read_metadata(
            tenant_id=TENANT, site_id="site-id", drive_id="drive-id", item_id="file-id")

def test_rejects_cross_drive_parent():
    tr = Transport()
    old = tr.request
    def response(**kwargs):
        if kwargs["url"].endswith("/items/file-id"):
            return {"id": "file-id", "file": {}, "parentReference": {"driveId": "other"}}
        return old(**kwargs)
    tr.request = response
    with pytest.raises(Exception):
        MicrosoftGraphSharePointReader(Tokens(), tr).read_metadata(
            tenant_id=TENANT, site_id="site-id", drive_id="drive-id", item_id="file-id")

def test_rejects_pagination():
    tr = Transport()
    tr.request = lambda **kw: {"value": [], "@odata.nextLink": "https://graph.microsoft.com"}
    with pytest.raises(Exception):
        MicrosoftGraphSharePointReader(Tokens(), tr).list_libraries(tenant_id=TENANT, site_id="site-id")

def test_rejects_large_file_before_download():
    tr = Transport()
    old = tr.request
    def response(**kwargs):
        if kwargs["url"].endswith("/items/file-id"):
            return {"id": "file-id", "size": 9999,
                    "file": {}, "parentReference": {"driveId": "drive-id"}}
        return old(**kwargs)
    tr.request = response
    with pytest.raises(ValueError):
        MicrosoftGraphSharePointReader(Tokens(), tr, max_content_bytes=8).read_bytes(
            tenant_id=TENANT, site_id="site-id", drive_id="drive-id", item_id="file-id")
    assert not any(c["url"].endswith("/content") for c in tr.calls)

def test_rejects_wrong_download_size():
    tr = Transport()
    tr.request_bytes = lambda **kwargs: b"x"
    with pytest.raises(Exception):
        MicrosoftGraphSharePointReader(Tokens(), tr, max_content_bytes=2048).read_bytes(
            tenant_id=TENANT, site_id="site-id", drive_id="drive-id", item_id="file-id")

def test_requires_canonical_host():
    with pytest.raises(ValueError):
        MicrosoftGraphSharePointReader(Tokens(), Transport(), base_url="https://evil.invalid")


def test_byte_limit_cannot_exceed_underlying_bounded_transport():
    with pytest.raises(ValueError):
        MicrosoftGraphSharePointReader(Tokens(), Transport(), max_content_bytes=16 * 1024 * 1024)
