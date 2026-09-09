from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Type

from .http import RuntimeHttpApplication


class JasonRuntimeHttpServer(HTTPServer):
    """Single-worker internal HTTP server.

    The current durable JKD-001 and ingress audit stores intentionally retain SQLite
    connections on their owning runtime objects. Serial request handling preserves
    that ownership model and avoids silently making those connections cross-thread.
    Scale-out must introduce an explicit concurrency-safe state layer first.
    """

    allow_reuse_address = True

    def __init__(self, server_address, application: RuntimeHttpApplication):
        self.application = application
        super().__init__(server_address, _handler_type(application))


def _handler_type(application: RuntimeHttpApplication) -> Type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "JasonRuntime/0.1"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch(b"")

        def do_POST(self) -> None:  # noqa: N802
            raw_length = self.headers.get("Content-Length", "")
            try:
                length = int(raw_length)
            except ValueError:
                self._send(400, b'{"error_code":"invalid_content_length","status":"rejected"}')
                return
            if length < 0:
                self._send(400, b'{"error_code":"invalid_content_length","status":"rejected"}')
                return
            if length > application.max_body_bytes:
                self._send(413, b'{"error_code":"request_too_large","status":"rejected"}')
                return
            self._dispatch(self.rfile.read(length))

        def _dispatch(self, body: bytes) -> None:
            response = application.dispatch(
                method=self.command,
                path=self.path,
                headers={key: value for key, value in self.headers.items()},
                body=body,
            )
            self._send(response.status_code, response.encoded())

        def _send(self, status_code: int, body: bytes) -> None:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            # Never log request bodies, authorization material, signatures, or Teams
            # message text at the HTTP framing layer. Audit belongs to Jason ingress.
            return

    return Handler


def serve(
    application: RuntimeHttpApplication,
    *,
    host: str = "0.0.0.0",
    port: int = 8080,
) -> None:
    if not (0 < port < 65536):
        raise ValueError("runtime port is invalid")
    with JasonRuntimeHttpServer((host, port), application) as server:
        server.serve_forever()
