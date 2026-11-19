"""Exact source-bound Windows Time JSON shadow in isolated preproduction.

The existing PMv4 JSON runtime, read-only registry and governed Observe port
are reused. Source-only explicit composition does not join production Core,
schedule a second worker, activate JSON versions or execute remediation.
"""
from __future__ import annotations

from pathlib import Path

from autonomous_remediation.json_shadow_integration import JsonShadowBoundaryError
from .json_playbook_readonly_preprod import build_json_readonly_preprod_candidate
from .json_windows_time_facts import reduce_windows_time_shadow

PLAYBOOK_ID = "windows_time_source"
PLAYBOOK_VERSION = "0.1.0-migration.1"
PLAYBOOK_FINGERPRINT = "b75a183d829f7cb98c4b53a8813919e47ece77698d4fd8d6a5a8ee98ea983b44"
READ_CAPABILITIES = frozenset({
    "management.alert.search",
    "endpoint.device.read",
    "endpoint.alert.history.search",
})


def build_windows_time_json_readonly_preprod(
    *,
    enabled: bool,
    isolated_root: Path,
    client_id: str,
    client_site_binding: str,
    request_factory,
    orchestrator,
    clock,
):
    """Create isolated exact-version read-only Windows Time shadow candidate.

    client_site_binding must be obtained from pre-existing trusted governed
    same-client site inventory; an alert's own site string is NOT a trusted
    permission proof and cannot supply this parameter.
    """
    if not enabled:
        return None
    if not str(client_site_binding or "").strip():
        raise JsonShadowBoundaryError("TIME_SOURCE_EXACT_CLIENT_SITE_BINDING_REQUIRED")
    return build_json_readonly_preprod_candidate(
        enabled=True,
        isolated_root=isolated_root,
        client_id=client_id,
        request_factory=request_factory,
        orchestrator=orchestrator,
        clock=clock,
        playbook_id=PLAYBOOK_ID,
        version=PLAYBOOK_VERSION,
        expected_fingerprint=PLAYBOOK_FINGERPRINT,
        allowed_read_capabilities=READ_CAPABILITIES,
        normalize=lambda capability, result, facts: reduce_windows_time_shadow(
            capability, result, facts, at=clock(),
            expected_site=client_site_binding,
        ),
        state_file_name="isolated-windows-time-json-shadow.sqlite3",
    )
