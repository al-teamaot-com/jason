from __future__ import annotations

import hmac
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID


_ALLOWED_OPERATIONS = frozenset(
    {
        "message_trace.search",
        "message_trace.detail",
        "mailbox.forwarding.read",
        "mailbox.inbox_rules.read_hidden",
        "mailbox.full_access.read",
        "mailbox.send_as.read",
        "mailbox.send_on_behalf.read",
        "mailbox.transport_rules.read",
        "mailbox.mobile_devices.read",
        "mailbox.retention_audit_config.read",
    }
)
_MAX_BODY = 64 * 1024


def _read_secret(path_env: str) -> str:
    path = os.environ.get(path_env, "").strip()
    if not path:
        raise RuntimeError(f"{path_env} is not configured")
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"{path_env} is empty")
    return value


def _error(code: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code}


def _validate_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("request must be an object")

    allowed_keys = {
        "tenant_id",
        "organization",
        "operation",
        "arguments",
        "correlation_id",
    }
    if set(value) - allowed_keys:
        raise ValueError("request contains unsupported fields")

    tenant_id = str(value.get("tenant_id") or "").strip()
    UUID(tenant_id)

    organization = str(value.get("organization") or "").strip().casefold()
    if (
        not organization.endswith(".onmicrosoft.com")
        or "@" in organization
        or "/" in organization
        or "\\" in organization
        or len(organization) > 253
    ):
        raise ValueError("organization is invalid")

    operation = str(value.get("operation") or "").strip()
    if operation not in _ALLOWED_OPERATIONS:
        raise ValueError("operation is not allowlisted")

    arguments = value.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")

    correlation_id = str(value.get("correlation_id") or "").strip()
    if not correlation_id or len(correlation_id) > 200:
        raise ValueError("correlation_id is invalid")

    return {
        "tenant_id": tenant_id,
        "organization": organization,
        "operation": operation,
        "arguments": arguments,
        "correlation_id": correlation_id,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "JasonExchangeReadWorker/1.0"

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"ok": True})
            return
        self._json(404, _error("NOT_FOUND"))

    def do_POST(self) -> None:
        if self.path != "/v1/read":
            self._json(404, _error("NOT_FOUND"))
            return

        expected = _read_secret("JASON_EXCHANGE_WORKER_TOKEN_FILE")
        supplied = self.headers.get("Authorization", "")
        wanted = f"Bearer {expected}"
        if not hmac.compare_digest(supplied, wanted):
            self._json(401, _error("WORKER_AUTHORIZATION_DENIED"))
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, _error("INVALID_CONTENT_LENGTH"))
            return
        if length < 1 or length > _MAX_BODY:
            self._json(413, _error("REQUEST_SIZE_INVALID"))
            return

        try:
            payload = json.loads(self.rfile.read(length))
            request = _validate_request(payload)
        except (ValueError, json.JSONDecodeError):
            self._json(400, _error("REQUEST_INVALID"))
            return

        try:
            completed = subprocess.run(
                [
                    "pwsh",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    "/app/invoke_exchange_read.ps1",
                ],
                input=json.dumps(request, separators=(",", ":")),
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self._json(504, _error("EXCHANGE_OPERATION_TIMEOUT"))
            return

        if completed.returncode != 0:
            self._json(502, _error("EXCHANGE_WORKER_PROCESS_FAILED"))
            return

        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError:
            self._json(502, _error("EXCHANGE_WORKER_RESPONSE_INVALID"))
            return

        if not isinstance(result, dict):
            self._json(502, _error("EXCHANGE_WORKER_RESPONSE_INVALID"))
            return

        self._json(200 if result.get("ok") is True else 502, result)


def main() -> None:
    host = os.environ.get("JASON_EXCHANGE_WORKER_HOST", "0.0.0.0")
    port = int(os.environ.get("JASON_EXCHANGE_WORKER_PORT", "8091"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
