"""Non-executing provider-neutral transport capability descriptors.

Registry enumeration is never permission to connect or execute; adapters need
independent reviewed implementation and orchestrator-issued authority.
"""
from __future__ import annotations
from dataclasses import dataclass

KNOWN_TRANSPORTS = frozenset({'datto_webremote', 'ssh', 'winrm', 'companion'})
KNOWN_MODES = frozenset({'guided', 'assisted', 'autonomous'})

@dataclass(frozen=True)
class AdapterCapabilities:
    transport_id: str
    target_kind: str
    supported_session_modes: frozenset[str]
    supports_live_input: bool
    supports_output_stream: bool
    supports_cancel: bool
    execution_identity: str
    max_output_bytes: int
    session_expiry_seconds: int
    # An explicit empty identity/target binding is never trusted.

    def __post_init__(self):
        if self.transport_id not in KNOWN_TRANSPORTS or not self.target_kind.strip():
            raise ValueError('unsupported adapter or target type')
        if not self.supported_session_modes or self.supported_session_modes - KNOWN_MODES:
            raise ValueError('unsupported session mode')
        if not self.execution_identity.strip():
            raise ValueError('missing execution identity')
        if type(self.max_output_bytes) is not int or not 0 < self.max_output_bytes <= 1048576:
            raise ValueError('invalid output limit')
        if type(self.session_expiry_seconds) is not int or not 0 < self.session_expiry_seconds <= 3600:
            raise ValueError('invalid session expiry')
        if not all(type(x) is bool for x in
                   (self.supports_live_input, self.supports_output_stream, self.supports_cancel)):
            raise ValueError('invalid capability flag')

class AdapterRegistry:
    """Definition catalog only; no transport handles or execution methods."""
    def __init__(self):
        self._descriptors: dict[str, AdapterCapabilities] = {}

    def register(self, descriptor: AdapterCapabilities):
        if descriptor.transport_id in self._descriptors:
            raise ValueError('duplicate adapter registration')
        self._descriptors[descriptor.transport_id] = descriptor

    def lookup(self, transport_id: str) -> AdapterCapabilities:
        try:
            return self._descriptors[transport_id]
        except KeyError as exc:
            raise ValueError('transport not registered') from exc
