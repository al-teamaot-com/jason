from __future__ import annotations
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"implementation"))
from jassist.datto_device_proof import GovernedAotDattoDeviceProof
from jassist.device_identifiers import canonical_device_uid,valid_device_uid

SITE="9bb56523-cade-4ffb-bc34-696e788f0f4c"
GUID="69571572-83f7-1e33-9cdf-01717d4e74a4"
ELSEWHERE="b0000000-0000-4000-8000-000000000002"

class RealShapeDeviceTests(unittest.TestCase):
    def setUp(self):
        self.record={
            "resource_id":GUID, "hostname":"TEST-AOT-WIN11",
            "site_id":SITE,"online":True,"deleted":False,"suspended":False,
        }
        self.response={
            "status":"succeeded","stage":"completed",
            "capability":"endpoint.device.read","provider":"datto_rmm",
            "evidence":{"provider":"datto_rmm",
                        "provider_capability":"datto_rmm.device.get",
                        "record":self.record},
        }
        self.calls=[]
        self.auth=GovernedAotDattoDeviceProof(
            aot_site_uid=SITE,
            governed_read=lambda uid:self.calls.append(uid) or self.response)

    def test_live_datto_native_guid_shape_and_aot_site_match(self):
        self.assertTrue(self.auth(SITE,GUID))
        self.assertEqual(self.calls,[GUID])
        self.assertFalse(self.auth("another-site",GUID))
        self.assertEqual(len(self.calls),1)

    def test_untrusted_device_or_site_proof_deny(self):
        for edit in (
            ("site_id",ELSEWHERE),("resource_id",ELSEWHERE),
            ("online",False),("suspended",True),("deleted",True),
            ("site_id",None),("hostname",""),
            ("online","true"),("suspended",None)
        ):
            with self.subTest(edit=edit):
                bad=copy.deepcopy(self.response)
                bad["evidence"]["record"][edit[0]]=edit[1]
                gate=GovernedAotDattoDeviceProof(
                    aot_site_uid=SITE,governed_read=lambda uid:bad)
                self.assertFalse(gate(SITE,GUID))

    def test_unapproved_or_ambiguous_provider_envelope_deny(self):
        for key,value in (
            ("status","failed"),("provider","other"),
            ("capability","endpoint.device.search"),
            ("stage","queued")
        ):
            with self.subTest(key=key):
                bad={**self.response,key:value}
                gate=GovernedAotDattoDeviceProof(
                    aot_site_uid=SITE,governed_read=lambda uid:bad)
                self.assertFalse(gate(SITE,GUID))
        gate=GovernedAotDattoDeviceProof(
            aot_site_uid=SITE,governed_read=lambda uid:None)
        self.assertFalse(gate(SITE,GUID))

    def test_legacy_decimal_uid_and_native_uuid_are_both_supported(self):
        for uid in (GUID,"1717088"):
            with self.subTest(uid=uid):
                self.assertTrue(valid_device_uid(uid))
                self.assertEqual(canonical_device_uid(uid),uid)
        self.assertEqual(canonical_device_uid(GUID.upper()),GUID)
        for uid in ("","false","0x12345","../../etc/passwd",
                    "00000000-0000-0000-0000-000000000000",
                    "1717088?site=other","1717088/extra","1717088 and 2"):
            with self.subTest(uid=uid):
                self.assertFalse(valid_device_uid(uid))

    def test_provider_fault_fails_closed_without_retry_or_direct_api(self):
        calls=[]
        def failure(uid):
            calls.append(uid)
            raise TimeoutError("Datto read unavailable")
        gate=GovernedAotDattoDeviceProof(
            aot_site_uid=SITE,governed_read=failure)
        self.assertFalse(gate(SITE,GUID))
        self.assertEqual(calls,[GUID])

if __name__=="__main__":
    unittest.main()
