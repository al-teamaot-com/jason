"""Strict, transport-independent companion wire envelope validation.

Parsing only: NO endpoint execution, credentials, or self-issued authority.
All messages require separately authenticated channel and peer identity.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import re

_HEX64 = re.compile(r'^[0-9a-f]{64}$')
_ALLOWED = frozenset({'hello','propose','output','complete','cancel','revoke','heartbeat'})
_REQUIRED = frozenset({'version','kind','tenant_id','client_id','device_uid','session_id',
                       'message_id','sequence','command_digest','payload'})
_MAX_FRAME = 65536

@dataclass(frozen=True)
class CompanionFrame:
    version: int
    kind: str
    tenant_id: str
    client_id: str
    device_uid: str
    session_id: str
    message_id: str
    sequence: int
    command_digest: str
    payload: dict

    @classmethod
    def parse(cls, raw: bytes) -> 'CompanionFrame':
        if not isinstance(raw, bytes) or not 0 < len(raw) <= _MAX_FRAME:
            raise ValueError('invalid frame size')
        try:
            value = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError('malformed frame') from exc
        if type(value) is not dict or set(value) != _REQUIRED:
            raise ValueError('unexpected frame schema')
        if type(value['version']) is not int or value['version'] != 1:
            raise ValueError('unsupported frame version')
        if type(value['kind']) is not str or value['kind'] not in _ALLOWED:
            raise ValueError('invalid kind')
        for name in ('tenant_id','client_id','device_uid','session_id','message_id'):
            v = value[name]
            if type(v) is not str or not v.strip() or len(v) > 128:
                raise ValueError('invalid identity')
        if type(value['sequence']) is not int or value['sequence'] < 1:
            raise ValueError('invalid sequence')
        if type(value['command_digest']) is not str or not _HEX64.fullmatch(value['command_digest']):
            raise ValueError('invalid digest')
        if type(value['payload']) is not dict:
            raise ValueError('invalid payload')
        if 'command' in value['payload'] or 'secret' in value['payload']:
            raise ValueError('raw command or secret in frame prohibited')
        return cls(**value)

    def encode(self) -> bytes:
        value = vars(self)
        raw = json.dumps(value, sort_keys=True, separators=(',',':'),allow_nan=False).encode()
        if len(raw) > _MAX_FRAME:
            raise ValueError('oversized frame')
        return raw

class FrameReplayGuard:
    """Offline test-state sequence checker; durable distributed replay store required."""
    def __init__(self):
        self._latest: dict[tuple[str,str,str],int] = {}
        self._messages: set[tuple[str,str,str]] = set()

    def accept(self, frame: CompanionFrame, *, authenticated_tenant: str,
               authenticated_device: str) -> bool:
        if frame.tenant_id != authenticated_tenant or frame.device_uid != authenticated_device:
            return False
        key = (frame.tenant_id,frame.device_uid,frame.session_id)
        msg = (frame.tenant_id,frame.device_uid,frame.message_id)
        if msg in self._messages or frame.sequence <= self._latest.get(key,0):
            return False
        self._latest[key] = frame.sequence
        self._messages.add(msg)
        return True
