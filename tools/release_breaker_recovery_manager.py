#!/usr/bin/env python3
"""Bounded recovery orchestration for a *drift-watchdog* release breaker.

This unprivileged manager may request only the existing root-owned
'revalidate' intent after multiple fresh independent healthy observations.
It cannot close the breaker, retag images, deploy, approve a candidate, write
protected release state or execute arbitrary commands. The root transition
worker independently verifies LKG and root-owned drift before any closure.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

POLICY_PATH = "config/release-breaker-self-recovery-policy.json"
OPEN_SOURCE = "production_drift_watchdog"
OPEN_REASON = "continuous_production_drift_detected"
SHA = re.compile(r"^[a-f0-9]{40}$")
MAX_TRACKER_BYTES = 80000

# The root worker independently verifies all fields again. A preflight
# observation is diagnostic only and can never grant root release authority.
PROTECTED_LKG_FIELDS = (
    "revision", "runtime_revision", "runtime_image_id", "mcp_revision",
    "mcp_image_id", "host_revision", "host_release",
    "release_manager_source_revision", "desired_state_policy_digest",
    "scheduled_control_units",
)


class NativePreflightError(ValueError):
    """Fixed public reason code; never contains raw host/provider data."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def native_revalidation_preflight(state_root: Path, expected_revision: str) -> None:
    """Inspect installed LKG health BEFORE consuming a governed root attempt.

    No request files, protected state, services, attempts, or image tags change.
    The immutable root release worker will independently redo every check.
    """
    snapshot = state_root / "protected-readback" / "production-control-state.json"
    try:
        if (snapshot.is_symlink() or not snapshot.is_file()
                or snapshot.stat().st_mtime > time.time() + 10
                or time.time() - snapshot.stat().st_mtime > 90):
            raise NativePreflightError("protected_readback_unavailable_or_stale")
        control = read_json(snapshot)
        if (control.get("circuit_breaker") or {}).get("state") != "open":
            raise NativePreflightError("protected_breaker_state_changed")
        recorded = ((control.get("last_known_good") or {}).get("manifest") or {})
        if (recorded.get("revision") != expected_revision
                or recorded.get("complete") is not True):
            raise NativePreflightError("protected_lkg_revision_changed")
    except NativePreflightError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise NativePreflightError("protected_readback_unavailable_or_invalid") from exc

    host = Path.home() / ".local/lib/jason/release_manager_host_runner.py"
    if not host.is_file() or host.is_symlink():
        raise NativePreflightError("installed_release_manager_missing")
    sys.path.insert(0, str(host.parent))
    try:
        import release_manager_host_runner as release
        observed = release.capture_production_manifest(expected_revision)
    except Exception as exc:
        # Keep raw exception data out of the unprivileged recovery ledger:
        # it might include paths, secrets or provider fields.
        raise NativePreflightError("production_manifest_precheck_failed") from exc
    if not isinstance(observed, Mapping) or observed.get("complete") is not True:
        raise NativePreflightError("production_manifest_incomplete")
    for field in PROTECTED_LKG_FIELDS:
        if (recorded.get(field) is None or observed.get(field) is None
                or recorded[field] != observed[field]):
            raise NativePreflightError("protected_lkg_mismatch_" + field)



def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return t.astimezone(timezone.utc)


def read_json(path: Path, *, max_bytes: int = MAX_TRACKER_BYTES) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("bounded plain state file required")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("state must be a JSON object")
    return data


def atomic_json(path: Path, obj: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".breaker-recovery-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            os.fchmod(writer.fileno(), 0o600)
            json.dump(obj, writer, indent=2, sort_keys=True)
            writer.write("\n")
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_pinned_policy(repo: Path, expected_revision: str) -> dict[str, Any]:
    """Policy must be present in the exact installed LKG source checkout."""
    if not SHA.fullmatch(expected_revision):
        raise ValueError("invalid LKG revision")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True,
        capture_output=True, timeout=8, check=False,
    )
    if head.returncode or head.stdout.strip() != expected_revision:
        raise ValueError("installed engineering source differs from LKG")
    content = subprocess.run(
        ["git", "show", "HEAD:" + POLICY_PATH], cwd=repo, text=True,
        capture_output=True, timeout=8, check=False,
    )
    if content.returncode or len(content.stdout) > 12000:
        raise ValueError("pinned recovery policy unavailable")
    policy = json.loads(content.stdout)
    if not isinstance(policy, dict) or policy.get("schema_version") != "1.0":
        raise ValueError("invalid pinned recovery policy")
    if type(policy.get("enabled")) is not bool:
        raise ValueError("invalid enablement")
    limits = {
        "minimum_distinct_clean_observations": (2, 6),
        "minimum_open_seconds": (60, 900),
        "minimum_observation_interval_seconds": (10, 120),
        "maximum_observation_age_seconds": (60, 180),
        "maximum_authorized_attempts_per_breaker": (1, 3),
        "minimum_seconds_between_attempts": (120, 3600),
    }
    if set(policy) != {"schema_version", "enabled", *limits}:
        raise ValueError("unsupported recovery policy fields")
    for key, (minimum, maximum) in limits.items():
        val = policy.get(key)
        if type(val) is not int or not minimum <= val <= maximum:
            raise ValueError("policy bound invalid: " + key)
    return policy


def decision(
    control: Mapping[str, Any], drift: Mapping[str, Any],
    previous: Mapping[str, Any], policy: Mapping[str, Any],
    observed_now: datetime,
) -> dict[str, Any]:
    """Pure proof-and-readmission decision, never mutates caller data."""
    breaker = control.get("circuit_breaker") or {}
    lkg = (control.get("last_known_good") or {}).get("manifest") or {}
    if not isinstance(breaker, Mapping) or not isinstance(lkg, Mapping):
        raise ValueError("invalid protected breaker evidence")
    sha = str(lkg.get("revision") or "")
    if not SHA.fullmatch(sha) or lkg.get("complete") is not True:
        raise ValueError("missing immutable complete last-known-good baseline")
    previous = dict(previous) if isinstance(previous, Mapping) else {}
    opened_at = str(breaker.get("opened_at") or "")
    identity = hashlib.sha256(
        (sha + "|" + opened_at + "|" + str(breaker.get("reason") or "")
         + "|" + str(breaker.get("source") or "")).encode("utf-8")
    ).hexdigest()
    if previous.get("breaker_id") == identity:
        samples = previous.get("clean_observations", [])
        attempts = previous.get("attempts", [])
        if (not isinstance(samples, list) or not isinstance(attempts, list)
                or len(samples) > 6 or len(attempts) > 3
                or not all(isinstance(x, str) for x in samples)
                or not all(isinstance(x, dict) and isinstance(x.get("requested_at"), str)
                           and x.get("revision") == sha for x in attempts)):
            raise ValueError("invalid durable recovery history")
    else:
        samples, attempts = [], []
    state: dict[str, Any] = {
        "schema_version": "1.0", "observed_at": observed_now.isoformat(),
        "breaker_id": identity, "lkg_revision": sha,
        "breaker_state": str(breaker.get("state") or ""),
        "clean_observations": samples[-6:], "attempts": attempts[-3:],
        "status": "blocked", "next_action": "inspect_independent_health",
    }
    # Keep the last permitted attempt across breaker closeout/readback cycles.
    if isinstance(previous.get("last_revalidation_attempt"), dict):
        state["last_revalidation_attempt"] = previous["last_revalidation_attempt"]
    if isinstance(previous.get("last_preflight_failure"), dict):
        state["last_preflight_failure"] = previous["last_preflight_failure"]
    if breaker.get("state") == "closed":
        state["status"] = "already_closed"
        state["next_action"] = "none"
        return state
    if (breaker.get("state") != "open"
            or breaker.get("source") != OPEN_SOURCE
            or breaker.get("reason") != OPEN_REASON):
        state["next_action"] = "human_review_of_non_drift_release_breaker"
        return state
    if policy.get("enabled") is not True:
        state["next_action"] = "self_recovery_disabled_by_versioned_policy"
        return state
    try:
        open_age = (observed_now - timestamp(opened_at)).total_seconds()
    except (ValueError, TypeError):
        state["next_action"] = "invalid_breaker_opened_at"
        return state
    if open_age < policy["minimum_open_seconds"]:
        state["next_action"] = "wait_for_breaker_cooldown"
        return state
    if drift.get("schema_version") != "1.0" or drift.get("status") != "pass" or drift.get("problems") != []:
        state["clean_observations"] = []
        state["next_action"] = "wait_for_fresh_clean_root_drift"
        return state
    try:
        observed = timestamp(drift.get("observed_at"))
        age = (observed_now - observed).total_seconds()
    except (ValueError, TypeError):
        state["clean_observations"] = []
        state["next_action"] = "wait_for_fresh_clean_root_drift"
        return state
    if (not -5 <= age <= policy["maximum_observation_age_seconds"]
            or observed <= timestamp(opened_at)):
        state["clean_observations"] = []
        state["next_action"] = "wait_for_fresh_clean_root_drift"
        return state
    # Distinct root-observed samples only; repeated reads of one prior PASS
    # do not qualify as sustained independently refreshed health evidence.
    clean = []
    for sample in samples[-6:]:
        try:
            ts = timestamp(sample)
            if 0 <= (observed_now-ts).total_seconds() <= 3600 and (not clean or ts > timestamp(clean[-1])):
                clean.append(ts.isoformat())
        except (ValueError, TypeError):
            continue
    if not clean or observed > timestamp(clean[-1]):
        if not clean or (observed - timestamp(clean[-1])).total_seconds() >= policy["minimum_observation_interval_seconds"]:
            clean.append(observed.isoformat())
    state["clean_observations"] = clean[-6:]
    if len(clean) < policy["minimum_distinct_clean_observations"]:
        state["next_action"] = "accumulate_distinct_root_drift_passes"
        return state
    if len(attempts) >= policy["maximum_authorized_attempts_per_breaker"]:
        state["next_action"] = "operator_review_recovery_attempt_budget_exhausted"
        return state
    if attempts:
        prior_at = attempts[-1].get("requested_at") if isinstance(attempts[-1], Mapping) else None
        try:
            elapsed = (observed_now - timestamp(prior_at)).total_seconds()
        except (ValueError, TypeError):
            state["next_action"] = "invalid_prior_recovery_attempt"
            return state
        if elapsed < policy["minimum_seconds_between_attempts"]:
            state["next_action"] = "wait_for_next_bounded_attempt"
            return state
    state["status"] = "ready_for_governed_request"
    state["next_action"] = "native_root_verified_revalidate_lkg"
    return state


def transaction_busy(path: Path) -> bool:
    """Best-effort nonblocking release transaction observation.

    Root's independent revision checks remain authoritative if a production
    transaction begins after this observation. No file is created or changed.
    """
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        if not os.path.isfile(path):
            raise ValueError("production transaction lock must be regular")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
    finally:
        os.close(fd)


def classify_root_revalidation_error(exc: BaseException) -> str:
    """Classify known failures without persisting untrusted exception details.

    Root's separate permission, health, drift and LKG gates are authoritative.
    This is *diagnostic only*. No raw root rejection messages, paths, tokens,
    client data, attempts, retry eligibility, or approval data are modified.
    """
    message = str(exc).casefold()
    known = (
        ('immutable last-known-good mismatch:', 'root_lkg_fingerprint_mismatch'),
        ('production drift is not clean', 'root_independent_drift_not_clean'),
        ('independent production drift refresh did not pass', 'root_drift_refresh_failed'),
        ('independent drift refresh failed closed', 'root_drift_refresh_failed'),
        ('root-owned drift evidence is stale', 'root_drift_stale'),
        ('root-only mode-0600 file required', 'root_protected_file_invalid'),
        ('invalid requester ownership', 'root_request_ownership_rejected'),
        ('governed root transition result timed out', 'root_transition_result_timeout'),
        ('root-governed breaker transition succeeded but readback did not converge',
         'root_closeout_readback_not_converged'),
        ('protected release-state snapshot stale', 'protected_readback_stale'),
        ('authoritative health revalidation failed', 'production_manifest_precheck_failed'),
        ('governed root release transition rejected', 'root_transition_rejected_other'),
    )
    for fragment, classification in known:
        if fragment in message:
            return classification
    return 'unclassified_root_revalidation_failure'


def native_root_transition(state_root: Path, expected_revision: str) -> dict[str, Any]:
    """Use only existing guarded request/response path; root decides outcome."""
    host = Path.home() / ".local/lib/jason/release_manager_host_runner.py"
    if host.is_symlink() or not host.is_file():
        raise RuntimeError("pinned native Release Manager unavailable")
    sys.path.insert(0, str(host.parent))
    import release_manager_host_runner as release
    response = release.revalidate_circuit_breaker(state_root)
    breaker = response.get("circuit_breaker") or {}
    if (breaker.get("state") != "closed"
            or breaker.get("revalidated_revision") != expected_revision):
        raise RuntimeError("independent protected revalidation did not converge")
    return response


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--spool", type=Path, required=True)
    p.add_argument("--release-state", type=Path, required=True)
    args = p.parse_args()
    root = args.release_state.resolve()
    track = args.spool.resolve() / "release-breaker-recovery-state.json"
    try:
        control = read_json(root / "protected-readback/production-control-state.json")
        drift = read_json(root / "protected-readback/production-drift.json")
        expected_sha = str(((control.get("last_known_good") or {}).get("manifest") or {}).get("revision") or "")
        if track.is_symlink():
            raise ValueError("symlinked recovery ledger not permitted")
        previous = read_json(track) if track.exists() else {}
        # A closed protected breaker requires no further authority requests.
        # This remains a successful no-op even before LKG commissioning.
        if (control.get("circuit_breaker") or {}).get("state") == "closed":
            result = {
                "schema_version": "1.0", "observed_at": utcnow().isoformat(),
                "breaker_state": "closed", "status": "already_closed",
                "next_action": "none", "lkg_revision": expected_sha,
                "last_revalidation_attempt": previous.get("last_revalidation_attempt"),
            }
            atomic_json(track, result)
            print("RELEASE_BREAKER_RECOVERY=already_closed action=none", flush=True)
            return 0
        policy = load_pinned_policy(args.repo.resolve(), expected_sha)
        result = decision(control, drift, previous, policy, utcnow())
        if result["status"] == "ready_for_governed_request" and transaction_busy(
            root / "production-transaction.lock"
        ):
            result["status"] = "blocked"
            result["next_action"] = "wait_for_existing_production_transaction"
        if result["status"] == "ready_for_governed_request":
            # A local health failure is not a root revalidation attempt.
            # Do not consume the protected root-attempt budget when no
            # governed request can yet be made. Existing used attempts are
            # never removed or refunded.
            try:
                native_revalidation_preflight(root, expected_sha)
            except NativePreflightError as exc:
                result["status"] = "blocked"
                result["next_action"] = "reconcile_read_only_preflight"
                result["last_preflight_failure"] = {
                    "checked_at": result["observed_at"],
                    "failure_class": exc.code,
                }
                atomic_json(track, result)
                print("RELEASE_BREAKER_RECOVERY=blocked action=reconcile_read_only_preflight"
                      " reason=" + exc.code, flush=True)
                return 0
            result.pop("last_preflight_failure", None)
            # Persist request authorization consumption before any worker
            # action. A failed/crashed tool cannot silently replay the permit.
            attempt = {"requested_at": result["observed_at"],
                       "revision": result["lkg_revision"],
                       "result": "awaiting_root_worker"}
            result["attempts"].append(attempt)
            result["status"] = "pending_root_verification"
            atomic_json(track, result)
            try:
                native_root_transition(root, expected_sha)
                verify = read_json(root / "protected-readback/production-control-state.json")
                closed = verify.get("circuit_breaker") or {}
                if closed.get("state") != "closed" or closed.get("revalidated_revision") != expected_sha:
                    raise RuntimeError("root breaker closeout readback did not converge")
                attempt["result"] = "root_verified_closed"
                result["status"] = "root_verified_closed"
                result["next_action"] = "resume_native_release_manager"
            except (OSError, ValueError, RuntimeError, TypeError) as exc:
                attempt["result"] = "root_revalidation_rejected"
                attempt["error_type"] = type(exc).__name__
                attempt["failure_class"] = classify_root_revalidation_error(exc)
                result["status"] = "blocked"
                result["next_action"] = "root_revalidation_rejected_retry_if_budget_allows"
        if result.get("attempts"):
            result["last_revalidation_attempt"] = result["attempts"][-1]
        atomic_json(track, result)
        print("RELEASE_BREAKER_RECOVERY=" + result["status"] + " action=" + result["next_action"], flush=True)
        return 0
    except ValueError as exc:
        # During a governed candidate swap, installed source may temporarily
        # be ahead of the *still protected* LKG baseline. Do not request root
        # and do not create a new failed systemd unit that opens drift again.
        # Keep any original attempt ledger unchanged for future reconciliation.
        if str(exc) == "installed engineering source differs from LKG":
            print("RELEASE_BREAKER_RECOVERY=blocked action=await_exact_LKG_source_alignment", flush=True)
            return 0
        print("RELEASE_BREAKER_RECOVERY=FAILED ValueError", flush=True)
        return 1
    except (OSError, TypeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print("RELEASE_BREAKER_RECOVERY=FAILED " + type(exc).__name__, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
