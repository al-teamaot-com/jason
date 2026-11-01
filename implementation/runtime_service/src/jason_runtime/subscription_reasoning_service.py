from __future__ import annotations

import json
import os
import subprocess
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping


MAX_REQUEST_BYTES = 300_000
MAX_OUTPUT_BYTES = 1_000_000


class SubscriptionReasoningError(RuntimeError):
    def __init__(self, code: str, status: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status = int(status)


class CodexSubscriptionReasoner:
    """Run bounded structured reasoning using a ChatGPT-authenticated Codex CLI."""

    def __init__(
        self,
        *,
        codex_binary: str = "codex",
        timeout_seconds: int = 180,
        model: str = "",
        runner=subprocess.run,
    ) -> None:
        self.codex_binary = codex_binary
        self.timeout_seconds = max(10, int(timeout_seconds))
        self.model = str(model).strip()
        self.runner = runner

    def auth_ready(self) -> bool:
        try:
            result = self.runner(
                [self.codex_binary, "login", "status"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            return int(result.returncode) == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int,
    ) -> Mapping[str, Any]:
        if not self.auth_ready():
            raise SubscriptionReasoningError(
                "subscription_auth_required",
                HTTPStatus.UNAUTHORIZED,
                "ChatGPT subscription authentication is required",
            )
        if not 1 <= int(max_output_tokens) <= 32768:
            raise SubscriptionReasoningError(
                "subscription_invalid_request",
                HTTPStatus.BAD_REQUEST,
                "invalid output budget",
            )
        system_text = str(system)
        user_text = str(user)
        if len(system_text) > 30_000 or len(user_text) > 180_000:
            raise SubscriptionReasoningError(
                "subscription_invalid_request",
                HTTPStatus.BAD_REQUEST,
                "reasoning input exceeds bounded size",
            )
        try:
            schema_text = json.dumps(dict(schema), sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise SubscriptionReasoningError(
                "subscription_invalid_request",
                HTTPStatus.BAD_REQUEST,
                "output schema is not JSON serializable",
            ) from exc
        if len(schema_text) > 120_000:
            raise SubscriptionReasoningError(
                "subscription_invalid_request",
                HTTPStatus.BAD_REQUEST,
                "output schema exceeds bounded size",
            )

        prompt = (
            "SYSTEM INSTRUCTIONS:\n"
            + system_text
            + "\n\nUSER INPUT:\n"
            + user_text
            + "\n\nReturn only the final JSON object matching the supplied output schema. "
              "Do not use shell, filesystem, network, MCP, browser, or other tools. "
              "Do not inspect the local environment. This is a reasoning-only request. "
            + f"Keep the final object within approximately {int(max_output_tokens)} output tokens."
        )

        with tempfile.TemporaryDirectory(prefix="jason-subscription-reasoning-") as temp:
            root = Path(temp)
            schema_path = root / "schema.json"
            output_path = root / "result.json"
            schema_path.write_text(schema_text, encoding="utf-8")
            command = [
                self.codex_binary,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "--color",
                "never",
                "-c",
                'approval_policy="never"',
            ]
            if self.model:
                command.extend(["--model", self.model])
            command.append("-")
            try:
                result = self.runner(
                    command,
                    input=prompt,
                    text=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    cwd=temp,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise SubscriptionReasoningError(
                    "subscription_reasoning_timeout",
                    HTTPStatus.GATEWAY_TIMEOUT,
                    "subscription reasoning timed out",
                ) from exc
            except OSError as exc:
                raise SubscriptionReasoningError(
                    "subscription_reasoning_unavailable",
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "subscription reasoning process unavailable",
                ) from exc

            if int(result.returncode) != 0:
                self._raise_sanitized_failure(str(result.stderr or ""))

            try:
                if not output_path.is_file() or output_path.stat().st_size > MAX_OUTPUT_BYTES:
                    raise ValueError("missing or oversized structured result")
                decoded = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise SubscriptionReasoningError(
                    "subscription_reasoning_invalid_response",
                    HTTPStatus.BAD_GATEWAY,
                    "subscription reasoning returned invalid structured output",
                ) from exc
            if not isinstance(decoded, Mapping):
                raise SubscriptionReasoningError(
                    "subscription_reasoning_invalid_response",
                    HTTPStatus.BAD_GATEWAY,
                    "subscription reasoning result must be a JSON object",
                )
            return dict(decoded)

    @staticmethod
    def _raise_sanitized_failure(stderr: str) -> None:
        text = str(stderr).casefold()
        if any(term in text for term in (
            "not logged in", "login required", "authentication required",
            "please run codex login", "unauthorized",
        )):
            raise SubscriptionReasoningError(
                "subscription_auth_required",
                HTTPStatus.UNAUTHORIZED,
                "ChatGPT subscription authentication is required",
            )
        if any(term in text for term in (
            "usage limit", "limit exceeded", "rate limit", "quota",
        )):
            raise SubscriptionReasoningError(
                "subscription_sharing_usage_limit_exceeded",
                HTTPStatus.TOO_MANY_REQUESTS,
                "ChatGPT subscription usage limit reached",
            )
        raise SubscriptionReasoningError(
            "subscription_reasoning_unavailable",
            HTTPStatus.SERVICE_UNAVAILABLE,
            "subscription reasoning request failed",
        )


def _error_body(code: str, message: str) -> bytes:
    return json.dumps({
        "error": {
            "type": code,
            "code": code,
            "message": message,
        }
    }, separators=(",", ":")).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    reasoner: CodexSubscriptionReasoner

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, payload: bytes) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            payload = json.dumps({
                "status": "ok",
                "subscription_auth_ready": self.reasoner.auth_ready(),
            }, separators=(",", ":")).encode("utf-8")
            self._send(HTTPStatus.OK, payload)
            return
        if self.path == "/readyz":
            ready = self.reasoner.auth_ready()
            payload = json.dumps({
                "status": "ready" if ready else "authentication_required",
            }, separators=(",", ":")).encode("utf-8")
            self._send(HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE, payload)
            return
        self._send(
            HTTPStatus.NOT_FOUND,
            _error_body("not_found", "resource not found"),
        )

    def do_POST(self) -> None:
        if self.path != "/v1/structured-complete":
            self._send(
                HTTPStatus.NOT_FOUND,
                _error_body("not_found", "resource not found"),
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._send(
                HTTPStatus.BAD_REQUEST,
                _error_body("subscription_invalid_request", "invalid request size"),
            )
            return
        try:
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("payload must be object")
            schema = payload.get("schema")
            if not isinstance(schema, Mapping):
                raise ValueError("schema must be object")
            result = self.reasoner.complete(
                system=str(payload.get("system") or ""),
                user=str(payload.get("user") or ""),
                schema=schema,
                max_output_tokens=int(payload.get("max_output_tokens") or 0),
            )
            body = json.dumps({
                "provider": "chatgpt_subscription",
                "result": result,
            }, separators=(",", ":")).encode("utf-8")
            self._send(HTTPStatus.OK, body)
        except SubscriptionReasoningError as exc:
            self._send(exc.status, _error_body(exc.code, str(exc)))
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            self._send(
                HTTPStatus.BAD_REQUEST,
                _error_body("subscription_invalid_request", "invalid request payload"),
            )


def main() -> int:
    host = os.getenv("JASON_SUBSCRIPTION_REASONING_HOST", "0.0.0.0").strip()
    port = int(os.getenv("JASON_SUBSCRIPTION_REASONING_PORT", "8091"))
    reasoner = CodexSubscriptionReasoner(
        codex_binary=os.getenv("JASON_CODEX_BINARY", "codex").strip() or "codex",
        timeout_seconds=int(os.getenv("JASON_SUBSCRIPTION_REASONING_TIMEOUT_SECONDS", "180")),
        model=os.getenv("JASON_CODEX_MODEL", "").strip(),
    )
    Handler.reasoner = reasoner
    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
