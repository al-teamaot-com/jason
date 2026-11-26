"""No uninstalled root source can initiate Stage E; exact entry only."""
from pathlib import Path
import json
import subprocess
from types import SimpleNamespace
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
        "/usr/local/lib/jason/pmv4-e-bootstrap/native/tools/pmv4_e_native_root_entry.py")
    assert once.RELEASES==Path("/usr/local/lib/jason/pmv4-e-bootstrap/releases")
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


@pytest.mark.parametrize("missing,reason", [
    ("manifest.json", "OWNER_REVIEW_FILE_MISSING:manifest.json"),
    ("source-scope.json", "OWNER_REVIEW_FILE_MISSING:source-scope.json"),
    ("owner-proof.json", "OWNER_PROOF_MISSING"),
])
def test_missing_review_artifact_is_reported_explicitly(
        tmp_path, monkeypatch, missing, reason):
    import json
    from types import SimpleNamespace

    candidate = "a" * 40
    folder = tmp_path / ("pmv4-e-source-only-" + candidate)
    folder.mkdir(mode=0o700)
    folder.chmod(0o700)
    for name in ("manifest.json", "source-scope.json", "owner-proof.json"):
        if name == missing:
            continue
        path = folder / name
        path.write_text(json.dumps({"candidate_sha": candidate}))
        path.chmod(0o400)

    monkeypatch.setattr(once, "ARTIFACTS", tmp_path)
    real_lstat = Path.lstat
    def fixture_lstat(path):
        meta = real_lstat(path)
        if path == folder or path.parent == folder:
            return SimpleNamespace(
                st_mode=meta.st_mode, st_uid=1000, st_gid=1000,
                st_nlink=meta.st_nlink, st_size=meta.st_size,
            )
        return meta
    monkeypatch.setattr(Path, "lstat", fixture_lstat)

    with pytest.raises(once.StageERootBootstrapDenied, match=reason):
        once.read_offer(candidate, packet=None)

@pytest.mark.parametrize("timed_out", [True, False])
@pytest.mark.parametrize("valid_receipt", [True, False])
def test_failed_native_promotion_uses_only_journaled_rollback(timed_out, valid_receipt):
    candidate, rollback = "a" * 40, "b" * 40
    approval_id = "owner-mcp-" + "c" * 32
    request = {"rollback_sha": rollback,
               "signed_owner_proof": {"payload": {"approval_id": approval_id}}}
    packet = SimpleNamespace(canonical=lambda value: json.dumps(value).encode())
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if "--promote" in command:
            assert json.loads(kwargs["input"]) == request
            if timed_out:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return SimpleNamespace(returncode=2, stdout="")
        assert "--recover-interrupted" in command
        assert "--owner-request-stdin" not in command and "input" not in kwargs
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "status": "native_stage_e_six_unit_rollback_verified",
            "candidate_sha": candidate, "rollback_sha": rollback,
            "approval_id": approval_id if valid_receipt else "owner-mcp-" + "d" * 32,
            "protected_services_changed": False,
        }))

    if valid_receipt:
        result = once.native_promotion(candidate, packet=packet, request=request,
                                       forwarded=True, runner=run)
        assert result["status"] == "native_stage_e_six_unit_rollback_verified"
    else:
        with pytest.raises(once.StageERootBootstrapDenied, match="SEE_ROOT_JOURNAL"):
            once.native_promotion(candidate, packet=packet, request=request,
                                  forwarded=True, runner=run)
    assert len(commands) == 2


def test_native_failure_retains_original_safe_denial_without_replaying_proof():
    result=SimpleNamespace(returncode=2,stderr="DENIED:ComponentReleaseDenied:COMPONENT_PROTECTED_HEALTH_UNVERIFIED\n")
    assert once.native_failure_code(result)==result.stderr.strip()
    assert once.native_failure_code(None)=="NATIVE_TIMEOUT"
    assert once.native_failure_code(SimpleNamespace(returncode=2,stderr="arbitrary secret text"))=="NATIVE_EXIT_2"
