"""Authenticated J-Assist HTTPS ingress application contract.

This is the server-side transaction engine; no listener or production route
is registered by importing it. A deployment MUST inject a vetted external
content-review readiness check and TLS/ingress attestation. No default
"allow" behavior exists. The Entra JWT is validated by a separately owned
RSA/JWKS verifier, followed by live Entra group + Datto device checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .session_gate import Denied, VerifiedTechnician

@dataclass(frozen=True)
class JAssistApiDenied(Exception):
    code: int
    safe_message: str


class JAssistEvidenceApi:
    def __init__(self, *, authenticate_bearer: Callable[[str],VerifiedTechnician],
                 durable_gate, encrypted_intake,
                 content_review_ready: Callable[[],bool],
                 secure_ingress_ready: Callable[[],bool]):
        if not all(callable(x) for x in (
            authenticate_bearer,content_review_ready,secure_ingress_ready)):
            raise ValueError("verified Entra, DLP and HTTPS availability required")
        if not all(callable(getattr(durable_gate,n,None)) for n in (
            "start","can_start","credential_for","authorize_read","stop")):
            raise ValueError("durable governed session service required")
        if not all(callable(getattr(encrypted_intake,n,None)) for n in (
            "receive","retrieve")):
            raise ValueError("encrypted reviewed screenshot intake required")
        self._authenticate=authenticate_bearer
        self._gate=durable_gate
        self._intake=encrypted_intake
        self._content_ready=content_review_ready
        self._ingress_ready=secure_ingress_ready

    def _ready(self):
        try:
            return self._content_ready() is True and self._ingress_ready() is True
        except Exception:
            return False

    def _principal(self,bearer):
        try:
            principal=self._authenticate(bearer)
            if not isinstance(principal,VerifiedTechnician):
                raise Denied("trusted user unavailable")
            return principal
        except Exception as exc:
            raise JAssistApiDenied(401,"J-Assist technician authentication required") from exc

    def _authorized(self,bearer,device_uid):
        if not self._ready():
            raise JAssistApiDenied(503,"J-Assist reviewed HTTPS receiving is unavailable")
        principal=self._principal(bearer)
        if not self._gate.can_start(trusted_context=principal,device_uid=device_uid):
            raise JAssistApiDenied(403,"J-Assist group or Datto device authorization denied")
        return principal

    @staticmethod
    def _attest(device_uid,status,**additional):
        return {"status":status,"device_uid":device_uid,
                "technician_verified":True,
                "entra_group_verified":True,
                "datto_device_authorized":True,
                "image_review_ready":True,
                "production_ingress":True,
                **additional}

    def readiness(self, *, bearer,device_uid):
        self._authorized(bearer,device_uid)
        return self._attest(device_uid,"ready")

    def create_session(self, *, bearer,device_uid,consent):
        principal=self._authorized(bearer,device_uid)
        try:
            receipt,secret=self._gate.start(
                trusted_context=principal,device_uid=device_uid,consent=consent)
        except Denied as exc:
            raise JAssistApiDenied(403,"J-Assist session creation denied") from exc
        # The internal secret is encrypted at rest by the durable gate and
        # is never returned to Chrome or included in logging.
        return self._attest(device_uid,"authorized",
                            session_id=receipt.session_id,
                            expires_at_ms=int(receipt.expires_at*1000))

    def _current(self, *, bearer,session_id,device_uid):
        principal=self._authorized(bearer,device_uid)
        secret=self._gate.credential_for(session_id)
        if not secret:
            raise JAssistApiDenied(403,"J-Assist session unavailable")
        try:
            self._gate.authorize_read(trusted_context=principal,
                session_id=session_id,token=secret,device_uid=device_uid)
        except Denied as exc:
            raise JAssistApiDenied(403,"J-Assist session no longer authorized") from exc
        return principal,secret

    def validate_session(self, *, bearer,session_id,device_uid):
        self._current(bearer=bearer,session_id=session_id,device_uid=device_uid)
        return self._attest(device_uid,"authorized",session_id=session_id)

    def accept_image(self, *, bearer,session_id,device_uid,
                     nonce,image,sha256):
        principal,secret=self._current(
            bearer=bearer,session_id=session_id,device_uid=device_uid)
        try:
            receipt=self._intake.receive(
                trusted_technician=principal,session_id=session_id,
                session_token=secret,device_uid=device_uid,
                request_nonce=nonce,image=image,declared_sha256=sha256)
        except Denied as exc:
            raise JAssistApiDenied(403,"J-Assist image rejected or unauthorized") from exc
        return {"status":"accepted","receipt_id":receipt.receipt_id,
                "session_id":receipt.session_id,
                "device_uid":receipt.device_uid,
                "image_sha256":receipt.image_sha256,
                "analyzed_by_model":False,"production_ingress":True}

    def stop_session(self, *, bearer,session_id,device_uid):
        principal,secret=self._current(
            bearer=bearer,session_id=session_id,device_uid=device_uid)
        try:
            self._gate.stop(trusted_context=principal,
                session_id=session_id,token=secret,device_uid=device_uid)
        except Denied as exc:
            raise JAssistApiDenied(403,"J-Assist session stop rejected") from exc
        return {"status":"closed","session_id":session_id,"device_uid":device_uid}

    @property
    def reviewed_image_intake(self):
        return self._intake

    def server_credential_for(self,session_id):
        return self._gate.credential_for(session_id)
