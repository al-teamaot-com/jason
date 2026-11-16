"""PMv4 A1 root watchdog one-name review; never edits protected policy."""
from copy import deepcopy
from pathlib import Path
import json
import os
import pytest
import subprocess

from tools import pmv4_a1_watchdog_policy_review as review


ROOT=Path(__file__).resolve().parents[1]
CAND=(ROOT/"config/production-desired-state.json").read_bytes()
BASE=subprocess.run(["git","-C",str(ROOT),"show",
                     review.SOURCE_SHA+":config/production-desired-state.json"],
                    capture_output=True,check=True).stdout


def test_source_change_is_precisely_one_optional_container():
    result=review.exact_source(BASE,CAND)
    assert result["only_one_optional_container"]==review.NAME
    assert result["candidate_source_policy_sha256"]==review.PROPOSED_SHA256


def test_live_overlay_preserved_and_reversible():
    old=review.decode(BASE)
    old["allowed_system_units"].append("jason-approved-historical.service")
    old["allowed_user_units"].append("jason-approved-historical.timer")
    old["allowed_running_containers"].append("independently-approved-legacy")
    original=json.dumps(old,sort_keys=True).encode()
    attestation=review.review_live(original,BASE,CAND)
    assert attestation["root_policy_changes"]==1
    assert attestation["other_root_policy_fields_changed"] is False
    assert attestation["required_containers_changed"] is False
    assert attestation["root_original_sha256"]==review.sha(original)
    expected=review.exact_addition(old)
    assert expected["allowed_running_containers"]==(
        old["allowed_running_containers"]+[review.NAME])
    assert expected["allowed_system_units"]==old["allowed_system_units"]
    assert expected["allowed_user_units"]==old["allowed_user_units"]
    assert attestation["root_exact_candidate_sha256"]==review.sha(
        (json.dumps(expected,sort_keys=True,indent=2,
                    separators=(",", ": "))+"\n").encode())
    assert attestation["root_writes"] is False
    assert attestation["owner_authorization_issued"] is False


@pytest.mark.parametrize("change",[
    lambda d:d["required_containers"].append(review.NAME),
    lambda d:d["allowed_running_containers"].append("other"),
    lambda d:d.pop("required_system_units"),
])
def test_arbitrary_source_changes_rejected(change):
    raw=review.decode(CAND)
    change(raw)
    with pytest.raises(review.PolicyReviewDenied):
        review.exact_source(BASE,json.dumps(raw).encode())


def test_root_already_allows_shadow_rejected():
    raw=review.decode(CAND)
    with pytest.raises(review.PolicyReviewDenied,
                       match="SHADOW_ALREADY_DECLARED"):
        review.review_live(json.dumps(raw).encode(),BASE,CAND)


@pytest.mark.parametrize("mutation",[
    lambda d:d["required_containers"].append("unallowed-runtime"),
    lambda d:d["allowed_running_containers"].append("jason-runtime"),
    lambda d:d.update(schema_version="0.9"),
])
def test_invalid_root_overlay_rejected(mutation):
    raw=review.decode(BASE)
    mutation(raw)
    with pytest.raises(review.PolicyReviewDenied):
        review.review_live(json.dumps(raw).encode(),BASE,CAND)


def test_readonly_file_inode_gate(tmp_path):
    raw=BASE
    p=tmp_path/"root-policy.json"
    p.write_bytes(raw)
    p.chmod(0o600)
    with p.open("rb") as f:
        assert review.live_readonly(f.fileno(),expected_uid=os.geteuid(),
                                   expected_gid=os.getegid())==raw
    p.chmod(0o644)
    with p.open("rb") as f,pytest.raises(review.PolicyReviewDenied,
                                                match="INODE_UNTRUSTED"):
        review.live_readonly(f.fileno(),expected_uid=os.geteuid(),
                                   expected_gid=os.getegid())
    p.chmod(0o600)


def test_cli_declares_no_mutating_action():
    assert review.ACTION.endswith("admission-v1")
    text=(ROOT/"tools/pmv4_a1_watchdog_policy_review.py").read_text()
    assert "--execute" not in text
    assert "--apply" not in text
    assert "os.replace(" not in text
    assert "os.unlink(" not in text
    assert "subprocess.run(command,capture_output=True" in text
