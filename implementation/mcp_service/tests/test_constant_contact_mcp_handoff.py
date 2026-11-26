"""MCP handoff honors authenticated Entra identity and never makes a POST."""
from types import SimpleNamespace

from jason_mcp import server


class FakeWorkflow:
    def __init__(self):
        self.calls = []

    def preview_attachment(self, **kwargs):
        self.calls.append(("preview", kwargs))
        return {"status": "preview_unapproved", "work_id": "work-test"}

    def submit_approval(self, **kwargs):
        self.calls.append(("request_approval", kwargs))
        return {"status": "awaiting_approval", "approval_id": "planapproval-123"}

    def readback(self, **kwargs):
        self.calls.append(("readback", kwargs))
        return {"status": "pending_or_unknown"}


def test_mcp_preview_and_approval_route_through_verified_identity(monkeypatch):
    flow = FakeWorkflow()
    monkeypatch.setattr(server, "_authenticated_microsoft_transport_identity",
                        lambda: ("tenant", "person"))
    monkeypatch.setattr(server, "_constant_contact_import_workflow", lambda: flow)
    result = server.constant_contact_excel_preview(
        workbook_base64="UEsDBA==", source_sha256="a" * 64,
        source_reference="chatgpt:attachment:1", filename="contacts.xlsx",
        list_ids=["11111111-2222-3333-4444-555555555555"],
    )
    assert result["status"] == "preview_unapproved"
    identity = flow.calls[0][1]["identity"]
    assert identity.authentication_assurance == "entra-oauth-bearer"
    assert identity.microsoft_tenant_id == "tenant"
    assert identity.microsoft_object_id == "person"
    assert server.constant_contact_excel_request_approval(work_id="work-test")["status"] == "awaiting_approval"
    assert server.constant_contact_excel_readback(work_id="work-test")["status"] == "pending_or_unknown"
    assert [x[0] for x in flow.calls] == ["preview", "request_approval", "readback"]


def test_mcp_rejects_when_pilot_inactive_without_workbook_echo(monkeypatch):
    monkeypatch.setattr(server, "_authenticated_microsoft_transport_identity",
                        lambda: ("tenant", "person"))
    def disabled():
        raise PermissionError("PILOT_OFF")
    monkeypatch.setattr(server, "_constant_contact_import_workflow", disabled)
    result = server.constant_contact_excel_preview(
        workbook_base64="secret-raw-base64", source_sha256="a" * 64,
        source_reference="chatgpt:attachment:1", filename="contacts.xlsx",
        list_ids=[],
    )
    assert result == {"status": "denied", "error_code": "constant_contact_not_authorized"}
    assert "secret-raw-base64" not in str(result)
