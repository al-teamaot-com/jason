#!/usr/bin/env python3
"""PMv4 subscription-only model route and native quota evidence, source-only.

Pure advisory functions. Never load tokens, call providers, schedule tasks,
switch models, update OpenClaw configuration, or replay completed work.
A trusted adapter must independently read native OpenClaw state and the
existing governed Workboard/PMV3 authority before any future resumption.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

_SUBSCRIPTION_LIMIT = (
    "codex subscription usage limit",
    "chatgpt subscription usage limit",
)
_RESET = re.compile(
    r"Next reset in\s+\d+\s+hours?,\s+"
    r"([A-Z][a-z]{2})\s+(\d{1,2})\s+at\s+"
    r"(\d{1,2}):(\d{2})\s+(AM|PM)\s+(EST|EDT)\b",
    re.IGNORECASE,
)
_MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
)}


def assess_subscription_route(status: Mapping[str, Any]) -> dict[str, Any]:
    """Require OpenAI OAuth-backed Codex runtime, never an API-key route.

    This proves configuration shape, not actual subscription billing or
    remaining usage capacity. No secrets are returned.
    """
    result = {"status": "HOLD", "reason": "subscription_route_unverified",
              "metered_fallback_permitted": False,
              "subscription_capacity_verified": False}
    if not isinstance(status, Mapping):
        return result
    auth = status.get("auth")
    if not isinstance(auth, Mapping):
        return result
    routes = auth.get("runtimeAuthRoutes")
    providers = auth.get("providers")
    allowed = status.get("allowed")
    if (not isinstance(routes, list) or len(routes) != 1
            or not isinstance(providers, list) or len(providers) != 1
            or not isinstance(allowed, list) or not allowed
            or any(not isinstance(x, str) or not x.startswith("openai/")
                   for x in allowed)
            or status.get("fallbacks") not in (None, [])
            or auth.get("unusableProfiles")
            or auth.get("missingProvidersInUse")):
        return result
    route, provider = routes[0], providers[0]
    if not isinstance(route, Mapping) or not isinstance(provider, Mapping):
        return result
    profiles = provider.get("profiles")
    if not isinstance(profiles, Mapping):
        return result
    try:
        valid_profile = (
            type(profiles.get("oauth")) is int and profiles["oauth"] >= 1
            and type(profiles.get("apiKey")) is int and profiles["apiKey"] == 0
            and type(profiles.get("token")) is int and profiles["token"] == 0
            and type(profiles.get("count")) is int
            and profiles["count"] == profiles["oauth"]
        )
    except (TypeError, ValueError):
        valid_profile = False
    if (route.get("provider") != "openai"
            or route.get("runtime") != "codex"
            or route.get("authProvider") != "openai"
            or route.get("status") != "usable"
            or not isinstance(route.get("effective"), Mapping)
            or route["effective"].get("kind") != "profiles"
            or provider.get("provider") != "openai"
            or not valid_profile):
        return result
    return {**result, "status": "SUBSCRIPTION_OAUTH",
            "reason": "openai_oauth_route_no_api_key_profile"}


def _reset_hint(error: str, ended_at_ms: int) -> str | None:
    """Untrusted provider hint only; never an authority to dispatch."""
    found = _RESET.search(error)
    if not found or type(ended_at_ms) is not int or ended_at_ms <= 0:
        return None
    month, day, hour, minute, ampm, tz = found.groups()
    try:
        end_utc = datetime.fromtimestamp(ended_at_ms / 1000, timezone.utc)
        zone = ZoneInfo("America/New_York")
        h = int(hour) % 12 + (12 if ampm.upper() == "PM" else 0)
        for year in (end_utc.year, end_utc.year + 1):
            candidate = datetime(
                year, _MONTHS[month.title()], int(day), h, int(minute),
                tzinfo=zone,
            )
            if candidate.tzname() != tz.upper():
                continue
            age = candidate.astimezone(timezone.utc) - end_utc
            if timedelta(0) <= age <= timedelta(hours=36):
                return candidate.isoformat()
    except (ValueError, OverflowError, OSError, KeyError):
        return None
    return None


def quota_hold_for_native_task(task: Mapping[str, Any]) -> dict[str, Any] | None:
    """Classify a subscription-quota failure; never authorize task replay."""
    if not isinstance(task, Mapping) or task.get("status") != "failed":
        return None
    error = task.get("error")
    if not isinstance(error, str):
        return None
    if not any(marker in error.casefold() for marker in _SUBSCRIPTION_LIMIT):
        return None
    hint = _reset_hint(error, task.get("endedAt"))
    return {
        "disposition": "HOLD",
        "reason": "subscription_capacity_exhausted",
        "native_termination_confirmed": False,
        "independent_operational_completion_verified": False,
        "provider_action_authorized": False,
        "automatic_replay_authorized": False,
        "subscription_capacity_verified": False,
        "next_capacity_recheck_hint": hint,
        "requires_fresh_subscription_probe": True,
        "requires_existing_workboard_pmv3_reconciliation": True,
    }


def unique_subscription_quota_runs(tasks: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Collapse CLI/subagent ledger views of the same quota-blocked run.

    This is a read-only *inventory*, never a dispatch queue. Never infer
    resumability, approval or idempotency from a list of failed native tasks.
    """
    if not isinstance(tasks, list):
        return []
    by_run: dict[tuple[str, str], dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, Mapping):
            continue
        hold = quota_hold_for_native_task(task)
        agent_id, run_id = task.get("agentId"), task.get("runId")
        if (hold is None or not isinstance(agent_id, str) or not agent_id
                or not isinstance(run_id, str) or not run_id):
            continue
        key = (agent_id, run_id)
        if key not in by_run:
            by_run[key] = {
                "agent_id": agent_id, "run_id": run_id,
                "native_record_count": 0,
                "next_capacity_recheck_hint": hold["next_capacity_recheck_hint"],
                "automatic_replay_authorized": False,
                "subscription_capacity_verified": False,
            }
        by_run[key]["native_record_count"] += 1
        old = by_run[key]["next_capacity_recheck_hint"]
        hint = hold["next_capacity_recheck_hint"]
        if old is None or (hint is not None and hint > old):
            by_run[key]["next_capacity_recheck_hint"] = hint
    return [by_run[k] for k in sorted(by_run)]


def assess_live_subscription_capacity(status: Mapping[str, Any]) -> dict[str, Any]:
    """Classify an independently run OpenClaw OAuth provider probe.

    This is read-only advice, not task replay or production approval. The
    caller must freshly execute the native CLI rather than trusting user data.
    """
    result = {
        "status": "HOLD_UNVERIFIED",
        "reason": "fresh_subscription_probe_unverified",
        "metered_fallback_permitted": False,
        "automatic_replay_authorized": False,
        "subscription_capacity_verified": False,
    }
    if assess_subscription_route(status)["status"] != "SUBSCRIPTION_OAUTH":
        return result
    auth = status.get("auth")
    probes = auth.get("probes") if isinstance(auth, Mapping) else None
    entries = probes.get("results") if isinstance(probes, Mapping) else None
    if not isinstance(entries, list) or len(entries) != 1:
        return result
    probe = entries[0]
    if not isinstance(probe, Mapping):
        return result
    if (probe.get("provider") != "openai"
            or probe.get("model") not in status["allowed"]
            or probe.get("source") != "profile"
            or probe.get("mode") != "oauth"
            or not isinstance(probe.get("profileId"), str)
            or not probe["profileId"].startswith("openai:")):
        return result
    if probe.get("status") == "ok":
        return {**result,
                "status": "CAPACITY_PROBE_SUCCEEDED",
                "reason": "small_oauth_request_succeeded",
                "subscription_capacity_verified": True}
    if probe.get("status") == "rate_limit":
        return {**result, "status": "WAIT_QUOTA_RESET",
                "reason": "subscription_rate_limit_confirmed"}
    return result
