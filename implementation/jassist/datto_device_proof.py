"""Governed Datto RMM device ownership evidence for J-Assist (read-only).

Uses an injected, already-authorized Jason endpoint.device.read capability.
Never issues direct Datto requests or trusts browser/group/user-provided site
ownership assertions. The pinned site UID MUST originate from governed AOT
configuration. Device online/active state and site are re-read every time.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import re
from .device_identifiers import canonical_device_uid, valid_device_uid

_SITE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

class GovernedAotDattoDeviceProof:
    def __init__(self, *, aot_site_uid: str,
                 governed_read: Callable[[str], Mapping]):
        if (not isinstance(aot_site_uid,str)
                or not _SITE.fullmatch(aot_site_uid)
                or aot_site_uid=="00000000-0000-0000-0000-000000000000"
                or not callable(governed_read)):
            raise ValueError("trusted AOT site and governed device read required")
        self._site = aot_site_uid
        self._read = governed_read

    def __call__(self, expected_aot_scope_uid: str, device_uid: str) -> bool:
        # In v1 this configured AOT scope must be the verified Datto site UID.
        if expected_aot_scope_uid != self._site or not valid_device_uid(device_uid):
            return False
        try:
            response=self._read(device_uid)
            if not isinstance(response, Mapping):
                return False
            if (response.get("status")!="succeeded"
                    or response.get("stage")!="completed"
                    or response.get("capability")!="endpoint.device.read"
                    or response.get("provider")!="datto_rmm"):
                return False
            evidence=response.get("evidence")
            if (not isinstance(evidence,Mapping)
                    or evidence.get("provider")!="datto_rmm"
                    or evidence.get("provider_capability")!="datto_rmm.device.get"):
                return False
            record=evidence.get("record")
            if not isinstance(record,Mapping):
                return False
            # Exact bound resource and site, not a match by display name.
            if (canonical_device_uid(record.get("resource_id"))!=device_uid
                    or record.get("site_id")!=self._site
                    or not isinstance(record.get("hostname"),str)
                    or not record["hostname"].strip()
                    or record.get("deleted") is not False
                    or record.get("suspended") is not False
                    or record.get("online") is not True):
                return False
            return True
        except Exception:
            return False
