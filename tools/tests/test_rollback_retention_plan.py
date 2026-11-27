from datetime import datetime, timezone
from copy import deepcopy
import json
from pathlib import Path
import pytest
from tools import rollback_retention_plan as p

NOW = datetime(2026, 11, 27, tzinfo=timezone.utc)
POLICY = json.loads((Path(__file__).resolve().parents[2]/"config/operations/rollback-retention-v1.json").read_text())

def row(role, date, index, image="a", revision="b"):
    return {"Name": f"/jason-{role}-rollback-{date}T120000Z",
            "Id": f"{index:064x}", "Image": "sha256:" + image*64,
             "State": {"Status": "exited", "Running": False, "Pid": 0,
                      "FinishedAt": f"{date[:4]}-{date[4:6]}-{date[6:]}T12:00:00Z"},
            "Config": {"Labels": {"com.teamaot.jason.source_revision": revision*40}},
            "HostConfig": {"AutoRemove": False}, "Mounts": [{"Type": "bind"}],
            "SizeRw": 100, "SizeRootFs": 1000}

def select(rows, free=2, cap=None):
    return p.choose(rows, inventory=sorted(x["Name"][1:] for x in rows),
                    maximum=len(rows) if cap is None else cap, free_slots=free, now=NOW,policy=POLICY)

def test_oldest_same_role_image_revision_and_retained_sibling():
    rows = [row("mcp-pilot", "20261110", 1), row("mcp-pilot", "20261111", 2),
            row("mcp-pilot", "20261112", 3), row("runtime", "20261113", 4)]
    a = select(rows)
    assert [x["target"]["id"] for x in a["retirements"]] == [rows[0]["Id"], rows[1]["Id"]]
    assert all(x["retained_siblings"][0]["id"] == rows[2]["Id"] for x in a["retirements"])
    assert len(a["after_names"]) == 2
    assert not a["original_docker_id_recreation_supported"]

@pytest.mark.parametrize("change", ["different_image", "different_revision", "running", "named_volume", "recent", "special", "auto_remove", "too_large"])
def test_no_unsafe_selection(change):
    a = row("runtime", "20261110", 1)
    b = row("runtime", "20261112", 2)
    if change == "different_image": b["Image"] = "sha256:"+"c"*64
    if change == "different_revision": b["Config"]["Labels"]["com.teamaot.jason.source_revision"] = "d"*40
    if change == "running": a["State"]["Running"] = True
    if change == "named_volume": a["Mounts"][0]["Type"] = "volume"
    if change == "recent": a["Name"] = "/jason-runtime-rollback-20261126T120000Z"
    if change == "special": a["Name"] = "/jason-runtime-rollback-audit-before-111"
    if change == "auto_remove": a["HostConfig"]["AutoRemove"] = True
    if change == "too_large": a["SizeRootFs"] = p.HARD_MAX_ARCHIVE_BYTES
    with pytest.raises(PermissionError, match="INSUFFICIENT_HISTORICAL_DUPLICATES"):
        select([a,b],free=1)

def test_inventory_mismatch_and_existing_capacity():
    a = row("runtime", "20261110", 1)
    with pytest.raises(PermissionError, match="INVENTORY_CHANGED"):
        p.choose([a], inventory=[], maximum=2, free_slots=1, now=NOW,policy=POLICY)
    assert select([a],free=1,cap=2)["retirements"] == []

def test_reference_exceptions_only_exact_historical_inventory():
    d = p.descriptor(row("runtime","20261110",1),now=NOW,policy=POLICY)
    value = {"scope":{"rollback_container_capacity_before":{"existing_names":[d["name"]]}}}
    assert p.unexpected_references(value,d,allow_historical_inventory=True) == []
    assert p.unexpected_references(value,d,allow_historical_inventory=False)
    for reference in [d["name"],d["id"],d["id"][:12]]:
        assert p.unexpected_references({"original_container": reference},d,allow_historical_inventory=True)
        assert p.unexpected_references({reference: "other"},d,allow_historical_inventory=True)
    assert p.unexpected_references({"scope":{"rollback_container_capacity_before":{"existing_names":["other "+d["name"]]}}},d,allow_historical_inventory=True)

def test_normalized_mount_order_but_no_config_equivalence_assumed():
    a = row("runtime","20261110",1)
    a["Mounts"].append({"Type":"bind","Source":"/two"})
    b = deepcopy(a); b["Mounts"].reverse()
    assert p.descriptor(a,now=NOW,policy=POLICY)==p.descriptor(b,now=NOW,policy=POLICY)
    b["Mounts"][0]["Source"]="/changed"
    assert p.descriptor(a,now=NOW,policy=POLICY)!=p.descriptor(b,now=NOW,policy=POLICY)

@pytest.mark.parametrize("key,value", [
    ("minimum_stopped_age_days", 0),
    ("minimum_retained_per_equivalent_group", 0),
    ("maximum_retirements_per_approved_transaction", 99),
    ("maximum_archive_bytes_per_container", p.HARD_MAX_ARCHIVE_BYTES+1),
    ("minimum_archive_free_bytes_after_reservation", 0),
    ("exact_authenticated_owner_approval_required", False),
    ("archive_and_readback_before_removal_required", False),
    ("preserve_native_capacity_limit", False),
    ("schema_version", "2.0"), ("unknown", True),
])
def test_invalid_policy_cannot_widen_safety(key,value):
    with pytest.raises(PermissionError):
        p.validate_policy({**POLICY,key:value})

def test_policy_values_control_retention_without_code_changes():
    rows = [row("runtime","20261110",1),row("runtime","20261111",2),row("runtime","20261112",3)]
    a = p.choose(rows,inventory=sorted(x["Name"][1:] for x in rows),
                 maximum=3,free_slots=1,now=NOW,
                 policy={**POLICY,"minimum_retained_per_equivalent_group":2})
    assert len(a["retirements"][0]["retained_siblings"]) == 2
    with pytest.raises(PermissionError):
        p.choose(rows,inventory=sorted(x["Name"][1:] for x in rows),
                 maximum=3,free_slots=2,now=NOW,
                 policy={**POLICY,"minimum_retained_per_equivalent_group":2})

def test_reference_exclusion_preserves_other_eligible_candidates():
    rows = [row("runtime","20261110",1),row("runtime","20261111",2),row("runtime","20261112",3)]
    a = p.choose(rows,inventory=sorted(x["Name"][1:] for x in rows),maximum=3,free_slots=1,
                 now=NOW,policy=POLICY,excluded_ids={rows[0]["Id"]})
    assert a["retirements"][0]["target"]["id"] == rows[1]["Id"]

def test_same_image_different_configuration_is_not_equivalent():
    a = row("runtime","20261110",1)
    b = row("runtime","20261112",2)
    b["HostConfig"]["ReadonlyRootfs"] = True
    with pytest.raises(PermissionError, match="INSUFFICIENT_HISTORICAL_DUPLICATES"):
        select([a,b],free=1)


def test_archived_environment_mode_requires_separate_exact_configuration_evidence():
    a = row("runtime","20261110",1)
    b = row("runtime","20261112",2)
    a["Config"].update(Env=["FEATURE_FLAG=old"], Image="test:old")
    b["Config"].update(Env=["FEATURE_FLAG=new"], Image="test:new")
    a["HostConfig"]["Mounts"] = [{"Type":"bind","Target":"/a"},{"Type":"bind","Target":"/b"}]
    b["HostConfig"]["Mounts"] = list(reversed(a["HostConfig"]["Mounts"]))
    r = select([a,b],free=1)["retirements"][0]
    assert r["target"]["configuration_sha256"] != r["retained_siblings"][0]["configuration_sha256"]
    assert r["target"]["equivalence_sha256"] == r["retained_siblings"][0]["equivalence_sha256"]
    with pytest.raises(PermissionError):
        p.choose([a,b],inventory=sorted(x["Name"][1:] for x in [a,b]),maximum=2,free_slots=1,
                 now=NOW,policy={**POLICY,"configuration_equivalence":"exact_effective_configuration"})
    b["Mounts"][0]["Source"] = "/different"
    with pytest.raises(PermissionError):
        select([a,b],free=1)

def test_equivalence_policy_rejects_unbounded_mode():
    with pytest.raises(PermissionError):
        p.validate_policy({**POLICY,"configuration_equivalence":"arbitrary"})

def test_recently_restarted_or_unknown_stop_time_is_not_historical():
    for finished in ("2026-11-26T12:00:00Z", "0001-01-01T00:00:00Z", "not-a-date"):
        a = row("runtime","20261110",1)
        b = row("runtime","20261112",2)
        a["State"]["FinishedAt"] = finished
        with pytest.raises(PermissionError,match="INSUFFICIENT_HISTORICAL_DUPLICATES"):
            select([a,b],free=1)
