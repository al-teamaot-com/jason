"""Source-only, bounded PMv4 engineering manager relocation review.

Generate the successor units and exact effective desired-state delta. This
module never installs, enables, starts, approves, or writes production state.
The candidate is deliberately inert until a separately reviewed native root
transaction installs its independent successor admission guard.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

TIMER = "jason-pmv4-engineering.timer"
SERVICE = "jason-pmv4-engineering.service"
WATCHDOG_TIMER = "jason-self-heal-watchdog.timer"
WATCHDOG_SERVICE = "jason-self-heal-watchdog.service"
WATCHDOG_SOURCE = Path("infrastructure/openclaw-operations/systemd/user")
MANAGER_TIMERS = (TIMER, WATCHDOG_TIMER)
MANAGER_SERVICES = (SERVICE, WATCHDOG_SERVICE)
SOURCE = Path("infrastructure/pmv4-e-scheduler/systemd/user")
TARGET = Path("infrastructure/pmv4-e-engineering-manager/systemd")
ROOT_RECEIPT = "/etc/jason-owner-release/pmv4-e/engineering-manager-system-authorized.json"
SUCCESSOR_GUARD = "/usr/local/lib/jason/pmv4-e-engineering-manager/manager_guard.py"
GIT_METADATA = "/home/al/.local/lib/jason/engineering-worker-source/.git"
PAUSE = "/var/lib/jason/openclaw/support-repair/pmv3-engineering-owner-pause.json"
OLD_SERVICE_SHA256 = "e865a61a40b7dedb566b09759fab004325636f40e8179c028dc95a672bc59630"
OLD_TIMER_SHA256 = "8103e5cc8bdfa0ec9e3d87f763534cb7266a93ff32e3f674f2fd786b0d5385f2"
WATCHDOG_SERVICE_SHA256 = "fc49a66be3692c650f03a537cbd1d5265bee1d9e6593c91aab880fe1daf4ebb1"
WATCHDOG_TIMER_SHA256 = "d1739344579c0cdcf9634b463818e79718c1742dd636b5a8b466926e16a11242"


def need(ok, reason):
    if not ok:
        raise ValueError("ENGINEERING_MANAGER_RELOCATION_" + reason)


def digest(raw):
    return sha256(raw).hexdigest()


def units(base: Path):
    old = (base / SOURCE / SERVICE).read_bytes()
    timer = (base / SOURCE / TIMER).read_bytes()
    need(digest(old) == OLD_SERVICE_SHA256 and digest(timer) == OLD_TIMER_SHA256,
         "ACCEPTED_SOURCE_UNIT_CHANGED")
    service = old.decode("utf-8")
    need(service.count("[Service]\n") == 1 and service.count("[Unit]\n") == 1
         and service.count("ReadWritePaths=") == 1,
         "SOURCE_UNIT_FORMAT_CHANGED")
    service = service.replace(
        "[Unit]\n",
        "[Unit]\nConditionPathExists=" + ROOT_RECEIPT + "\n", 1)
    service = service.replace(
        "[Service]\n",
        "[Service]\nUser=al\nGroup=al\n", 1)
    # No command prefix that bypasses the sandbox. Retain both original guards,
    # and require a separate root-authorized manager transition before work.
    gate = ("ExecCondition=/usr/bin/python3 -I -B " + SUCCESSOR_GUARD
            + " --require-system\n")
    service = service.replace("Type=oneshot\n", gate + "Type=oneshot\n", 1)
    service = service.replace(
        "Environment=HOME=/home/al\n",
        "Environment=HOME=/home/al\n"
        "Environment=XDG_RUNTIME_DIR=/run/user/1000\n"
        "Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus\n"
        "Environment=PYTHONDONTWRITEBYTECODE=1\n", 1)
    service = service.replace("ReadWritePaths=", "ReadWritePaths=" + GIT_METADATA + " ", 1)
    wd = (base / WATCHDOG_SOURCE / WATCHDOG_SERVICE).read_bytes()
    wt = (base / WATCHDOG_SOURCE / WATCHDOG_TIMER).read_bytes()
    need(digest(wd) == WATCHDOG_SERVICE_SHA256 and digest(wt) == WATCHDOG_TIMER_SHA256,
         "WATCHDOG_BASELINE_CHANGED")
    wd = wd.decode("utf-8")
    wd = wd.replace("[Unit]\n", "[Unit]\nConditionPathExists=" + ROOT_RECEIPT + "\n", 1)
    wd = wd.replace("[Service]\n", "[Service]\nUser=al\nGroup=al\n" + gate, 1)
    wd = wd.replace("Environment=HOME=/home/al\n",
                    "Environment=HOME=/home/al\n"
                    "Environment=XDG_RUNTIME_DIR=/run/user/1000\n"
                    "Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus\n"
                    "Environment=PYTHONPATH=/opt/jason/current/tools\n"
                    "Environment=PYTHONDONTWRITEBYTECODE=1\n", 1)
    prior = "ExecStart=/usr/bin/python3 /opt/jason/current/tools/jason_self_heal_watchdog.py "
    need(wd.count(prior) == 1, "WATCHDOG_EXECSTART_CHANGED")
    wd = wd.replace(prior, "ExecStart=/usr/bin/python3 -B /home/al/.local/lib/jason/jason_self_heal_watchdog.py ", 1)
    return {str(TARGET / SERVICE): service.encode("utf-8"),
            str(TARGET / TIMER): timer,
            str(TARGET / WATCHDOG_SERVICE): wd.encode("utf-8"),
            str(TARGET / WATCHDOG_TIMER): wt}


def desired_state_delta(policy):
    """Move exactly the two required triggers and their allowed services."""
    need(isinstance(policy, dict) and policy.get("schema_version") == "1.0",
         "POLICY_SCHEMA")
    out = deepcopy(policy)
    for field, name in ((*[("required", n) for n in MANAGER_TIMERS], *[("allowed", n) for n in MANAGER_SERVICES])):
        u, s = field + "_user_units", field + "_system_units"
        for key in (u, s):
            entries = out.get(key)
            need(isinstance(entries, list) and all(isinstance(x, str) for x in entries)
                 and len(entries) == len(set(entries)), "POLICY_UNIT_INVENTORY")
        need(name in out[u] and name not in out[s], "MANAGER_SCOPE_NOT_EXACT")
        out[u] = [x for x in out[u] if x != name]
        out[s] = sorted(out[s] + [name])
    need(not any(n in out["allowed_user_units"] or n in out["allowed_system_units"] for n in MANAGER_TIMERS)
         and not any(n in out["required_user_units"] or n in out["required_system_units"] for n in MANAGER_SERVICES),
         "AMBIGUOUS_UNIT_CLASSIFICATION")
    return out


def routing_plan(*, base: Path, policy):
    files = units(base)
    return {
        "status": "source_only_preparation_not_production_authorization",
        "production_changes_performed": False,
        "owner_authority_issued": False,
        "source_units_sha256": {name: digest(raw) for name, raw in files.items()},
        "worker_uid": 1000,
        "worker_gid": 1000,
        "previous_manager": "user",
        "successor_manager": "system",
        "source_checkout_read_only": True,
        "git_metadata_write_path": GIT_METADATA,
        "original_pause_preserved_during_install": True,
        "require_legacy_timer_and_service_retired": True,
        "require_root_owned_successor_guard_and_receipt": True,
        "require_manager_aware_manifest_and_watchdog": True,
        "desired_state": desired_state_delta(policy),
    }
