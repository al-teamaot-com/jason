from __future__ import annotations
from dataclasses import replace
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from session_gate import VerifiedTechnician
from datto_technician_authority import DattoWebRemoteAuthorizer, DattoWebRemoteEvidence

class DattoTechnicianAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.person=VerifiedTechnician("staff-a","aot")
        self.proof=DattoWebRemoteEvidence(
            user_subject="staff-a",tenant_id="aot",device_uid="1717088",
            issued_at=1000.0,active_security_level="AOT technician",
            device_visible=True,sites_view=True,devices_view=True,
            web_remote_enabled=True,provider_verified=True,
        )
        self.current=self.proof
        self.auth=DattoWebRemoteAuthorizer(
            evidence_for=lambda person,device:self.current,
            clock=lambda:1010.0,
        )
    def test_authorized_fresh_provider_evidence(self):
        self.assertTrue(self.auth(self.person,"1717088"))
    def test_wrong_person_tenant_device_or_missing_active_level(self):
        for change in (
            {"user_subject":"staff-b"},{"tenant_id":"other"},
            {"device_uid":"9"},{"active_security_level":""},
        ):
            with self.subTest(change=change):
                self.current=replace(self.proof,**change)
                self.assertFalse(self.auth(self.person,"1717088"))
    def test_all_individual_permission_flags_mandatory(self):
        for field in ("device_visible","sites_view","devices_view","web_remote_enabled","provider_verified"):
            with self.subTest(flag=field):
                self.current=replace(self.proof,**{field:False})
                self.assertFalse(self.auth(self.person,"1717088"))
    def test_expired_and_future_evidence_denied(self):
        for moment in (979.0,1020.0):
            with self.subTest(moment=moment):
                self.current=replace(self.proof,issued_at=moment)
                self.assertFalse(self.auth(self.person,"1717088"))
    def test_unavailable_adapter_denied(self):
        denied=DattoWebRemoteAuthorizer(evidence_for=lambda person,device:None)
        self.assertFalse(denied(self.person,"1717088"))
    def test_device_id_validation(self):
        self.assertFalse(self.auth(self.person,"1717088/"))
        self.assertFalse(self.auth(self.person,"invalid"))
    def test_wrong_identity_type_denied(self):
        self.assertFalse(self.auth(("staff-a","aot"),"1717088"))
if __name__=="__main__":unittest.main()
