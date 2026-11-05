from __future__ import annotations

from connectors.core.contracts import ConnectorTransportError
from connectors.microsoft_graph.sharepoint_files import SharePointFileClient


class Tokens:
    def access_token_for_tenant(self, *, microsoft_tenant_id):
        assert microsoft_tenant_id == "tenant"
        return "token"


class Transport:
    def __init__(self):
        self.calls = []
        self.fail_once = False

    def request(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_once:
            self.fail_once = False
            raise ConnectorTransportError("throttled", status_code=429, retry_after_seconds=0)
        if kwargs["method"] == "PATCH":
            return {"id": "file", "name": kwargs["json"]["name"], "parentReference": kwargs["json"]["parentReference"]}
        if kwargs["method"] == "POST":
            return {"id": "folder", "name": kwargs["json"]["name"], "folder": {}}
        if "/children" in kwargs["url"]:
            return {"value": [{"id": "one", "name": "x.pdf", "file": {}}]}
        return {"id": "root", "name": "Bank Checking Accounts Register", "folder": {}}

    def request_bytes(self, **kwargs):
        self.calls.append(kwargs)
        return b"pdf"


def test_sharepoint_move_is_exact_patch_and_has_no_delete_surface():
    transport = Transport()
    client = SharePointFileClient(tokens=Tokens(), transport=transport, sleeper=lambda _: None)
    result = client.move_and_rename(
        tenant_id="tenant", drive_id="drive", item_id="file",
        destination_parent_id="dest", new_name="PNCBank-5842-102026.pdf",
    )
    assert result["id"] == "file"
    call = transport.calls[-1]
    assert call["method"] == "PATCH"
    assert call["json"] == {"name": "PNCBank-5842-102026.pdf", "parentReference": {"id": "dest"}}
    assert not hasattr(client, "delete")


def test_sharepoint_throttle_is_bounded_and_retried():
    transport = Transport()
    transport.fail_once = True
    client = SharePointFileClient(tokens=Tokens(), transport=transport, sleeper=lambda _: None)
    values = client.list_children(tenant_id="tenant", drive_id="drive", item_id="root")
    assert len(values) == 1
    assert len(transport.calls) == 2


def test_sharepoint_path_rejects_parent_escape():
    client = SharePointFileClient(tokens=Tokens(), transport=Transport())
    try:
        client.get_item_by_path(tenant_id="tenant", drive_id="drive", path="A/../B")
    except ValueError as exc:
        assert "invalid" in str(exc)
    else:
        raise AssertionError("expected invalid path")
