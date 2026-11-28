"""J-Assist screen-assistance eligibility as a server-managed configuration item.

This is a preproduction adapter contract. The trusted settings service must
approve, audit and publish each policy revision; this module NEVER accepts
a policy from Chrome, a Datto page, an Entra claim, or an unauthenticated API.
No configuration value grants endpoint execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat

_GROUP_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_LEVEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,79}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{7,199}$")
_MAX_SIZE = 4096
_FIELDS = frozenset({
    "schema_version", "revision", "enabled", "access_source",
    "aot_account_uid", "required_security_level", "scope",
    "approval_record",
})


@dataclass(frozen=True)
class JAssistDattoAccessPolicy:
    schema_version: int
    revision: int
    enabled: bool
    access_source: str
    aot_account_uid: str
    required_security_level: str
    scope: str
    approval_record: str

    @classmethod
    def from_mapping(cls, data: object) -> "JAssistDattoAccessPolicy":
        if not isinstance(data, dict) or set(data) != _FIELDS:
            raise ValueError("complete J-Assist access policy is required")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("unsupported access policy schema")
        if type(data["revision"]) is not int or data["revision"] < 1:
            raise ValueError("positive policy revision required")
        if type(data["enabled"]) is not bool:
            raise ValueError("access policy enabled must be a boolean")
        if data["access_source"] != "datto_rmm_assigned_security_level":
            raise ValueError("unsupported eligibility source")
        account = data["aot_account_uid"]
        if not isinstance(account, str) or not account.strip() or len(account) > 128:
            raise ValueError("verified AOT Datto account identifier required")
        level = data["required_security_level"]
        if (not isinstance(level, str) or level != level.strip()
                or not _LEVEL.fullmatch(level)
                or level.casefold() in {"all", "any", "everyone", "user"}):
            raise ValueError("one specific Datto security level required")
        if data["scope"] != "screen_assistance":
            raise ValueError("J-Assist policy cannot grant device operations")
        ref = data["approval_record"]
        if not isinstance(ref, str) or not _REF.fullmatch(ref):
            raise ValueError("auditable approved change record reference required")
        return cls(**data)



@dataclass(frozen=True)
class JAssistEntraAccessPolicy:
    """Approved J-Assist group eligibility, separate from device rights."""
    schema_version: int
    revision: int
    enabled: bool
    access_source: str
    aot_account_uid: str
    entra_group_id: str
    scope: str
    approval_record: str

    @classmethod
    def from_mapping(cls, data: object) -> "JAssistEntraAccessPolicy":
        fields = (_FIELDS - {"required_security_level"}) | {"entra_group_id"}
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError("complete Entra J-Assist access policy required")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("unsupported J-Assist policy schema")
        if type(data["revision"]) is not int or data["revision"] < 1:
            raise ValueError("positive policy revision required")
        if type(data["enabled"]) is not bool:
            raise ValueError("enabled must be an explicit boolean")
        if data["access_source"] != "entra_group":
            raise ValueError("J-Assist eligibility must use a trusted Entra group")
        account = data["aot_account_uid"]
        if (not isinstance(account, str) or not account.strip()
                or len(account) > 128 or account != account.strip()):
            raise ValueError("pinned AOT Datto account required")
        group = data["entra_group_id"]
        if (not isinstance(group, str) or not _GROUP_ID.fullmatch(group)
                or group.lower() == "00000000-0000-0000-0000-000000000000"):
            raise ValueError("approved Entra group object ID required")
        if data["scope"] != "screen_assistance":
            raise ValueError("J-Assist eligibility cannot grant endpoint actions")
        record = data["approval_record"]
        if not isinstance(record, str) or not _REF.fullmatch(record):
            raise ValueError("auditable approval record reference required")
        return cls(**{**data, "entra_group_id": group.lower()})


def _reject_duplicates(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("duplicate configuration field")
        record[key] = value
    return record


class FileBackedJAssistPolicyReader:
    """Reads each revision on demand: changes require no code or redeployment.

    This path must be provided by a trusted server-side settings service, not
    any browser or end user. The settings service governs authorization,
    immutable audit history, revision changes and rollback. A local file's
    approval_record label is not independent evidence of Owner approval.
    """

    def __init__(self, path: str | Path, *,
                 policy_type: type = JAssistDattoAccessPolicy):
        if policy_type not in (JAssistDattoAccessPolicy, JAssistEntraAccessPolicy):
            raise ValueError("unsupported server policy schema")
        self._policy_type = policy_type
        self._path = Path(path)
        if not self._path.is_absolute():
            raise ValueError("trusted absolute settings path required")

    def __call__(self) -> JAssistDattoAccessPolicy | JAssistEntraAccessPolicy:
        info = self._path.lstat()  # deny symlinks; missing file denies
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
            raise ValueError("settings must be a regular, non-writable-by-others file")
        if info.st_size <= 0 or info.st_size > _MAX_SIZE:
            raise ValueError("access policy is empty or oversized")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self._path, flags)
        with os.fdopen(fd, "rb") as stream:
            raw = stream.read(_MAX_SIZE + 1)
            live = os.fstat(stream.fileno())
        if (not stat.S_ISREG(live.st_mode) or live.st_mode & 0o022
                or len(raw) > _MAX_SIZE):
            raise ValueError("invalid access policy storage")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)
        return self._policy_type.from_mapping(data)
