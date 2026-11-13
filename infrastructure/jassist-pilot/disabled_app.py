"""Fail-closed placeholder for a future authorized J-Assist pilot.

This module does not register the J-Assist evidence API. Even if started,
it only exposes an inactive health check and returns 503 for all other
requests; environment variables cannot activate ingestion.
"""
from __future__ import annotations
import json

_APPROVED_ORIGIN = "chrome-extension://pihjpgplfhmpenlghbcdbgdkadleflfi"

async def app(scope, receive, send):
    if scope.get("type") != "http":
        return
    if scope.get("path") == "/healthz" and scope.get("method") == "GET":
        status = 200
        value = {"service": "jassist-pilot", "state": "inactive", "ingress_ready": False}
    else:
        status = 503
        value = {"status": "unavailable", "message": "J-Assist pilot receiver not authorized"}
    data = json.dumps(value, separators=(",", ":")).encode("utf-8")
    headers = [(b"content-type", b"application/json"),
               (b"cache-control", b"no-store"),
               (b"content-length", str(len(data)).encode("ascii")),
               (b"x-content-type-options", b"nosniff")]
    origins = [v.decode("latin-1") for k,v in scope.get("headers",())
               if k.lower() == b"origin"]
    if origins == [_APPROVED_ORIGIN]:
        headers.extend([(b"access-control-allow-origin", _APPROVED_ORIGIN.encode()),
                        (b"vary", b"Origin")])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": data})
