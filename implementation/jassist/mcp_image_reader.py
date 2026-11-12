"""Reviewed J-Assist image read adapter for the existing Jason MCP identity.

No model may supply a principal or session secret. The authenticated MCP
JWT -> active Jason identity binding is resolved by the existing MCP
server, and encrypted readback rechecks current Entra group and Datto
device ownership. Output is MCP ImageContent-compatible metadata only.
The MCP server must explicitly register it behind approved release flags.
"""
from __future__ import annotations

from typing import Callable

from .chatgpt_image_tool import ChatGPTImageEvidenceTool
from .mcp_identity_adapter import JasonMcpTechnicianIdentity
from .session_gate import Denied


class JAssistMcpImageReader:
    def __init__(self, *, reviewed_image_tool: ChatGPTImageEvidenceTool,
                 resolve_authenticated_mcp_identity: Callable[[],tuple],
                 image_read_enabled: Callable[[],bool]):
        if (not isinstance(reviewed_image_tool,ChatGPTImageEvidenceTool)
                or not callable(resolve_authenticated_mcp_identity)
                or not callable(image_read_enabled)):
            raise ValueError("bound Jason MCP reader and release gate required")
        self._tool=reviewed_image_tool
        self._identity=JasonMcpTechnicianIdentity(
            resolve_authenticated_mcp_identity)
        self._ready=image_read_enabled

    def read(self, *, session_id: str,device_uid: str,
             receipt_id: str) -> dict:
        try:
            if self._ready() is not True:
                raise Denied("J-Assist MCP image retrieval is not approved")
            principal=self._identity.current()
            evidence=self._tool.read_reviewed_image(
                authenticated_technician=principal,session_id=session_id,
                device_uid=device_uid,receipt_id=receipt_id)
            if (evidence["image"]["type"]!="image"
                    or evidence["image"]["mimeType"] not in (
                        "image/png","image/jpeg")
                    or not evidence.get("image_reviewed")
                    or evidence.get("analyzed_by_model") is not False):
                raise Denied("reviewed J-Assist evidence unavailable")
            return {
                "status":"succeeded",
                "receipt_id":evidence["receipt_id"],
                "device_uid":evidence["device_uid"],
                "session_id":evidence["session_id"],
                "image_sha256":evidence["image_sha256"],
                "content":[
                    {"type":"text",
                     "text":"Reviewed J-Assist evidence received. No automatic analysis or device command executed."},
                    evidence["image"],
                ],
            }
        except Denied:
            raise
        except Exception as exc:
            raise Denied("J-Assist MCP evidence retrieval denied") from exc
