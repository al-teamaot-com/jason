"""Optional, exact-release J-Assist MCP/HTTPS activation adapter.

The integration owner calls activate only after independently verifying
production release exact SHA, Owner approval and every runtime dependency.
No activation occurs on import. Missing authority or dependency fails closed;
no unreviewed environment-variable-only activation path exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from .mcp_image_reader import JAssistMcpImageReader
from .runtime_wiring import JAssistRunningComponents

_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class JAssistReleaseAttestation:
    candidate_sha: str
    deployed_sha: str
    reviewed_scope_sha256: str
    owner_approval_receipt: str
    protected_main_verified: bool
    runtime_health_verified: bool
    safe_review_enabled: bool

    def validate(self):
        if (not all(isinstance(x,str) and _SHA.fullmatch(x)
                    for x in (self.candidate_sha,self.deployed_sha))
                or self.candidate_sha!=self.deployed_sha
                or not isinstance(self.reviewed_scope_sha256,str)
                or not re.fullmatch(r"[0-9a-f]{64}",self.reviewed_scope_sha256)
                or not isinstance(self.owner_approval_receipt,str)
                or not self.owner_approval_receipt.strip()
                or self.protected_main_verified is not True
                or self.runtime_health_verified is not True
                or self.safe_review_enabled is not True):
            raise PermissionError("verified exact-release attestation required")


def activate_jassist(*, app, register_mcp_tool: Callable,
                     components: JAssistRunningComponents,
                     authenticated_mcp_identity: Callable,
                     attest: JAssistReleaseAttestation,
                     enabled_by_governed_configuration: Callable[[],bool],
                     image_read_enabled: Callable[[],bool]):
    """Register a read-only MCP image tool and a narrow HTTPS intake mount.

    app is the existing Jason MCP Starlette application.
    register_mcp_tool is the existing MCP .tool() decorator.
    Both operations occur only under authenticated exact-release evidence.
    Caller must ensure current identity bindings and TLS boundaries.
    """
    attest.validate()
    if (not isinstance(components,JAssistRunningComponents)
            or not callable(register_mcp_tool)
            or not callable(authenticated_mcp_identity)
            or not callable(enabled_by_governed_configuration)
            or not callable(image_read_enabled)
            or not callable(getattr(app,"mount",None))):
        raise ValueError("reviewed production MCP application dependencies required")
    if enabled_by_governed_configuration() is not True:
        raise PermissionError("J-Assist is not approved for active ingress")
    reader=JAssistMcpImageReader(
        reviewed_image_tool=components.mcp_image_tool,
        resolve_authenticated_mcp_identity=authenticated_mcp_identity,
        image_read_enabled=image_read_enabled)

    def read_jassist_reviewed_image(*, session_id:str,
                                    device_uid:str,receipt_id:str):
        """Read same-tech, policy-reviewed image evidence without execution."""
        return reader.read(
            session_id=session_id,device_uid=device_uid,receipt_id=receipt_id)
    # MCP server must apply normal OAuth and authority policy to this tool.
    # Adapter cannot self-authorize a registration or forge its evidence.
    register_mcp_tool(read_jassist_reviewed_image)
    app.mount("/v1/jassist",components.gateway,name="jassist-reviewed-evidence")
    return {
        "registered":True,
        "candidate_sha":attest.candidate_sha,
        "tool":"read_jassist_reviewed_image",
        "image_ingress":"/v1/jassist",
        "production_read_only_tool":True,
    }
