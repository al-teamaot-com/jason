"""Auditable fixed PowerShell read-only diagnostics for Claw2 companion pilot.

This module chooses script text; it never launches PowerShell. User-supplied
script fragments or interpolation are intentionally unsupported.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256

@dataclass(frozen=True)
class ReviewedCommand:
    command_id: str
    script: str
    classification: str
    max_runtime_seconds: int
    max_output_bytes: int

    @property
    def digest(self) -> str:
        return sha256(self.script.encode('utf-8')).hexdigest()

# Fixed, reviewed informational commands. No parameters, injection or writes.
_COMMANDS: dict[str, ReviewedCommand] = {
    'powershell.version': ReviewedCommand('powershell.version',
        '$PSVersionTable.PSVersion.ToString()', 'read_only', 10, 4096),
    'host.identity': ReviewedCommand('host.identity',
        '[System.Environment]::MachineName', 'read_only', 10, 4096),
    'host.os': ReviewedCommand('host.os',
        '[System.Runtime.InteropServices.RuntimeInformation]::OSDescription',
        'read_only', 10, 4096),
    'host.utc': ReviewedCommand('host.utc',
        '[System.DateTime]::UtcNow.ToString("o")', 'read_only', 10, 4096),
}

def get_reviewed_command(command_id: str) -> ReviewedCommand:
    if type(command_id) is not str or command_id not in _COMMANDS:
        raise ValueError('unreviewed command id')
    return _COMMANDS[command_id]
