"""Loopback-only J-Assist synthetic transport proof (never production ingress).

Real HTTP request/response, but ONLY on 127.0.0.1, with injected trusted
identity verification and session authority. No screenshots, no Datto API,
no external listener, no paid inference, no persistent credentials.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from session_gate import Denied
from synthetic_probe import SyntheticProbe

MAX_HTTP_BODY = 2048


def make_handler(
    probe: SyntheticProbe,
    authenticate: Callable[[str], object | None],
):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/v1/synthetic-probe":
                self.send_error(404)
                return
            authorization = self.headers.get("Authorization", "")
            if not authorization.startswith("Bearer ") or len(authorization) > 512:
                self.send_error(401)
                return
            trusted = authenticate(authorization[7:])
            if trusted is None:
                self.send_error(401)
                return
            try:
                content_length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                self.send_error(400)
                return
            if content_length < 1 or content_length > MAX_HTTP_BODY:
                self.send_error(413)
                return
            try:
                envelope = json.loads(self.rfile.read(content_length).decode("utf-8"))
                if not isinstance(envelope, dict) or set(envelope) != {
                    "session_id", "session_token", "device_uid", "probe"
                }:
                    raise Denied("unexpected fields")
                if not isinstance(envelope["probe"], dict):
                    raise Denied("invalid probe")
                raw_probe = json.dumps(envelope["probe"], sort_keys=True, separators=(",", ":")).encode()
                response = probe.exchange(
                    trusted_context=trusted,
                    session_id=envelope["session_id"],
                    token=envelope["session_token"],
                    device_uid=envelope["device_uid"],
                    request=raw_probe,
                )
            except (Denied, ValueError, TypeError, KeyError, UnicodeDecodeError):
                self.send_error(403)
                return
            payload = json.dumps({
                "session_id": response.session_id,
                "sequence": response.sequence,
                "observation": response.observation,
                "evidence_sha256": response.evidence_sha256,
                "synthetic_only": True,
                "screen_analyzed": False,
            }, separators=(",", ":")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            # Never log auth headers, tokens, or payloads.
            return

    return Handler


def create_loopback_server(*, probe: SyntheticProbe, authenticate: Callable[[str], object | None]):
    """No default credential adapter. Refuse all externally reachable hosts."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(probe, authenticate))
    assert server.server_address[0] == "127.0.0.1"
    return server
