from __future__ import annotations
from dataclasses import replace
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from datto_administrator_authority import (
    DattoAdministratorEvidence, DattoAdministratorScreenAuthorizer,
)
from session_gate import VerifiedTechnician
from jassist_access_policy import JAssistDattoAccessPolicy


class DattoAdministratorAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.person=VerifiedTechnician("aot-entra-technician-oid", "aot")
        self.proof=DattoAdministratorEvidence(
            technician_subject=self.person.subject,
            technician_tenant=self.person.tenant_id,
            account_uid="aot-native-datto-account",
            datto_username="aot.tech@example.test",
            assigned_security_levels=("Administrator",),
            assignment_verified=True,
            user_enabled=True,
            provider_verified=True,
            verified_at=1000.0,
        )
        self.policy=JAssistDattoAccessPolicy.from_mapping({
            "schema_version": 1, "revision": 1, "enabled": True,
            "access_source": "datto_rmm_assigned_security_level",
            "aot_account_uid": self.proof.account_uid,
            "required_security_level": "Administrator",
            "scope": "screen_assistance", "approval_record": "AOT-JASSIST-20261111",
        })
        self.current=self.proof
        self.owned={"1717088"}
        self.auth=DattoAdministratorScreenAuthorizer(
            aot_account_uid=self.proof.account_uid,
            access_policy_for=lambda:self.policy,
            evidence_for=lambda person:self.current,
            device_in_account=lambda account, device:device in self.owned,
            clock=lambda:1010.0,
        )

    def test_admin_member_with_fresh_provider_evidence_can_share_screen(self):
        self.assertTrue(self.auth(self.person,"1717088"))
        self.assertTrue(self.auth.can_access(self.person,"1717088",surface="screen_assistance"))

    def test_never_bypass_native_endpoint_actions(self):
        for surface in ("powershell","webremote","component_execute","reboot","send"):
            with self.subTest(surface=surface):
                self.assertFalse(self.auth.can_access(self.person,"1717088",surface=surface))

    def test_nonmember_disabled_user_missing_provider_proof_rejected(self):
        for change in (
            {"assignment_verified":False},
            {"user_enabled":False},
            {"provider_verified":False},
            {"assigned_security_levels":("Technician",)},
            {"assigned_security_levels":("Administrators",)},
            {"datto_username":""},
            {"datto_username":" "},
        ):
            with self.subTest(change=change):
                self.current=replace(self.proof,**change)
                self.assertFalse(self.auth(self.person,"1717088"))

    def test_identity_account_mismatch_denied(self):
        for change in (
            {"technician_subject":"other"},
            {"technician_tenant":"unrelated"},
            {"account_uid":"another-msp"},
        ):
            with self.subTest(change=change):
                self.current=replace(self.proof,**change)
                self.assertFalse(self.auth(self.person,"1717088"))
        self.current=self.proof
        self.assertFalse(self.auth(VerifiedTechnician("different","aot"),"1717088"))
        self.assertFalse(self.auth(("aot-entra-technician-oid","aot"),"1717088"))

    def test_device_not_in_account_denied_even_admin(self):
        self.assertFalse(self.auth(self.person,"9999"))
        for uid in ("", "../1717088","1717088/x","1"*25):
            with self.subTest(uid=uid):
                self.assertFalse(self.auth(self.person,uid))

    def test_stale_future_and_invalid_clock_denied(self):
        for timestamp in (970.0, 1020.0, float("nan"),float("inf")):
            with self.subTest(timestamp=timestamp):
                self.current=replace(self.proof,verified_at=timestamp)
                self.assertFalse(self.auth(self.person,"1717088"))

    def test_denies_missing_or_broken_membership_source(self):
        self.current=None
        self.assertFalse(self.auth(self.person,"1717088"))
        self.auth=DattoAdministratorScreenAuthorizer(
            aot_account_uid="aot-native-datto-account",
            access_policy_for=lambda:self.policy,
            evidence_for=lambda person:(_ for _ in ()).throw(RuntimeError("Datto unavailable")),
            device_in_account=lambda a,b:True,
        )
        self.assertFalse(self.auth(self.person,"1717088"))

    def test_denies_when_native_device_lookup_unavailable_or_negative(self):
        for result in (False,None,1):
            checker=DattoAdministratorScreenAuthorizer(
                aot_account_uid="aot-native-datto-account",
                access_policy_for=lambda:self.policy,
                evidence_for=lambda person:self.proof,
                device_in_account=lambda a,b:result,
                clock=lambda:1010.0,
            )
            self.assertFalse(checker(self.person,"1717088"))
        checker=DattoAdministratorScreenAuthorizer(
            aot_account_uid="aot-native-datto-account",
            access_policy_for=lambda:self.policy,
            evidence_for=lambda person:self.proof,
            device_in_account=lambda a,b:(_ for _ in ()).throw(RuntimeError("offline")),
            clock=lambda:1010.0,
        )
        self.assertFalse(checker(self.person,"1717088"))

    def test_missing_authoritative_providers_constructor_fail_closed(self):
        for args in (
            {"aot_account_uid":"","access_policy_for":lambda:self.policy,"evidence_for":lambda p:self.proof,"device_in_account":lambda a,b:True},
            {"aot_account_uid":"account","access_policy_for":lambda:self.policy,"evidence_for":None,"device_in_account":lambda a,b:True},
            {"aot_account_uid":"account","access_policy_for":None,"evidence_for":lambda p:self.proof,"device_in_account":lambda a,b:True},
            {"aot_account_uid":"account","access_policy_for":lambda:self.policy,"evidence_for":lambda p:self.proof,"device_in_account":None},
        ):
            with self.subTest(args=args),self.assertRaises(ValueError):
                DattoAdministratorScreenAuthorizer(**args)

    def test_access_level_is_configuration_not_code_and_revocation_is_immediate(self):
        # The same running authorizer reads a changed configuration
        # on its next authorization. Provider assignment still must match.
        self.policy=replace(self.policy,revision=2,required_security_level="Field Technician",
                            approval_record="AOT-JASSIST-20261111-B")
        self.assertFalse(self.auth(self.person,"1717088"))
        self.current=replace(self.proof,assigned_security_levels=("Field Technician",))
        self.assertTrue(self.auth(self.person,"1717088"))
        self.policy=replace(self.policy,revision=3,required_security_level="Administrator",
                            approval_record="AOT-JASSIST-20261111-C")
        self.assertFalse(self.auth(self.person,"1717088"))
        self.current=replace(self.proof,assigned_security_levels=("Administrator","Field Technician"))
        self.assertTrue(self.auth(self.person,"1717088"))

    def test_disabled_cross_account_or_invalid_configuration_fails_closed(self):
        for changed in (
            {"enabled":False}, {"aot_account_uid":"other-account"},
            {"access_source":"browser_supplied"}, {"scope":"powershell"},
            {"approval_record":""}, {"required_security_level":"*"},
        ):
            with self.subTest(changed=changed):
                self.policy=replace(JAssistDattoAccessPolicy.from_mapping({
                    "schema_version":1,"revision":1,"enabled":True,
                    "access_source":"datto_rmm_assigned_security_level",
                    "aot_account_uid":self.proof.account_uid,
                    "required_security_level":"Administrator",
                    "scope":"screen_assistance",
                    "approval_record":"AOT-JASSIST-20261111",
                }),**changed)
                self.assertFalse(self.auth(self.person,"1717088"))

    def test_policy_reader_failure_rejects_without_native_provider_calls(self):
        invoked=[]
        auth=DattoAdministratorScreenAuthorizer(
            aot_account_uid=self.proof.account_uid,
            access_policy_for=lambda:(_ for _ in ()).throw(OSError("config unavailable")),
            evidence_for=lambda p:invoked.append(p) or self.proof,
            device_in_account=lambda a,b:True,
        )
        self.assertFalse(auth(self.person,"1717088"))
        self.assertEqual(invoked,[])



if __name__ == "__main__":
    unittest.main()
