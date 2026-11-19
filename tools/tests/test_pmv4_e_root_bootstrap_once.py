"""No uninstalled root source can initiate Stage E; exact entry only."""
from pathlib import Path
import pytest
from tools import pmv4_e_root_bootstrap_once as once


@pytest.mark.parametrize("bad",["main","", "f"*39,"A"*40, "e"*41])
def test_bad_candidate_rejected_without_accessing_system_or_identity(bad):
    with pytest.raises(once.StageERootBootstrapDenied,
                       match="EXACT_CANDIDATE_SHA_REQUIRED"):
        once.candidate_arg(bad)


def test_uninstalled_source_cannot_bootstrap_root_or_sign_approval():
    with pytest.raises(once.StageERootBootstrapDenied,
                       match="CANONICAL_UID0_BOOTSTRAP_INSTALL_REQUIRED"):
        once.run_once("f"*40,stage_only=True)


def test_exact_immutable_source_stage_then_original_native_only():
    source=Path(once.__file__).read_text()
    assert "SignedInertBootstrap(" in source
    assert "ImmutableRootSourceStage(" in source
    assert "RootTrustStager(" in source
    assert "core.host_transaction()" in source
    assert "core.freeze_transaction(" in source
    assert "stage_only" in source and "--promote" in source
    assert "stage-and-promote" in source
    assert '"/usr/bin/python3","-I","-B",str(FINAL_ENTRY)' in source
    assert "original_native_receipt" in source
    assert "issue_exact_owner_release(" not in source
    assert "docker restart" not in source
    assert "sudo " not in source
    assert "systemctl start" not in source
    assert "os.system(" not in source


def test_original_pinned_native_source_digest_is_explicitly_unchanged():
    from hashlib import sha256
    from tools import pmv4_e_exact_release_packet as packet
    for name,expected in once.PINNED_NATIVE.items():
        assert sha256((packet.ROOT/name).read_bytes()).hexdigest()==expected


def test_owner_requested_stage_e_cannot_expand_to_other_paths():
    assert once.FINAL_ENTRY==Path(
        "/opt/jason/pmv4-e-trusted/tools/pmv4_e_native_root_entry.py")
    assert once.RELEASES==Path("/opt/jason/releases")
    assert once.NATIVE_RECORDS==Path(
        "/var/lib/jason/independent-component-release/releases")
    assert once.ENTRY.parent.parent==once.TRUST
    assert not hasattr(once,"approve_release")
