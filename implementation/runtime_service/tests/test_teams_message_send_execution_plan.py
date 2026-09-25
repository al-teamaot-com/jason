from dataclasses import replace
from types import SimpleNamespace

import pytest

from jason_runtime import teams_message_send as module


def _request(**overrides):
    arguments = {
        "aad_object_id": "aad-user-1",
        "tenant_id": "tenant-1",
        "text": "Jason test message",
    }
    arguments.update(overrides)
    return SimpleNamespace(
        capability_name=module.CAPABILITY,
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        arguments=arguments,
    )


def _resolution():
    return SimpleNamespace(selected_provider_id=module.PROVIDER)


def test_teams_prepare_binds_target_and_content_without_sending_or_exposing_token(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token_file.write_text("synthetic-proactive-token")
    invoker = module.TeamsMessageSendInvoker(
        gateway_url="http://gateway.internal:3979",
        token_file=str(token_file),
    )
    calls = []
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: calls.append((args, kwargs)))

    prepared = invoker.prepare_execution_plan(request=_request(), resolution=_resolution())

    assert calls == []
    assert prepared.plan.selected_provider_id == module.PROVIDER
    assert prepared.plan.action_method == "POST"
    assert prepared.plan.resource_identifier == "tenant-1:aad-user-1"
    assert prepared.plan.normalized_path == "/internal/proactive/send"
    assert prepared.plan.normalized_payload["text"] == "Jason test message"
    assert "synthetic-proactive-token" not in repr(prepared)
    assert "gateway.internal" not in repr(prepared.plan.canonical_material())


def test_teams_tampered_target_is_rejected_before_send(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token_file.write_text("synthetic-proactive-token")
    invoker = module.TeamsMessageSendInvoker(
        gateway_url="http://gateway.internal:3979",
        token_file=str(token_file),
    )
    send_calls = []
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: send_calls.append((args, kwargs)))
    prepared = invoker.prepare_execution_plan(request=_request(), resolution=_resolution())
    tampered = replace(
        prepared,
        plan=replace(prepared.plan, resource_identifier="tenant-1:other-user"),
    )

    with pytest.raises(PermissionError, match="target changed"):
        invoker.invoke_execution_plan(
            request=_request(),
            resolution=_resolution(),
            prepared=tampered,
        )

    assert send_calls == []


def test_teams_exact_prepared_plan_sends_once(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token_file.write_text("synthetic-proactive-token")
    invoker = module.TeamsMessageSendInvoker(
        gateway_url="http://gateway.internal:3979",
        token_file=str(token_file),
    )

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return b'{"status":"succeeded","message_id":"message-1","conversation_id":"conversation-1","bootstrap_created":true}'

    calls = []
    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        return Response()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    prepared = invoker.prepare_execution_plan(request=_request(), resolution=_resolution())
    result = invoker.invoke_execution_plan(
        request=_request(), resolution=_resolution(), prepared=prepared
    )

    assert len(calls) == 1
    assert result.output["message_id"] == "message-1"
    assert result.output["conversation_id"] == "conversation-1"
    assert result.output["bootstrap_created"] is True
