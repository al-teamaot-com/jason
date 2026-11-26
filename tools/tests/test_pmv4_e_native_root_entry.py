"""Stage E final root entry can only consume one original signed native proof."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from tools import pmv4_e_native_root_entry as entry
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet
from tools.tests.test_pmv4_e_signed_native_ledger import (
    CANDIDATE,ROLLBACK,approval,
)


def reviewed():
    return contract.draft(candidate_sha=CANDIDATE,rollback_sha=ROLLBACK)["manifest"]


def correct_request():
    m=reviewed()
    return {
        "schema_version":"1.0","request_id":"release-"+CANDIDATE[:16],
        "action":"pmv4_e_stage_exact_signed_inert_root_v1",
        "candidate_sha":CANDIDATE,"rollback_sha":ROLLBACK,
        "scope_sha256":m["source_scope_sha256"],
        "manifest_sha256":sha256(packet.canonical(m)).hexdigest(),
        "freeze_sha256":m["freeze_sha256"],
        "signed_owner_proof":approval(m),
    }


def test_authentic_exact_owner_request_can_only_be_conveyed_not_issued():
    request=correct_request()
    assert entry.require_exact_owner_request(request,reviewed())==request[
        "signed_owner_proof"]
    assert "issue_exact_owner_release" not in Path(entry.__file__).read_text()
    assert "signed_owner_proof" in Path(entry.__file__).read_text()


@pytest.mark.parametrize("field,bad",[
    ("candidate_sha","f"*40),("rollback_sha","b"*40),
    ("scope_sha256","0"*64),("manifest_sha256","0"*64),
    ("freeze_sha256","0"*64),("request_id","release-"+"0"*16),
    ("action","host_reconcile"),("schema_version","2.0"),
])
def test_user_controlled_request_cannot_choose_another_action_scope(
        field,bad):
    request=correct_request()
    request[field]=bad
    with pytest.raises(entry.StageERootEntryDenied,
                       match="OWNER_REQUEST_NOT_EXACT_BOUND_RELEASE"):
        entry.require_exact_owner_request(request,reviewed())


def test_malformed_or_missing_signed_owner_payload_denied():
    for changed in ({"extra":"yes"},{"signed_owner_proof":{}},
                    {"signed_owner_proof":{"payload":{"approval_id":"id"}}}):
        r=correct_request()
        r.update(changed)
        with pytest.raises(entry.StageERootEntryDenied):
            entry.require_exact_owner_request(r,reviewed())


def test_existing_native_release_sha_pins_still_match_unmodified_original():
    for relative,digest in entry.PINNED_NATIVE_SHA256.items():
        assert sha256((packet.ROOT/relative).read_bytes()).hexdigest()==digest


@pytest.mark.parametrize("sha",[
    "", "main", "a"*39,"g"*40,ROLLBACK+"a",
])
def test_invalid_sha_never_resolves_install_root(sha):
    with pytest.raises(entry.StageERootEntryDenied,match="CANDIDATE_SHA_NOT_EXACT"):
        entry.exact_candidate(sha)


def test_uninstalled_root_entry_fails_before_reading_any_owner_proof():
    with pytest.raises(entry.StageERootEntryDenied,match="CANONICAL_ROOT_ENTRY_NOT_INSTALLED"):
        entry.main(["--candidate-sha",CANDIDATE,"--promote"])


def test_zero_arbitrary_dispatch_and_same_native_controller():
    source=Path(entry.__file__).read_text()
    for banned in ("sudo ","docker restart","subprocess.Popen(",
                   "os.system(","issue_exact_owner_release(",
                   "kill -9","disable --now"):
        assert banned not in source
    assert "StageESignedNativeLedger(" in source
    assert "NativeStageEHost(" in source
    assert "StageERootBridge(" in source
    assert "StageEUnitAdapter(" in source
    assert "recover_interrupted_rollback()" in source
    assert "PMV3_FREEZE" not in source or "freeze" in source.lower()
