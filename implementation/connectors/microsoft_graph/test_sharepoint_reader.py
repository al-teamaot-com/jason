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
    result: dict = field(default_factory=lambda: {"value": [{"id": "file-id", "name": "report.pdf"}]})
    calls: list = field(default_factory=list)
    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.result
    def request_bytes(self, **kwargs):
        self.calls.append(kwargs)
        return b"%PDF-1.4"

def test_list_children_binds_tenant_and_uses_graph_get_only():
    tr, tokens = Transport(), Tokens()
    reader = MicrosoftGraphSharePointReader(tokens, tr)
    result = reader.list_children(tenant_id=TENANT, drive_id="drive-id")
    assert tokens.seen == TENANT
    assert result["items"][0]["name"] == "report.pdf"
    assert tr.calls[0]["method"] == "GET"
    assert tr.calls[0]["url"] == "https://graph.microsoft.com/v1.0/drives/drive-id/root/children"

def test_content_is_bounded():
    tr = Transport()
    result = MicrosoftGraphSharePointReader(Tokens(), tr, max_content_bytes=2048).read_bytes(
        tenant_id=TENANT, drive_id="drive-id", item_id="file-id")
    assert result.startswith(b"%PDF")
    assert tr.calls[0]["max_bytes"] == 2048

@pytest.mark.parametrize("bad", ["../etc", "abc/def", "a?x", "a%2fb", ""])
def test_rejects_untrusted_path_selectors(bad):
    tr = Transport()
    with pytest.raises(ValueError):
        MicrosoftGraphSharePointReader(Tokens(), tr).list_children(tenant_id=TENANT, drive_id=bad)
    assert tr.calls == []

def test_rejects_wrong_tenant():
    with pytest.raises(ValueError):
        MicrosoftGraphSharePointReader(Tokens(), Transport()).list_libraries(
            tenant_id="user-provided-name", site_id="site-id")

def test_rejects_id_mismatch():
    tr = Transport(result={"id": "wrong", "name": "private"})
    with pytest.raises(Exception):
        MicrosoftGraphSharePointReader(Tokens(), tr).read_metadata(
            tenant_id=TENANT, drive_id="drive", item_id="correct")

def test_rejects_overfull_collection():
    tr = Transport(result={"value": [{"id":str(i)} for i in range(3)]})
    with pytest.raises(Exception):
        MicrosoftGraphSharePointReader(Tokens(), tr, max_items=2).list_children(
            tenant_id=TENANT, drive_id="drive")

def test_requires_canonical_host():
    with pytest.raises(ValueError):
        MicrosoftGraphSharePointReader(Tokens(), Transport(), base_url="https://evil.invalid")
