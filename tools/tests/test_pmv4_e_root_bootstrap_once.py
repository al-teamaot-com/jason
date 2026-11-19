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


def test_inert_recovery_reuses_root_signed_started_and_never_issues_new_grant():
    source=Path(once.__file__).read_text()
    assert 'mode.add_argument("--recover-inert"' in source
    assert '"NATIVE_RELEASE_HAS_STARTED_MUST_USE_LEDGER_RECOVERY"' in source
    assert "phase.signed_started(" in source
    assert "root.recover_inert_stage(hashes)" in source
    assert "source.recover_inert(" in source
    assert "owner_approval_reusable" in source
    assert "phase.begin(request)" in source
    assert source.index("phase.begin(request)") < source.index(
        "source.stage(candidate=candidate,exact_hashes=hashes)")


def test_exact_native_release_records_match_root_attestor_reader_modes(tmp_path, monkeypatch):
    """The writer must produce downstream 0444 records, not 0400 artifacts."""
    import json
    import os
    import stat
    from tools import pmv4_e_native_root_entry as entry
    from tools import pmv4_e_native_root_manifest_attestation as rootproof

    root = tmp_path / "native"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(once, "NATIVE_RECORDS", root)
    # The isolated fixture substitutes ONLY the production directory UID
    # check; no production code has a non-root entrypoint or a bypass flag.
    monkeypatch.setattr(once, "checked_root_dir", lambda path, **kw:
                        None if path == root else
                        (_ for _ in ()).throw(AssertionError(path)))
    sample = {
        "manifest": {"candidate_sha": "a"*40,
                     "rollback_sha": "b"*40},
        "source_scope": {"candidate_sha": "a"*40,
                         "rollback_sha": "b"*40},
    }
    class Packet:
        @staticmethod
        def canonical(obj):
            return json.dumps(obj, sort_keys=True,
                              separators=(",", ":")).encode()

    once.safe_release_records("a"*40, sample, Packet)
    target = root / ("a"*40)
    assert stat.S_IMODE(target.lstat().st_mode) == 0o555
    for filename in ("manifest.json", "source-scope.json"):
        path = target / filename
        assert stat.S_IMODE(path.lstat().st_mode) == 0o444
        assert json.loads(rootproof._regular(path, production=False)) in sample.values()
        assert json.loads(entry.trust_file(path, uid=os.getuid())) in sample.values()
