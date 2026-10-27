"""P0 release canary must preserve the native authenticated MCP read boundary."""

import json

from jason_mcp import server


CANDIDATE = "a" * 40
BASELINE = "b" * 40
START = "2026-10-27T00:00:00Z"
END = "2026-10-27T11:30:00Z"


class MCPReadFixture:
    def __init__(self):
        self.calls = []

    def __call__(self, *, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        response = {
            "capability": capability, "status": "succeeded", "provider": "autotask",
            "error_code": None, "reason_codes": [],
        }
        if capability == "service.ticket.count":
            data = {"queryCount": 9}
        elif capability == "service.ticket.search":
            offset = arguments.get("after_resource_id", 0)
            ids = [n for n in range(701, 710) if n > offset]
            data = {"items": [{"id": n, "description": "PRIVATE-TICKET-BODY"} for n
                              in ids[:arguments["page_size"]]]}
        elif capability == "service.ticket.read":
            data = {"items": [{"id": arguments["resource_id"],
                               "description": "PRIVATE-TICKET-BODY",
                               "email": "private@example.invalid"}]}
        else:
            raise AssertionError("unexpected provider-read capability")
        response["evidence"] = {"data": data}
        return response


def canary(**changes):
    args = {
        "release_candidate_sha": CANDIDATE,
        "phase": "after", "created_after": START, "created_before": END,
        "page_size": 5,
    }
    args.update(changes)
    return server.verify_release_ticket_read_canary(**args)


def test_one_mcp_call_uses_existing_governed_reads_without_leaking_customer_data(
    monkeypatch,
):
    captured = MCPReadFixture()
    identity_calls = []
    monkeypatch.setenv("JASON_SOURCE_REVISION", CANDIDATE)
    monkeypatch.setattr(
        server, "_authenticated_identity",
        lambda: identity_calls.append("checked") or
        ("person-owner", "aot", "delegated_microsoft_identity", None),
    )
    monkeypatch.setattr(server, "execute_read_capability", captured)

    result = canary()
    assert result["status"] == "succeeded"
    assert result["acceptance_status"] == "PASS"
    assert result["needs_independent_receipt_binding"] is True
    assert result["production_release_approval"] is False
    assert len(identity_calls) == 1
    assert [name for name, _ in captured.calls] == [
        "service.ticket.count", "service.ticket.search",
        "service.ticket.search", "service.ticket.read",
    ]
    assert captured.calls[-1][1] == {"resource_id": 701}
    assert captured.calls[2][1]["after_resource_id"] == 705
    assert result["summary"]["count_verified"] == 9
    assert result["summary"]["pages_verified"] == 2
    assert result["summary"]["running_revision"] == CANDIDATE
    assert result["customer_data_included"] is False
    encoded = json.dumps(result)
    assert "PRIVATE-TICKET-BODY" not in encoded
    assert "private@example.invalid" not in encoded
    assert "701" not in encoded


def test_unauthenticated_requester_is_denied_before_any_provider_call(monkeypatch):
    captured = MCPReadFixture()
    monkeypatch.setenv("JASON_SOURCE_REVISION", CANDIDATE)
    def no_identity():
        raise PermissionError("MCP_AUTHENTICATION_REQUIRED")
    monkeypatch.setattr(server, "_authenticated_identity", no_identity)
    monkeypatch.setattr(server, "execute_read_capability", captured)
    result = canary()
    assert result["status"] == "denied"
    assert result["error_code"] == "MCP_AUTHENTICATED_REQUESTER_REQUIRED"
    assert captured.calls == []


def test_caller_cannot_forge_postrelease_revision(monkeypatch):
    captured = MCPReadFixture()
    monkeypatch.setenv("JASON_SOURCE_REVISION", BASELINE)
    monkeypatch.setattr(
        server, "_authenticated_identity",
        lambda: ("person-owner", "aot", "delegated_microsoft_identity", None),
    )
    monkeypatch.setattr(server, "execute_read_capability", captured)
    result = canary()
    assert result["status"] == "failed"
    assert result["error_code"] == "post_release_revision_mismatch"
    assert captured.calls == []


def test_missing_immutable_runtime_revision_fails_closed(monkeypatch):
    captured = MCPReadFixture()
    monkeypatch.delenv("JASON_SOURCE_REVISION", raising=False)
    monkeypatch.setattr(
        server, "_authenticated_identity",
        lambda: ("person-owner", "aot", "delegated_microsoft_identity", None),
    )
    monkeypatch.setattr(server, "execute_read_capability", captured)
    result = canary()
    assert result["status"] == "failed"
    assert result["error_code"] == "invalid_source_revision"
    assert captured.calls == []


def test_trusted_identity_but_denied_requester_read_fails_not_pass(monkeypatch):
    captured = MCPReadFixture()
    monkeypatch.setenv("JASON_SOURCE_REVISION", CANDIDATE)
    monkeypatch.setattr(
        server, "_authenticated_identity",
        lambda: ("person-owner", "aot", "delegated_microsoft_identity", None),
    )
    def source_denied(*, capability, arguments):
        return {
            "status": "denied", "provider": "autotask",
            "error_code": "INFORMATION_RELEASE_DENIED",
            "reason_codes": ["SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED"],
        }
    monkeypatch.setattr(server, "execute_read_capability", source_denied)
    result = canary()
    assert result["status"] == "failed"
    assert result["error_code"] == "governed_read_not_successful"
    assert result["customer_data_included"] is False
