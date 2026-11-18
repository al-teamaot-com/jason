"""Signed-root-only inert trust stage: exact 46-file source and rollback."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from tools import pmv4_e_root_trust_stage as trust
from tools import pmv4_e_exact_release_packet as packet


def bundle_hashes():
    return {p:sha256((packet.ROOT/p).read_bytes()).hexdigest()
            for p in packet.REVIEWED_PATHS}


def stager(tmp_path,*,signed=True,marker_absent=True,inert=True,
           production=False):
    return trust.RootTrustStager(
        source=packet.ROOT,target=tmp_path/"pmv4-e-trusted",
        native_signed_started=lambda:signed,
        native_host_locked=lambda:True,
        native_freeze_locked=lambda:True,
        native_marker_absent=lambda:marker_absent,
        native_replacements_inert=lambda:inert,
        production=production,
    )


def test_signed_inert_root_tree_staged_sealed_verified_and_recovered(tmp_path):
    b=stager(tmp_path)
    hashes=bundle_hashes()
    result=b.stage(source_sha="b"*40,exact_hashes=hashes)
    assert result["status"]=="reviewed_root_trust_bundle_sealed_no_unit_activation"
    assert result["installed_file_count"]==len(packet.REVIEWED_PATHS)
    assert result["production_services_changed"] is False
    assert b.verify(hashes)==result
    assert (b.target/"tools/pmv4_e_unit_admission.py").is_file()
    assert (b.target/"tools/pmv4_e_root_trust_stage.py").is_file()
    assert b.target.stat().st_mode&0o777==0o555
    b.recover_inert_stage(hashes)
    assert not b.target.exists()


@pytest.mark.parametrize("signed,marker,inert",[
    (False,True,True),(True,False,True),(True,True,False),
])
def test_unsigned_active_or_accepted_staging_is_denied_before_files(
    tmp_path,signed,marker,inert
):
    b=stager(tmp_path,signed=signed,marker_absent=marker,inert=inert)
    with pytest.raises(trust.PMv4ERootTrustDenied):
        b.stage(source_sha="b"*40,exact_hashes=bundle_hashes())
    assert not b.target.exists()


def test_unreviewed_extra_file_or_modified_sha_denied(tmp_path):
    b=stager(tmp_path)
    hashes=bundle_hashes()
    with pytest.raises(trust.PMv4ERootTrustDenied,match="EXACT_FILE_SET_REQUIRED"):
        b.stage(source_sha="b"*40,exact_hashes={**hashes,"etc/passwd":"0"*64})
    modified=dict(hashes)
    modified[next(iter(modified))]="0"*64
    with pytest.raises(trust.PMv4ERootTrustDenied,match="SOURCE_DIGEST_MISMATCH"):
        b.stage(source_sha="b"*40,exact_hashes=modified)
    assert not b.target.exists()


def test_unknown_file_in_staging_denies_recovery(tmp_path):
    b=stager(tmp_path)
    hashes=bundle_hashes()
    b.stage(source_sha="b"*40,exact_hashes=hashes)
    (b.target/"foreign.txt").write_text("unknown")
    with pytest.raises(trust.PMv4ERootTrustDenied,match="RECOVERY_EXTRA_FILE"):
        b.recover_inert_stage(hashes)
    assert (b.target/"foreign.txt").is_file()


def test_partial_exact_source_prefix_recovers_after_power_loss(tmp_path):
    b=stager(tmp_path)
    hashes=bundle_hashes()
    b.stage(source_sha="b"*40,exact_hashes=hashes)
    target=b.target/"tools/pmv4_e_native_systemd_adapter.py"
    data=target.read_bytes()
    assert len(data)>100
    target.write_bytes(data[:100])
    target.chmod(0o444)
    b.recover_inert_stage(hashes)
    assert not b.target.exists()


def test_marker_appearing_after_stage_denies_cleanup(tmp_path):
    marker={"absent":True}
    b=trust.RootTrustStager(
        source=packet.ROOT,target=tmp_path/"pmv4-e-trusted",
        native_signed_started=lambda:True,
        native_host_locked=lambda:True,
        native_freeze_locked=lambda:True,
        native_marker_absent=lambda:marker["absent"],
        native_replacements_inert=lambda:True,
        production=False,
    )
    hashes=bundle_hashes()
    b.stage(source_sha="b"*40,exact_hashes=hashes)
    marker["absent"]=False
    with pytest.raises(trust.PMv4ERootTrustDenied,match="LIVE_REPLACEMENT_RECOVERY_DENIED"):
        b.recover_inert_stage(hashes)
    assert b.target.exists()


def test_install_root_can_never_be_mutated_from_chat_or_ambient_shell():
    source=(packet.ROOT/"tools/pmv4_e_root_trust_stage.py").read_text()
    assert "native_signed_started" in source
    assert "native_host_locked" in source
    assert "native_freeze_locked" in source
    assert "native_marker_absent" in source
    assert "native_replacements_inert" in source
    for forbidden in ("subprocess.Popen(","os.system(","shell=True",
                      "systemctl restart","docker restart","requests.post("):
        assert forbidden not in source
