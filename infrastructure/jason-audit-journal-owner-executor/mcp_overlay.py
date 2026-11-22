#!/usr/bin/env python3
"""One additive Owner-audit approval tool on the immutable live MCP base.

DO NOT import the newer whole Main server. Preserve all 37 existing tools,
the exact prior production image, its provider configuration, and service
identities. New scoped tool is disabled without exact separately governed
activation and a fresh Root-staged offer.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

from jason_mcp import server as base

BASE_TOOL_COUNT = 37
BASE_TOOL_NAMES_SHA256 = "6ea28fc61d43096a8def64750ee2d5ad76c92486e6539c1a08660bfdbe037d64"
ADDON_PATH = Path("/opt/jason-src/audit_journal_adoption_approval_overlay.py")
ACTION = "approve_audit_journal_adoption"


def _digest_tools(tools: dict[str, Any]) -> str:
    return hashlib.sha256("\n".join(sorted(tools)).encode()).hexdigest()


def _reviewed_approval_module():
    spec = importlib.util.spec_from_file_location(
        "reviewed_audit_journal_owner_approval", str(ADDON_PATH)
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("AUDIT_MCP_OWNER_APPROVAL_MODULE_NOT_PINNED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def register():
    original = dict(base.mcp._tool_manager._tools)
    if (len(original) != BASE_TOOL_COUNT
            or _digest_tools(original) != BASE_TOOL_NAMES_SHA256
            or ACTION in original):
        raise RuntimeError("AUDIT_MCP_ORIGINAL_TOOL_REGISTRY_MISMATCH")
    approval = _reviewed_approval_module()

    @base.mcp.tool()
    def approve_audit_journal_adoption(
        release_id: str,
        candidate_sha: str,
        scope_sha256: str,
        manifest_sha256: str,
        affirmative_decision: str = "",
    ) -> dict[str, Any]:
        """Owner OAuth-signs ONE Root-preflighted daily audit archive adoption.

        This is an independent licensed-Owner consent record, NOT a provider
        write, Root execution, generic software release or a production reset.
        """
        try:
            if os.getenv("JASON_AUDIT_JOURNAL_OWNER_ISSUER_ENABLED") != "true":
                raise PermissionError("AUDIT_JOURNAL_OWNER_ISSUER_NOT_ACTIVATED")
            principal, organization = base._release_approval_owner()
            token = base.get_access_token()
            if token is None:
                raise PermissionError("AUDIT_JOURNAL_ENTRA_BEARER_REQUIRED")
            signer_path = os.getenv("JASON_OWNER_RELEASE_ED25519_KEY_PATH", "").strip()
            if not signer_path.startswith("/"):
                raise PermissionError("AUDIT_JOURNAL_SERVICE_SIGNER_NOT_CONFIGURED")
            from kernel.signed_owner_release import read_service_owner_signing_key
            signer = read_service_owner_signing_key(Path(signer_path))
            return dict(approval.queue_exact_archive_owner_approval(
                state_root=Path("/var/lib/jason/authority/audit-journal-release"),
                release_id=release_id,
                candidate_sha=candidate_sha,
                scope_sha256=scope_sha256,
                manifest_sha256=manifest_sha256,
                approved_by=principal,
                organization_id=organization,
                verified_token_claims=token.claims or {},
                service_signer=signer,
                affirmative_decision=affirmative_decision,
            ))
        except (PermissionError, ValueError, OSError, json.JSONDecodeError) as exc:
            return {"status": "rejected", "error_code": str(exc)}

    current = dict(base.mcp._tool_manager._tools)
    if set(current) != set(original) | {ACTION} or len(current) != BASE_TOOL_COUNT + 1:
        raise RuntimeError("AUDIT_MCP_SCOPE_BROADER_THAN_ONE_TOOL")
    for name, original_tool in original.items():
        if current[name] is not original_tool:
            raise RuntimeError("AUDIT_MCP_EXISTING_TOOL_CHANGED")
    return approve_audit_journal_adoption


def main():
    register()
    base.main()


if __name__ == "__main__":
    main()
