"""Disabled-by-default local PowerShell probe engine for a disposable lab host.

Not a network service or supported execution authority. This engine MUST NOT be
used in production. Its caller must authenticate and authorize out-of-band and
provide a validated, one-time grant through the verifier interface.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import socket
import subprocess
from typing import Protocol

from .command_catalog import get_reviewed_command
from .grants import GrantScope

CLAW2_DATTO_UID = '13eda165-08e0-ec79-026a-985b37e2eb9e'

class GrantVerifier(Protocol):
    def consume(self, token: str, expected_scope: GrantScope) -> bool: ...

@dataclass(frozen=True)
class ProbeOutcome:
    attempted: bool
    completed: bool
    reason: str
    stdout: str = ''
    stderr: str = ''
    exit_code: int | None = None

class Claw2LocalProbe:
    def __init__(self, *, grant_verifier: GrantVerifier, expected_hostname: str = 'claw2-pc',
                 enabled: bool = False, pwsh_path: str = '/usr/bin/pwsh'):
        self.verifier = grant_verifier
        self.expected_hostname = expected_hostname
        self.enabled = enabled
        self.pwsh_path = pwsh_path

    def execute_reviewed_test(self, *, scope: GrantScope, token: str, command_id: str) -> ProbeOutcome:
        # Constitutional safe floor: source defaults disabled; never execute from
        # control host, another device, or without exact single-use scope.
        if self.enabled is not True:
            return ProbeOutcome(False, False, 'laboratory_execution_disabled')
        if (socket.gethostname().casefold() != self.expected_hostname.casefold() or
            self.expected_hostname.casefold() != 'claw2-pc' or
            scope.target_id != CLAW2_DATTO_UID):
            return ProbeOutcome(False, False, 'wrong_target')
        if scope.transport_id != 'companion' or not all((scope.tenant_id, scope.client_id,
                         scope.technician_id, scope.ticket_id)):
            return ProbeOutcome(False, False, 'invalid_scope')
        try:
            cmd = get_reviewed_command(command_id)
        except ValueError:
            return ProbeOutcome(False, False, 'unreviewed_command')
        if scope.command_digest != cmd.digest:
            return ProbeOutcome(False, False, 'command_digest_mismatch')
        if Path(self.pwsh_path).as_posix() != '/usr/bin/pwsh':
            return ProbeOutcome(False, False, 'unreviewed_powershell_path')
        if not self.verifier.consume(token,scope):
            return ProbeOutcome(False, False, 'grant_denied_or_replayed')
        try:
            # No shell=True, no user fragments, no script path from caller.
            completed = subprocess.run(
                ['/usr/bin/pwsh','-NoLogo','-NoProfile','-NonInteractive','-Command',cmd.script],
                capture_output=True, timeout=cmd.max_runtime_seconds, check=False)
        except FileNotFoundError:
            return ProbeOutcome(True,False,'powershell_not_installed')
        except subprocess.TimeoutExpired:
            return ProbeOutcome(True,False,'command_timeout')
        except OSError:
            return ProbeOutcome(True,False,'execution_io_error')
        if len(completed.stdout)>cmd.max_output_bytes or len(completed.stderr)>cmd.max_output_bytes:
            return ProbeOutcome(True,False,'output_limit_exceeded')
        out=completed.stdout.decode('utf-8','replace')
        err=completed.stderr.decode('utf-8','replace')
        return ProbeOutcome(True,completed.returncode==0,'success' if completed.returncode==0 else 'nonzero_exit',
                            out,err,completed.returncode)
