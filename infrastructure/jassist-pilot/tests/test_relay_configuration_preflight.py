"""Offline exact-route comparison; synthetic configurations, not live Caddy."""
import copy
import importlib.util
from pathlib import Path
import unittest

MODULE=Path(__file__).resolve().parents[1]/"verify_caddy_adapted.py"
spec=importlib.util.spec_from_file_location("jassist_relay_verify",MODULE)
v=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

class RelayDeltaTests(unittest.TestCase):
    def setUp(self):
        self.baseline={
            "apps":{
              "http":{"servers":{"srvr0":{"routes":[
                 {"match":[{"host":["mcp-jason.teamaot.com"]}],
                  "handle":[{"handler":"subroute","routes":[
                    {"match":[{"path":["/mcp"]}],
                     "handle":[{"handler":"reverse_proxy",
                         "upstreams":[{"dial":"10.87.246.157:8000"}]}]},
                  ]}]},
                 {"match":[{"host":["teams-jason.teamaot.com"]}],
                  "handle":[{"handler":"subroute","routes":[
                    {"match":[{"path":["/api/messages"]}],
                     "handle":[{"handler":"reverse_proxy",
                         "upstreams":[{"dial":"10.87.246.157:3978"}]}]},
                  ]}]}
              ]}}},
              "tls":{"automation":{"policies":[{"issuers":[{"module":"acme"}]}]}}
            }
        }
        self.candidate=copy.deepcopy(self.baseline)
        self.pilot={
            "match":[{"path":["/v1/jassist/*"]}],
            "handle":[{"handler":"subroute","routes":[{
                "handle":[{"handler":"reverse_proxy",
                           "upstreams":[{"dial":"10.87.246.157:3981"}]}]
            }]}]
        }
        self.candidate["apps"]["http"]["servers"]["srvr0"]["routes"][0]["handle"][0]["routes"].append(self.pilot)

    def test_one_exact_mcp_route_does_not_change_any_existing_service(self):
        self.assertTrue(v.verified_single_route_delta(self.baseline,self.candidate))

    def test_changed_teams_mcp_or_tls_settings_rejected(self):
        for group in ("teams","mcp","tls"):
            with self.subTest(group=group):
                changed=copy.deepcopy(self.candidate)
                if group=="teams":
                    changed["apps"]["http"]["servers"]["srvr0"]["routes"][1]["handle"][0]["routes"][0]["handle"][0]["upstreams"][0]["dial"]="127.0.0.1:1"
                elif group=="mcp":
                    changed["apps"]["http"]["servers"]["srvr0"]["routes"][0]["handle"][0]["routes"][0]["handle"][0]["upstreams"][0]["dial"]="127.0.0.1:1"
                else:
                    changed["apps"]["tls"]["automation"]["policies"][0]["issuers"][0]["module"]="internal"
                with self.assertRaises(v.RelayPreflightDenied):
                    v.verified_single_route_delta(self.baseline,changed)

    def test_generated_caddy_group_label_renumbering_preserves_semantics(self):
        baseline=copy.deepcopy(self.baseline)
        candidate=copy.deepcopy(self.candidate)
        original=baseline["apps"]["http"]["servers"]["srvr0"]["routes"]
        updated=candidate["apps"]["http"]["servers"]["srvr0"]["routes"]
        original[0]["group"]="group1"
        original[1]["group"]="group3"
        updated[0]["group"]="group21"
        updated[1]["group"]="group23"
        self.assertTrue(v.verified_single_route_delta(baseline,candidate))
        # Do not accept arbitrary custom group names or structural mutations.
        updated[0]["group"]="custom-authorizer-group"
        with self.assertRaises(v.RelayPreflightDenied):
            v.verified_single_route_delta(baseline,candidate)

    def test_group_aliasing_change_and_order_change_must_fail(self):
        baseline=copy.deepcopy(self.baseline)
        candidate=copy.deepcopy(self.candidate)
        existing=baseline["apps"]["http"]["servers"]["srvr0"]["routes"]
        proposed=candidate["apps"]["http"]["servers"]["srvr0"]["routes"]
        existing[0]["group"]="group0"
        existing[1]["group"]="group0"
        proposed[0]["group"]="group11"
        proposed[1]["group"]="group12"
        with self.assertRaises(v.RelayPreflightDenied):
            v.verified_single_route_delta(baseline,candidate)
        # This is an exact route-order-preservation check, not just a multiset.
        swapped=copy.deepcopy(self.candidate)
        swapped["apps"]["http"]["servers"]["srvr0"]["routes"].reverse()
        with self.assertRaises(v.RelayPreflightDenied):
            v.verified_single_route_delta(self.baseline,swapped)

    def test_wrong_peer_unscoped_route_or_duplicate_pilot_rejected(self):
        changed=copy.deepcopy(self.candidate)
        changed["apps"]["http"]["servers"]["srvr0"]["routes"][0]["handle"][0]["routes"][-1]["handle"][0]["routes"][0]["handle"][0]["upstreams"][0]["dial"]="0.0.0.0:3981"
        with self.assertRaises(v.RelayPreflightDenied):
            v.verified_single_route_delta(self.baseline,changed)
        changed=copy.deepcopy(self.candidate)
        changed["apps"]["http"]["servers"]["srvr0"]["routes"][0]["handle"][0]["routes"].append(copy.deepcopy(self.pilot))
        with self.assertRaises(v.RelayPreflightDenied):
            v.verified_single_route_delta(self.baseline,changed)
        changed=copy.deepcopy(self.candidate)
        route=changed["apps"]["http"]["servers"]["srvr0"]["routes"][0]["handle"][0]["routes"].pop()
        changed["apps"]["http"]["servers"]["srvr0"]["routes"][1]["handle"][0]["routes"].append(route)
        with self.assertRaises(v.RelayPreflightDenied):
            v.verified_single_route_delta(self.baseline,changed)

if __name__=="__main__":
    unittest.main()
