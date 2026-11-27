"""Pure, reusable historical rollback archive admission.

This module selects a bounded review scope; it never deletes, exports, starts,
or modifies a container. Exact native execution and Owner authorization remain
outside this planner.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re

NAME = re.compile(r"(jason-(?:runtime|mcp-pilot|mcp|teams-gateway))-rollback-(\d{8}T\d{6}Z)\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
HARD_MAX_ARCHIVE_BYTES = 536870912
POLICY_FIELDS = frozenset({
    "schema_version", "minimum_stopped_age_days",
    "minimum_retained_per_equivalent_group",
    "maximum_retirements_per_approved_transaction",
    "maximum_archive_bytes_per_container",
    "minimum_archive_free_bytes_after_reservation",
    "exact_authenticated_owner_approval_required",
    "archive_and_readback_before_removal_required",
    "preserve_native_capacity_limit", "configuration_equivalence",
})
HISTORICAL_FIELDS = frozenset({
    "scope.rollback_container_capacity_before.existing_names.[]",
    "scope.bounded_objective_continuation.rollback_container_capacity_revalidated.stopped_names.[]",
    "scope.bounded_objective_continuation.rollback_container_capacity_revalidated.after_stopped_names.[]",
})


def need(ok, code):
    if not ok:
        raise PermissionError("ROLLBACK_RETENTION_" + code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_policy(policy):
    need(isinstance(policy, dict) and set(policy) == POLICY_FIELDS
         and policy["schema_version"] == "1.0", "POLICY_SCHEMA")
    ranges = {"minimum_stopped_age_days": (7, 365),
              "minimum_retained_per_equivalent_group": (1, 16),
              "maximum_retirements_per_approved_transaction": (1, 6),
              "maximum_archive_bytes_per_container": (1048576, HARD_MAX_ARCHIVE_BYTES),
              "minimum_archive_free_bytes_after_reservation": (1073741824, 107374182400)}
    need(all(type(policy[k]) is int and lo <= policy[k] <= hi
             for k, (lo, hi) in ranges.items()), "POLICY_BOUNDS")
    need(all(policy[k] is True for k in ("exact_authenticated_owner_approval_required",
             "archive_and_readback_before_removal_required", "preserve_native_capacity_limit")),
         "POLICY_SAFETY")
    need(policy["configuration_equivalence"] in
         ("exact_effective_configuration", "archive_historical_environment"),
         "POLICY_EQUIVALENCE")
    return dict(policy)


def normalize_inspect(row):
    host = dict(row["HostConfig"])
    if isinstance(host.get("Mounts"), list):
        host["Mounts"] = sorted(host["Mounts"], key=canonical)
    return {**row, "HostConfig": host, "Mounts": sorted(row["Mounts"], key=canonical)}


def descriptor(row, *, now, policy):
    policy = validate_policy(policy)
    max_archive = policy["maximum_archive_bytes_per_container"]
    name = row.get("Name", "")[1:]
    m = NAME.fullmatch(name)
    if m is None:
        return None
    when = datetime.strptime(m[2], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    state = row.get("State", {})
    try:
        stopped_at = datetime.fromisoformat(state["FinishedAt"].replace("Z","+00:00"))
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    if stopped_at.utcoffset() is None or stopped_at.year < 2000:
        return None
    revision = row.get("Config", {}).get("Labels", {}).get("com.teamaot.jason.source_revision", "")
    mounts = row.get("Mounts")
    image = row.get("Image", "")
    rootfs = row.get("SizeRootFs")
    rw = row.get("SizeRw")
    if not (now - max(when, stopped_at) >= timedelta(days=policy["minimum_stopped_age_days"])
            and state.get("Status") == "exited" and state.get("Running") is False
            and state.get("Pid") == 0
            and HEX.fullmatch(row.get("Id", "")) and SHA.fullmatch(revision)
            and image.startswith("sha256:") and HEX.fullmatch(image[7:])
            and row.get("HostConfig", {}).get("AutoRemove") is False
            and isinstance(mounts, list) and all(x.get("Type") == "bind" for x in mounts)
            and type(rootfs) is int and 0 < rootfs < max_archive
            and type(rw) is int and 0 <= rw < max_archive):
        return None
    normalized = normalize_inspect(row)
    config = {k:v for k,v in row["Config"].items() if k != "Hostname"}
    configuration = {"config": config, "host": normalized["HostConfig"],
                     "mounts": normalized["Mounts"]}
    config_digest = digest(configuration)
    # The immutable image ID and source revision must match independently.
    # Only historical image-tag spelling and environment values may differ;
    # both exact configurations are separately bound and archived. This is
    # NOT a claim that the remaining sibling can recreate the retired ID.
    equivalence = configuration
    if policy["configuration_equivalence"] == "archive_historical_environment":
        equivalence = {**configuration, "config": {
            k:v for k,v in config.items() if k not in ("Env","Image")}}
    equivalence_digest = digest(equivalence)
    return {"name": name, "role": m[1], "id": row["Id"], "image": image,
             "revision": revision, "created_name_at": when.isoformat(),
            "stopped_at": stopped_at.isoformat(),
            "metadata_sha256": digest(normalized), "configuration_sha256": config_digest, "equivalence_sha256": equivalence_digest, "rootfs_bytes": rootfs,
            "writable_bytes": rw}


def choose(rows, *, inventory, maximum, free_slots, now, policy, excluded_ids=()):
    policy = validate_policy(policy)
    need(type(maximum) is int and 0 < maximum <= 100
         and type(free_slots) is int and 1 <= free_slots <= 6, "CAPACITY_POLICY")
    need(isinstance(inventory, list) and inventory == sorted(set(inventory))
         and len(inventory) <= maximum, "INVENTORY")
    needed = max(0, len(inventory) + free_slots - maximum)
    need(needed <= policy["maximum_retirements_per_approved_transaction"], "BATCH_LIMIT")
    need(len(rows) == len(inventory)
         and sorted(r["Name"][1:] for r in rows) == inventory
         and len({r["Id"] for r in rows}) == len(rows), "INVENTORY_CHANGED")
    groups = {}
    for row in rows:
        d = descriptor(row, now=now, policy=policy)
        if d:
            groups.setdefault((d["role"], d["image"], d["revision"], d["equivalence_sha256"]), []).append(d)
    eligible = []
    for group in groups.values():
        group.sort(key=lambda d: d["created_name_at"])
        retain = policy["minimum_retained_per_equivalent_group"]
        retained = group[-retain:]
        eligible.extend({"target": d, "retained_siblings": retained}
                        for d in group[:-retain] if d["id"] not in excluded_ids)
    eligible.sort(key=lambda d: (d["target"]["created_name_at"], d["target"]["name"]))
    need(len(eligible) >= needed, "INSUFFICIENT_HISTORICAL_DUPLICATES")
    selected = eligible[:needed]
    removed = {x["target"]["name"] for x in selected}
    return {"before_names": inventory, "after_names": [n for n in inventory if n not in removed],
            "maximum": maximum, "free_slots_requested": free_slots,
            "retirements": selected, "archive_max_bytes_per_target": policy["maximum_archive_bytes_per_container"],
            "retention_policy_sha256": digest(policy),
            "original_docker_id_recreation_supported": False}


def unexpected_references(value, target, *, allow_historical_inventory):
    """Only exact legacy audit *inventory* fields are eligible exceptions.

    A name, full ID or abbreviated ID in any other JSON field blocks removal,
    including a terminal receipt with an original-container rollback identity.
    """
    tokens = (target["name"], target["id"], target["id"][:12])
    result = []
    def visit(v, path):
        if isinstance(v, dict):
            for k, x in v.items():
                if any(t in str(k) for t in tokens):
                    result.append(".".join(path + ("<key>",)))
                visit(x, path + (str(k),))
        elif isinstance(v, list):
            for x in v:
                visit(x, path + ("[]",))
        elif isinstance(v, str) and any(t in v for t in tokens):
            field = ".".join(path)
            if not (allow_historical_inventory and field in HISTORICAL_FIELDS and v == target["name"]):
                result.append(field)
    visit(value, ())
    return result
