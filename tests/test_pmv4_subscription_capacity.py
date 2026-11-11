"""Offline, fail-closed tests for PMv4 subscription-only capacity handling."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pmv4_subscription_capacity import assess_subscription_route, quota_hold_for_native_task
from pmv4_workboard_reconciliation import native_task_terminal_evidence

MODEL_STATUS = {
    "defaultModel": "openai/gpt-5.6-sol",
    "allowed": ["openai/gpt-5.6-sol"],
    "fallbacks": [],
    "auth": {
        "runtimeAuthRoutes": [{
            "provider": "openai", "runtime": "codex", "authProvider": "openai",
            "status": "usable", "effective": {"kind": "profiles"},
        }],
        "providers": [{
            "provider": "openai",
            "profiles": {"count": 1, "oauth": 1, "token": 0, "apiKey": 0},
        }],
        "unusableProfiles": [],
        "missingProvidersInUse": [],
    },
}
RUN = "d9acf396-ffb7-4256-a098-2e47ca70b576"
CARD = {
    "runId": RUN,
    "sessionKey": "agent:j-dev:subagent:fdb04810-d8e2-47c3-a15e-992e2fa08b30",
    "agentId": "j-dev",
}
TASK = {
    "taskId": "native-ledger-task-id",
    "runtime": "subagent",
    "sourceId": RUN, "runId": RUN,
    "childSessionKey": CARD["sessionKey"], "agentId": CARD["agentId"],
    "status": "failed",
    "startedAt": int(datetime(2026, 11, 11, 18, 10, tzinfo=timezone.utc).timestamp() * 1000),
    "endedAt": int(datetime(2026, 11, 11, 18, 20, tzinfo=timezone.utc).timestamp() * 1000),
    "error": "FailoverError: You've reached your Codex subscription usage limit. Next reset in 4 hours, Nov 11 at 4:24 PM EST. Wait until the reset time.",
}


class SubscriptionRouteTests(unittest.TestCase):
    def test_observed_oauth_subscription_route_does_not_imply_api_billing(self):
        before = copy.deepcopy(MODEL_STATUS)
        decision = assess_subscription_route(MODEL_STATUS)
        self.assertEqual(decision["status"], "SUBSCRIPTION_OAUTH")
        self.assertFalse(decision["metered_fallback_permitted"])
        self.assertFalse(decision["subscription_capacity_verified"])
        self.assertEqual(MODEL_STATUS, before)

    def test_api_key_route_is_never_accepted(self):
        for mutation in ("api_key", "token", "runtime", "provider", "fallback",
                         "missing_oauth", "other_provider", "bad_profile_count",
                         "other_model", "missing_auth", "unusable"):
            with self.subTest(mutation=mutation):
                data = copy.deepcopy(MODEL_STATUS)
                if mutation == "api_key":
                    data["auth"]["providers"][0]["profiles"]["apiKey"] = 1
                elif mutation == "token":
                    data["auth"]["providers"][0]["profiles"]["token"] = 1
                elif mutation == "runtime":
                    data["auth"]["runtimeAuthRoutes"][0]["runtime"] = "api"
                elif mutation == "provider":
                    data["auth"]["runtimeAuthRoutes"][0]["provider"] = "anthropic"
                elif mutation == "fallback":
                    data["fallbacks"] = ["anthropic/paid"]
                elif mutation == "missing_oauth":
                    data["auth"]["providers"][0]["profiles"]["oauth"] = 0
                elif mutation == "other_provider":
                    data["auth"]["providers"].append({"provider": "anthropic"})
                elif mutation == "bad_profile_count":
                    data["auth"]["providers"][0]["profiles"]["count"] = 2
                elif mutation == "other_model":
                    data["allowed"].append("anthropic/paid")
                elif mutation == "missing_auth":
                    del data["auth"]
                elif mutation == "unusable":
                    data["auth"]["unusableProfiles"] = ["broken"]
                decision = assess_subscription_route(data)
                self.assertEqual(decision["status"], "HOLD")
                self.assertFalse(decision["metered_fallback_permitted"])


class NativeQuotaTests(unittest.TestCase):
    def test_realistic_subscription_limit_is_a_hold_with_only_a_time_hint(self):
        before = copy.deepcopy(TASK)
        hold = quota_hold_for_native_task(TASK)
        self.assertIsNotNone(hold)
        self.assertEqual(hold["disposition"], "HOLD")
        self.assertEqual(hold["reason"], "subscription_capacity_exhausted")
        self.assertEqual(hold["next_capacity_recheck_hint"], "2026-11-11T16:24:00-05:00")
        for key in ("automatic_replay_authorized", "provider_action_authorized",
                    "subscription_capacity_verified"):
            self.assertFalse(hold[key])
        self.assertTrue(hold["requires_existing_workboard_pmv3_reconciliation"])
        self.assertEqual(TASK, before)

    def test_no_confusion_with_api_billing_or_ordinary_rate_limit(self):
        for value in ("API insufficient_quota", "HTTP 429 Rate limit exceeded",
                      "credit_balance_exhausted", "Authentication expired"):
            with self.subTest(value=value):
                self.assertIsNone(quota_hold_for_native_task({**TASK, "error": value}))
        self.assertIsNone(quota_hold_for_native_task({**TASK, "status": "succeeded"}))
        self.assertIsNone(quota_hold_for_native_task({**TASK, "error": None}))

    def test_bad_reset_hint_still_holds_without_scheduling(self):
        for value in ("Next reset someday", "Next reset in 4 hours, Nov 11 at 4:24 PM EDT"):
            modified = {**TASK, "error": "Codex subscription usage limit. " + value}
            hold = quota_hold_for_native_task(modified)
            self.assertEqual(hold["disposition"], "HOLD")
            self.assertIsNone(hold["next_capacity_recheck_hint"])

    def test_native_identity_must_match_before_quota_observation(self):
        matching = native_task_terminal_evidence(CARD, TASK)
        self.assertEqual(matching["disposition"], "HOLD")
        self.assertEqual(matching["reason"], "subscription_capacity_exhausted")
        self.assertTrue(matching["native_termination_confirmed"])
        self.assertEqual(matching["native_task_id"], "native-ledger-task-id")
        self.assertFalse(matching["automatic_replay_authorized"])
        for changed in ({**TASK, "runId": "wrong"},
                        {**TASK, "childSessionKey": "agent:j-dev:other"},
                        {**TASK, "endedAt": None}):
            result = native_task_terminal_evidence(CARD, changed)
            self.assertEqual(result["disposition"], "HOLD")
            self.assertNotEqual(result["reason"], "subscription_capacity_exhausted")


if __name__ == "__main__":
    unittest.main()


class LedgerDedupTests(unittest.TestCase):
    def test_native_cli_and_subagent_views_are_one_run(self):
        from pmv4_subscription_capacity import unique_subscription_quota_runs
        records = [TASK, {**TASK, "runtime": "cli", "taskId": "another-native-task"}]
        got = unique_subscription_quota_runs(records)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["native_record_count"], 2)
        self.assertFalse(got[0]["automatic_replay_authorized"])

    def test_never_construct_replay_queue_from_untrusted_or_successful_records(self):
        from pmv4_subscription_capacity import unique_subscription_quota_runs
        self.assertEqual(unique_subscription_quota_runs({}), [])
        self.assertEqual(unique_subscription_quota_runs([None, {}, {"status": "succeeded"}, {**TASK, "runId": None}]), [])


class CapacityProbeTests(unittest.TestCase):
    def test_rate_limit_probe_matches_observed_openclaw_reply(self):
        from pmv4_subscription_capacity import assess_live_subscription_capacity
        live = copy.deepcopy(MODEL_STATUS)
        live["auth"]["probes"] = {"results": [{
            "provider": "openai", "model": "openai/gpt-5.6-sol",
            "source": "profile", "mode": "oauth", "status": "rate_limit",
            "profileId": "openai:user@example.com",
        }]}
        result = assess_live_subscription_capacity(live)
        self.assertEqual(result["status"], "WAIT_QUOTA_RESET")
        self.assertFalse(result["subscription_capacity_verified"])
        self.assertFalse(result["automatic_replay_authorized"])

    def test_valid_success_is_only_a_probe_not_work_authority(self):
        from pmv4_subscription_capacity import assess_live_subscription_capacity
        live = copy.deepcopy(MODEL_STATUS)
        live["auth"]["probes"] = {"results": [{
            "provider": "openai", "model": "openai/gpt-5.6-sol",
            "source": "profile", "mode": "oauth", "status": "ok",
            "profileId": "openai:user@example.com",
        }]}
        result = assess_live_subscription_capacity(live)
        self.assertEqual(result["status"], "CAPACITY_PROBE_SUCCEEDED")
        self.assertTrue(result["subscription_capacity_verified"])
        self.assertFalse(result["automatic_replay_authorized"])
        live["auth"]["providers"][0]["profiles"]["apiKey"] = 1
        self.assertEqual(assess_live_subscription_capacity(live)["status"], "HOLD_UNVERIFIED")

    def test_unbound_or_untrusted_probe_never_authorizes_capacity(self):
        from pmv4_subscription_capacity import assess_live_subscription_capacity
        for bad in (None, {}, "bad", [], {"auth": {"probes": {"results": []}}}):
            with self.subTest(bad=bad):
                self.assertEqual(assess_live_subscription_capacity(bad)["status"], "HOLD_UNVERIFIED")
