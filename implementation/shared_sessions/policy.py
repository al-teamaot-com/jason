"""Fail-closed shared-session admission. No transport or command execution exists here.

The JSON file is read on *every* evaluation so policy changes require no rebuild
or application restart. This module is not an authority issuer: external signed
identity, target binding, and governed capability grants must already be verified.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

ALLOWED_MODES = frozenset({"guided", "assisted", "autonomous"})
ALLOWED_TRANSPORTS = frozenset({"datto_webremote", "ssh", "winrm", "companion"})
ALLOWED_CLASSIFICATIONS = frozenset({"read_only", "sensitive", "mutating", "uncertain"})

@dataclass(frozen=True)
class SessionRequest:
    tenant_id: str
    client_id: str
    target_id: str
    technician_id: str
    ticket_id: str
    transport: str
    mode: str
    classification: str
    governed_grant_valid: bool = False
    identity_verified: bool = False
    target_binding_verified: bool = False
    execution_transport_approved: bool = False
    separate_sensitive_grant: bool = False
    specific_change_approval: bool = False

@dataclass(frozen=True)
class SessionDecision:
    allowed: bool
    reason: str
    configuration_version: str

class SessionPolicy:
    def __init__(self, config_path: str | Path):
        self.path = Path(config_path)

    def _load(self) -> dict[str, Any]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported shared-session configuration")
        if not isinstance(data.get("enabled"), bool):
            raise ValueError("enabled must be boolean")
        if not isinstance(data.get("transports"), dict):
            raise ValueError("transports must be an object")
        if not isinstance(data.get("modes"), dict):
            raise ValueError("modes must be an object")
        if set(data["transports"]) - ALLOWED_TRANSPORTS or set(data["modes"]) - ALLOWED_MODES:
            raise ValueError("unknown transport or mode")
        if any(type(v) is not bool for v in (*data["transports"].values(), *data["modes"].values())):
            raise ValueError("transport and mode settings must be boolean")
        return data

    def decide(self, req: SessionRequest) -> SessionDecision:
        # Invalid policy cannot inadvertently widen authority.
        try:
            c = self._load()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return SessionDecision(False, "configuration_unavailable_or_invalid", "unknown")
        version = str(c.get("configuration_version", "unversioned"))
        def deny(reason: str) -> SessionDecision:
            return SessionDecision(False, reason, version)
        if not c["enabled"]:
            return deny("feature_disabled")
        context = (req.tenant_id, req.client_id, req.target_id, req.technician_id, req.ticket_id)
        if any(type(value) is not str or not value.strip() for value in context):
            return deny("invalid_authoritative_context")
        attestation_fields = (req.governed_grant_valid, req.identity_verified,
                              req.target_binding_verified, req.execution_transport_approved,
                              req.separate_sensitive_grant, req.specific_change_approval)
        if any(type(flag) is not bool for flag in attestation_fields):
            return deny("invalid_authorization_attestation")
        if not all((req.tenant_id, req.client_id, req.target_id, req.technician_id, req.ticket_id)):
            return deny("incomplete_authoritative_context")
        if not (req.identity_verified and req.target_binding_verified and req.governed_grant_valid):
            return deny("identity_target_or_grant_unverified")
        if any(type(value) is not str for value in (req.transport, req.mode, req.classification)):
            return deny("invalid_request_type")
        if req.transport not in ALLOWED_TRANSPORTS or not c["transports"].get(req.transport, False):
            return deny("transport_not_enabled")
        if not req.execution_transport_approved:
            return deny("transport_not_approved")
        if req.mode not in ALLOWED_MODES or not c["modes"].get(req.mode, False):
            return deny("mode_not_enabled")
        if req.classification not in ALLOWED_CLASSIFICATIONS:
            return deny("invalid_classification")
        if req.classification == "uncertain":
            return deny("uncertain_command")
        if req.classification == "sensitive" and not req.separate_sensitive_grant:
            return deny("sensitive_grant_required")
        if req.classification == "mutating" and not req.specific_change_approval:
            return deny("specific_change_approval_required")
        # Still only session admission: never a permission to execute a command.
        return SessionDecision(True, "session_admission_only", version)
