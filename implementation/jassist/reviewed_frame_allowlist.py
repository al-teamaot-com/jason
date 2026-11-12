"""Strict nonproduction positive-only screenshot review policy.

Accepts ONLY an exact byte-identical image whose SHA256 has already been
independently reviewed and approved in a tightly scoped signed/attested
pilot manifest. This is an exact-frame content gate, NOT generic DLP, and
cannot authorize arbitrary live remote-desktop screenshots. Any missing
or changed approval, file permission failure, or unknown hash denies.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import re
import stat
from typing import Callable

from .screen_evidence_intake import AcceptedScreen, ScreenEvidenceIntake

_SHA = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[A-Za-z0-9._:-]{12,160}$")


class AttestedPilotFrameReview:
    def __init__(self, *, policy_path: Path,
                 verify_current_manifest: Callable[[str], bool]):
        if (not isinstance(policy_path, Path) or not policy_path.is_absolute()
                or not callable(verify_current_manifest)):
            raise ValueError("trusted, attested review policy required")
        self._path = policy_path
        self._attest = verify_current_manifest

    def _approved(self):
        info = self._path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise PermissionError("review manifest must be mode 0600")
        parent = self._path.parent.stat()
        if parent.st_mode & 0o022:
            raise PermissionError("review manifest directory is not protected")
        raw = self._path.read_bytes()
        if len(raw) > 4096:
            raise PermissionError("oversized review manifest")
        digest = hashlib.sha256(raw).hexdigest()
        if self._attest(digest) is not True:
            raise PermissionError("review manifest has no independent approval")
        def distinct_pairs(pairs):
            result = {}
            for name, value in pairs:
                if name in result:
                    raise ValueError("ambiguous reviewed image policy")
                result[name] = value
            return result
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=distinct_pairs)
        if (not isinstance(data, dict)
                or set(data) != {"schema_version","enabled","policy_version",
                                 "reviewer_id","approved_sha256"}
                or data["schema_version"] != 1
                or data["enabled"] is not True
                or not isinstance(data["policy_version"], str)
                or not _REF.fullmatch(data["policy_version"])
                or not isinstance(data["reviewer_id"], str)
                or not _REF.fullmatch(data["reviewer_id"])
                or not isinstance(data["approved_sha256"], list)
                or not 1 <= len(data["approved_sha256"]) <= 8
                or len(set(data["approved_sha256"])) != len(data["approved_sha256"])
                or any(not isinstance(x, str) or not _SHA.fullmatch(x)
                       for x in data["approved_sha256"])):
            raise PermissionError("invalid exact-image review policy")
        return data

    def ready(self) -> bool:
        try:
            self._approved()
            return True
        except Exception:
            return False

    def __call__(self, raw: bytes):
        if type(raw) is not bytes:
            raise PermissionError("invalid screenshot")
        ScreenEvidenceIntake._format(raw)
        approved = self._approved()
        sha = hashlib.sha256(raw).hexdigest()
        if not any(hmac.compare_digest(sha, key)
                   for key in approved["approved_sha256"]):
            raise PermissionError("screenshot has not been independently reviewed")
        return AcceptedScreen(
            raw, approved["reviewer_id"], approved["policy_version"]
        )
