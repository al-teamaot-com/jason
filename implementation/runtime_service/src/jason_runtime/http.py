from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class TeamsConversationIngress(Protocol):
    def handle(self, envelope: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: Mapping[str, Any]

    def encoded(self) -> bytes:
        return json.dumps(
            dict(self.body),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class RuntimeHttpApplication:
    """Small internal HTTP boundary around Jason's governed conversation ingress.

    This layer performs transport framing only. It does not bind human identity,
    select capabilities/providers, grant authority, resolve secrets, or execute
    connectors. Those decisions remain inside the governed Jason ingress/flow.
    """

    ingress: TeamsConversationIngress
    max_body_bytes: int = 64 * 1024
    conversation_path: str = "/v1/openclaw/teams/conversation"

    def dispatch(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> HttpResponse:
        verb = method.upper().strip()
        request_path = path.split("?", 1)[0]

        if verb == "GET" and request_path == "/healthz":
            return HttpResponse(
                200,
                {
                    "status": "ok",
                    "component": "jason-runtime",
                    "authority": "central-orchestrator",
                },
            )

        if request_path != self.conversation_path:
            return HttpResponse(404, {"status": "rejected", "error_code": "not_found"})
        if verb != "POST":
            return HttpResponse(
                405,
                {"status": "rejected", "error_code": "method_not_allowed"},
            )

        content_type = self._header(headers, "content-type").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return HttpResponse(
                415,
                {"status": "rejected", "error_code": "unsupported_media_type"},
            )
        if not body:
            return HttpResponse(400, {"status": "rejected", "error_code": "empty_body"})
        if len(body) > self.max_body_bytes:
            return HttpResponse(
                413,
                {"status": "rejected", "error_code": "request_too_large"},
            )

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return HttpResponse(
                400,
                {"status": "rejected", "error_code": "invalid_json"},
            )
        if not isinstance(payload, Mapping):
            return HttpResponse(
                400,
                {"status": "rejected", "error_code": "json_object_required"},
            )

        # Application-layer Ed25519 authentication, replay checks, Teams identity
        # evidence validation and all Jason governance occur inside ingress.handle().
        result = dict(self.ingress.handle(payload))
        return HttpResponse(self._http_status(result), result)

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str:
        wanted = name.lower()
        for key, value in headers.items():
            if str(key).lower() == wanted:
                return str(value)
        return ""

    @staticmethod
    def _http_status(result: Mapping[str, Any]) -> int:
        status = str(result.get("status", "")).strip()
        error_code = str(result.get("error_code", "")).strip()
        if status == "completed":
            return 200
        if status == "duplicate":
            return 200
        if status == "approval_required":
            return 202
        if status == "denied":
            return 403
        if status == "failed":
            return 500
        if status == "rejected":
            if error_code == "transport_authentication_failed":
                return 401
            if error_code == "replay_detected":
                return 409
            return 400
        # Unknown ingress result shapes fail closed and are not reflected as success.
        return 500
