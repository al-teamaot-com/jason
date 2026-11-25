"""Exact isolated preproduction composition for offline-ticket read-only JSON.

No provider writes, note creation, ticket state change or production dispatcher
hook. Source-only builder composes existing JSON draft registry/ObservePort.
"""
from __future__ import annotations

from pathlib import Path

from .json_playbook_readonly_preprod import build_json_readonly_preprod_candidate
from .json_offline_context_facts import reduce_offline_context_shadow

PLAYBOOK_ID = "offline_ticket_context_augmentation"
PLAYBOOK_VERSION = "0.1.0-migration.2"
PLAYBOOK_FINGERPRINT = "feeb7e6e0379487f65906a712d1955d1e7da97769ce6a57aaaa17a91f82dd698"
READ_CAPABILITIES = frozenset({
    "service.ticket.read",
    "service.configuration.read",
    "endpoint.device.read",
    "backup.endpoint.asset.search",
    "endpoint.device.search",
})


def build_offline_context_json_readonly_preprod(
    *,
    enabled: bool,
    isolated_root: Path,
    client_id: str,
    request_factory,
    orchestrator,
    clock,
):
    return build_json_readonly_preprod_candidate(
        enabled=enabled, isolated_root=isolated_root,
        client_id=client_id,
        request_factory=request_factory,
        orchestrator=orchestrator, clock=clock,
        playbook_id=PLAYBOOK_ID,
        version=PLAYBOOK_VERSION,
        expected_fingerprint=PLAYBOOK_FINGERPRINT,
        allowed_read_capabilities=READ_CAPABILITIES,
        normalize=lambda capability, result, facts: reduce_offline_context_shadow(
            capability, result, facts, at=clock()),
        state_file_name="isolated-offline-context-shadow.sqlite3",
    )
