"""Bounded, exact-origin ASGI gateway for reviewed J-Assist screen intake.

Not registered in MCP production by import. It requires a separately
constructed JAssistEvidenceApi, a TLS-terminated trusted ingress and the
approved Chrome extension ID. It never provides browser access to Jason's
internal session credential, encrypted evidence, or other MCP tools.
"""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import parse_qs

from .jassist_evidence_api import JAssistApiDenied, JAssistEvidenceApi

APPROVED_CHROME_ORIGIN="chrome-extension://pihjpgplfhmpenlghbcdbgdkadleflfi"
_ALLOW_HEADERS="authorization,content-type,x-jassist-session,x-jassist-device,x-jassist-sha256,x-jassist-nonce"
_CONTENT_HEADERS=frozenset(part.strip() for part in _ALLOW_HEADERS.split(","))
_ALLOWED_PATHS=frozenset({
  "/v1/jassist/readiness","/v1/jassist/session",
  "/v1/jassist/session/validate","/v1/jassist/session/stop",
  "/v1/jassist/image",
})
_DEVICE=re.compile(r"^[0-9]{1,24}$")
_SESSION=re.compile(r"^[A-Za-z0-9_-]{12,128}$")
_SHA=re.compile(r"^[0-9a-f]{64}$")
_NONCE=re.compile(r"^[A-Za-z0-9]{16,96}$")
_JSON_LIMIT=2048
_IMAGE_LIMIT=1024*1024


class JAssistASGIGateway:
    def __init__(self, *, api: JAssistEvidenceApi,
                 chrome_origin: str=APPROVED_CHROME_ORIGIN):
        if not isinstance(api,JAssistEvidenceApi):
            raise ValueError("reviewed and governed J-Assist API required")
        if chrome_origin!=APPROVED_CHROME_ORIGIN:
            raise ValueError("exact reviewed Chrome extension ID required")
        self._api=api
        self._origin=chrome_origin

    @staticmethod
    def _headers(scope):
        result={}
        for k,v in scope.get("headers",[]):
            try:
                name=k.decode("ascii").lower()
                value=v.decode("latin1")
            except Exception:
                raise JAssistApiDenied(400,"Malformed request headers")
            if name in result:
                raise JAssistApiDenied(400,"Duplicate request header")
            result[name]=value
        return result

    @staticmethod
    async def _body(receive,max_length):
        output=bytearray()
        while True:
            event=await receive()
            if event["type"]=="http.disconnect":
                raise JAssistApiDenied(400,"Request disconnected")
            if event["type"]!="http.request":
                raise JAssistApiDenied(400,"Unexpected HTTP event")
            chunk=event.get("body",b"")
            if type(chunk) is not bytes or len(output)+len(chunk)>max_length:
                raise JAssistApiDenied(413,"J-Assist request too large")
            output.extend(chunk)
            if not event.get("more_body",False):
                return bytes(output)

    @staticmethod
    def _reject_duplicate_keys(pairs):
        seen={}
        for name,value in pairs:
            if name in seen:
                raise ValueError("ambiguous JSON field")
            seen[name]=value
        return seen

    @staticmethod
    def _json(body,fields):
        try: data=json.loads(body.decode("utf-8"),
                             object_pairs_hook=JAssistASGIGateway._reject_duplicate_keys)
        except Exception as exc:
            raise JAssistApiDenied(400,"Invalid J-Assist JSON") from exc
        if not isinstance(data,dict) or set(data)!=set(fields):
            raise JAssistApiDenied(400,"Unexpected J-Assist JSON fields")
        return data

    @staticmethod
    def _device(value):
        if not isinstance(value,str) or not _DEVICE.fullmatch(value):
            raise JAssistApiDenied(400,"Invalid Datto device")
        return value

    @staticmethod
    def _session(value):
        if not isinstance(value,str) or not _SESSION.fullmatch(value):
            raise JAssistApiDenied(400,"Invalid session reference")
        return value

    @staticmethod
    def _bearer(headers):
        header=headers.get("authorization","")
        if not header.startswith("Bearer ") or not 100<=len(header[7:])<=8192:
            raise JAssistApiDenied(401,"Valid AOT Entra authorization required")
        return header[7:]

    async def _route(self,scope,receive,headers):
        path=scope["path"]
        method=scope["method"]
        bearer=self._bearer(headers)
        if method=="GET" and path=="/v1/jassist/readiness":
            try:
                params=parse_qs(scope.get("query_string",b"").decode("ascii"),
                                strict_parsing=True)
            except Exception as exc:
                raise JAssistApiDenied(400,"Invalid readiness selector") from exc
            if set(params)!={"device_uid"} or len(params["device_uid"])!=1:
                raise JAssistApiDenied(400,"Exact Datto device required")
            data=await asyncio.to_thread(self._api.readiness,
                bearer=bearer,device_uid=self._device(params["device_uid"][0]))
            return 200,data
        if method=="POST" and path in {
            "/v1/jassist/session","/v1/jassist/session/validate",
            "/v1/jassist/session/stop"}:
            if headers.get("content-type")!="application/json":
                raise JAssistApiDenied(415,"J-Assist JSON required")
            payload=self._json(await self._body(receive,_JSON_LIMIT),
                {"device_uid","consent"} if path=="/v1/jassist/session"
                else {"session_id","device_uid"})
            device=self._device(payload["device_uid"])
            if path=="/v1/jassist/session":
                if payload["consent"] is not True:
                    raise JAssistApiDenied(403,"Explicit technician consent required")
                result=await asyncio.to_thread(self._api.create_session,
                    bearer=bearer,device_uid=device,consent=True)
                return 201,result
            session=self._session(payload["session_id"])
            if path=="/v1/jassist/session/validate":
                result=await asyncio.to_thread(self._api.validate_session,
                    bearer=bearer,device_uid=device,session_id=session)
            else:
                result=await asyncio.to_thread(self._api.stop_session,
                    bearer=bearer,device_uid=device,session_id=session)
            return 200,result
        if method=="POST" and path=="/v1/jassist/image":
            if headers.get("content-type")!="image/jpeg":
                raise JAssistApiDenied(415,"JPEG screenshot required")
            if "x-jassist-session-token" in headers:
                raise JAssistApiDenied(403,"Browser cannot transmit session credentials")
            session=self._session(headers.get("x-jassist-session"))
            device=self._device(headers.get("x-jassist-device"))
            declared=headers.get("x-jassist-sha256")
            nonce=headers.get("x-jassist-nonce")
            if (not isinstance(declared,str) or not _SHA.fullmatch(declared)
                    or not isinstance(nonce,str) or not _NONCE.fullmatch(nonce)):
                raise JAssistApiDenied(400,"Invalid screenshot integrity envelope")
            image=await self._body(receive,_IMAGE_LIMIT)
            result=await asyncio.to_thread(self._api.accept_image,
                bearer=bearer,session_id=session,device_uid=device,
                nonce=nonce,image=image,sha256=declared)
            return 201,result
        raise JAssistApiDenied(404,"J-Assist route not found")

    async def __call__(self,scope,receive,send):
        if scope.get("type")!="http":
            return
        path=scope.get("path")
        method=scope.get("method")
        origin=""
        status=404
        payload={"status":"error","message":"J-Assist route not found"}
        allow_origin=False
        try:
            headers=self._headers(scope)
            origin=headers.get("origin","")
            if (path not in _ALLOWED_PATHS
                    or method not in {"GET","POST","OPTIONS"}):
                raise JAssistApiDenied(404,"J-Assist route not found")
            if origin!=self._origin:
                raise JAssistApiDenied(403,"Unapproved J-Assist browser origin")
            allow_origin=True
            if scope.get("scheme")!="https":
                raise JAssistApiDenied(403,"Trusted HTTPS transport required")
            if method=="OPTIONS":
                requested=headers.get("access-control-request-headers","").lower()
                requested_set={x.strip() for x in requested.split(",") if x.strip()}
                if not requested_set.issubset(_CONTENT_HEADERS):
                    raise JAssistApiDenied(403,"Unapproved request headers")
                status,payload=204,None
            else:
                status,payload=await self._route(scope,receive,headers)
        except JAssistApiDenied as exc:
            status,payload=exc.code,{"status":"error","message":exc.safe_message}
        except Exception:
            status,payload=503,{"status":"error","message":"J-Assist service unavailable"}
        data=(b"" if payload is None else
              json.dumps(payload,separators=(",",":")).encode())
        response_headers=[
            (b"content-type",b"application/json"),
            (b"cache-control",b"no-store"),
            (b"content-length",str(len(data)).encode()),
            (b"x-content-type-options",b"nosniff"),
            (b"strict-transport-security",b"max-age=31536000"),
        ]
        if allow_origin:
            response_headers.extend([
                (b"access-control-allow-origin",self._origin.encode()),
                (b"access-control-allow-methods",b"GET, POST, OPTIONS"),
                (b"access-control-allow-headers",_ALLOW_HEADERS.encode()),
                (b"vary",b"Origin"),
            ])
        await send({"type":"http.response.start",
                    "status":status,"headers":response_headers})
        await send({"type":"http.response.body","body":data})
