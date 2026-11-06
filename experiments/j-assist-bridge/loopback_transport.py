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
from screen_evidence_intake import ScreenEvidenceIntake, MAX_IMAGE_BYTES

MAX_HTTP_BODY = 2048


def make_handler(
    probe: SyntheticProbe,
    authenticate: Callable[[str], object | None],
    image_intake: ScreenEvidenceIntake | None = None,
):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path == "/v1/test-image":
                self._test_image()
                return
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

        def _test_image(self):
            # Explicitly isolated test-only ingress; no default reviewer
            # and no external listener. Production must use real OAuth/TLS.
            if image_intake is None:
                self.send_error(404)
                return
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or len(auth) > 512:
                self.send_error(401)
                return
            principal = authenticate(auth[7:])
            if principal is None:
                self.send_error(401)
                return
            if self.headers.get("Content-Type") != "image/png":
                self.send_error(415)
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                self.send_error(400)
                return
            if length < 1 or length > MAX_IMAGE_BYTES:
                self.send_error(413)
                return
            try:
                receipt = image_intake.receive(
                    trusted_technician=principal,
                    session_id=self.headers.get("X-JAssist-Session", ""),
                    session_token=self.headers.get("X-JAssist-Session-Token", ""),
                    device_uid=self.headers.get("X-JAssist-Device", ""),
                    request_nonce=self.headers.get("X-JAssist-Nonce", ""),
                    image=self.rfile.read(length),
                    declared_sha256=self.headers.get("X-JAssist-SHA256", ""),
                )
            except (Denied, ValueError, TypeError):
                self.send_error(403)
                return
            body = json.dumps({
                "status": "accepted-for-test",
                "receipt_id": receipt.receipt_id,
                "session_id": receipt.session_id,
                "device_uid": receipt.device_uid,
                "image_sha256": receipt.image_sha256,
                "analyzed_by_model": False,
                "production_ingress": False,
            }, separators=(",", ":")).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            # Never log auth headers, tokens, or payloads.
            return

    return Handler


def create_loopback_server(*, probe: SyntheticProbe, authenticate: Callable[[str], object | None], image_intake: ScreenEvidenceIntake | None = None):
    """No default credential adapter. Refuse all externally reachable hosts."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(probe, authenticate, image_intake))
    assert server.server_address[0] == "127.0.0.1"
    return server
