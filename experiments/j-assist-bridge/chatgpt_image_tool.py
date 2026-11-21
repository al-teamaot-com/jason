"""Preproduction ChatGPT MCP-facing approved image read contract.

No registered production MCP tool and no model inference. A trusted Jason
MCP authentication adapter supplies the verified principal; the model may
only select opaque identifiers. Images and credentials never leave the
authorized SessionGate except as reviewed image bytes for the MCP renderer.
"""
from __future__ import annotations

import base64
from typing import Callable

from screen_evidence_intake import ScreenEvidenceIntake
from session_gate import Denied, VerifiedTechnician


class ChatGPTImageEvidenceTool:
    """Exact, server-held credential and native-permission-bound image lookup."""

    def __init__(
        self,
        *,
        intake: ScreenEvidenceIntake,
        credential_lookup: Callable[[str], str | None],
    ):
        self._intake = intake
        self._credential_lookup = credential_lookup

    def read_reviewed_image(
        self, *,
        authenticated_technician: VerifiedTechnician,
        session_id: str,
        device_uid: str,
        receipt_id: str,
    ) -> dict:
        if not isinstance(authenticated_technician, VerifiedTechnician):
            raise Denied("trusted MCP identity required")
        if not isinstance(session_id, str) or not 12 <= len(session_id) <= 128:
            raise Denied("invalid session selector")
        if not isinstance(device_uid, str) or not 1 <= len(device_uid) <= 24:
            raise Denied("invalid device selector")
        if not isinstance(receipt_id, str) or not 12 <= len(receipt_id) <= 128:
            raise Denied("invalid receipt selector")
        credential = self._credential_lookup(session_id)
        if not isinstance(credential, str) or not credential:
            raise Denied("server session credential unavailable")
        receipt, frame = self._intake.retrieve(
            trusted_technician=authenticated_technician,
            session_id=session_id,
            session_token=credential,
            device_uid=device_uid,
            receipt_id=receipt_id,
        )
        # No text extraction claim: this is actual reviewed image content,
        # not a screen description, terminal transcript, or rendered answer.
        if frame.startswith(bytes.fromhex("89504e470d0a1a0a")):
            mime = "image/png"
        elif frame.startswith(bytes.fromhex("ffd8ff")):
            mime = "image/jpeg"
        else:
            raise Denied("unsupported reviewed evidence")
        return {
            "session_id": receipt.session_id,
            "device_uid": receipt.device_uid,
            "receipt_id": receipt.receipt_id,
            "image_sha256": receipt.image_sha256,
            "image": {"type": "image", "mimeType": mime,
                      "data": base64.b64encode(frame).decode("ascii")},
            "image_reviewed": True,
            "analyzed_by_model": False,
            "inference_billing": "none",
            "production_connected": False,
        }
