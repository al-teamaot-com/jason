"""Verified AWS Caddy -> ZeroTier J-Assist HTTPS ingress adapter.

The existing TLS terminator talks to an isolated HTTP container over
ZeroTier. Never trust arbitrary X-Forwarded-Proto or Host headers. Uvicorn
MUST run with proxy-header rewriting DISABLED, so scope.client is the
actual TCP peer. Only the pinned relay's ZeroTier IP can assert HTTPS.
The external relay route and host firewall require independent approval.
"""
from __future__ import annotations

import json

from .jassist_asgi_gateway import JAssistASGIGateway

AOT_JASON_PUBLIC_HOST = "mcp-jason.teamaot.com"
AOT_RELAY_ZEROTIER_PEER = "10.87.246.16"
_LOOPBACK = frozenset(("127.0.0.1", "::1"))


class TrustedCaddyJAssistIngress:
    def __init__(self, *, gateway: JAssistASGIGateway,
                 relay_peer: str=AOT_RELAY_ZEROTIER_PEER,
                 host: str=AOT_JASON_PUBLIC_HOST):
        if (not isinstance(gateway, JAssistASGIGateway)
                or relay_peer != AOT_RELAY_ZEROTIER_PEER
                or host != AOT_JASON_PUBLIC_HOST):
            raise ValueError("only the verified AOT relay and MCP host may proxy")
        self._gateway = gateway
        self._peer = relay_peer
        self._host = host

    @staticmethod
    async def _deny(send, status=403):
        data = json.dumps({"status":"error",
                "message":"J-Assist trusted ingress unavailable"}).encode()
        await send({"type":"http.response.start","status":status,
                    "headers":[(b"content-type",b"application/json"),
                               (b"cache-control",b"no-store"),
                               (b"content-length",str(len(data)).encode())]})
        await send({"type":"http.response.body","body":data})

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return
        client = scope.get("client")
        remote = client[0] if isinstance(client,(tuple,list)) and client else ""
        path = scope.get("path","")
        if path == "/healthz" and scope.get("method")=="GET":
            # A health check is not an image readiness check. Do not serve
            # any evidence, claims or credentials from this route.
            data=b'{"service":"jassist-pilot","state":"isolated","upload_authorized":false}'
            await send({"type":"http.response.start","status":200,
                "headers":[(b"content-type",b"application/json"),
                           (b"cache-control",b"no-store"),
                           (b"content-length",str(len(data)).encode())]})
            await send({"type":"http.response.body","body":data})
            return
        if remote != self._peer or scope.get("scheme")!="http":
            await self._deny(send)
            return
        headers={}
        for rawkey,rawvalue in scope.get("headers",()):
            try:
                key=rawkey.decode("ascii").lower()
                val=rawvalue.decode("ascii")
            except Exception:
                await self._deny(send)
                return
            if key in headers:
                await self._deny(send)
                return
            headers[key]=val
        if (headers.get("host") != self._host
                or headers.get("x-forwarded-proto") != "https"
                or headers.get("x-forwarded-host", self._host) != self._host):
            await self._deny(send)
            return
        authorized_scope=dict(scope)
        authorized_scope["scheme"]="https"
        await self._gateway(authorized_scope,receive,send)
