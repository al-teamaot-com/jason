"""Source-only Stage A0 bootstrap release boundaries; never mutate production."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import tarfile
import time
from unittest.mock import patch

import pytest

from tools import pmv4_stage_a0_sparse_source as sparse
from tools import pmv4_stage_a0_issuer_activation as issuer

SHA = "a" * 40
LKG = "b" * 40
FREEZE = "c" * 64
IMAGE = "sha256:" + "d" * 64
RUNTIME_IMAGE = "sha256:" + "e" * 64


def blobs(sha: str, path: str) -> bytes:
    assert sha == SHA
    return ("source-for:" + path).encode()


@pytest.fixture
def manifest():
    return sparse.source_manifest(
        SHA, blobs, freeze_sha256=FREEZE, current_lkg=LKG,
    )


@pytest.fixture
def archive(manifest):
    return sparse.package_bytes(manifest, blobs)


def test_exact_source_only_allowlist_never_includes_runtime_or_mcp():
    names = sparse.required_paths()
    assert "tools/pmv4_stage_a_native_install.py" in names
    assert "implementation/kernel/signed_owner_release.py" in names
    assert len(names) == 13
    assert all(not name.startswith((
        "infrastructure/jason-runtime/", "infrastructure/jason-mcp/",
        "implementation/mcp_service/", "implementation/runtime_service/",
    )) for name in names)
    for name in ("../../etc/shadow", "/root/a", "tools/../x.py",
                 "implementation/mcp_service/src/jason_mcp/server.py",
                 "infrastructure/jason-runtime/production-deploy.sh",
                 "config/production-desired-state.json",
                 "tools\\pmv4_stage_a_native_install.py"):
        with pytest.raises(sparse.SparseSourceDenied):
            sparse._checked_path(name)


def test_rejects_unbound_or_same_source_identity():
    for source, lkg, freeze in (
        (SHA, SHA, FREEZE),
        ("x" * 40, LKG, FREEZE),
        (SHA, LKG, "x" * 64),
        ("", LKG, FREEZE),
    ):
        with pytest.raises(sparse.SparseSourceDenied):
            sparse.source_manifest(source, blobs,
                                   freeze_sha256=freeze, current_lkg=lkg)


def test_sparse_tar_is_deterministic_and_root_metadata_only(manifest, archive):
    assert archive == sparse.package_bytes(manifest, blobs)
    sparse.verify_package(archive, manifest)
    with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
        files = [member for member in handle if member.isfile()]
        assert len(files) == len(manifest["files"])
        assert all((item.uid, item.gid, item.mode, item.mtime)
                   == (0, 0, 0o444, 0) for item in files)
    assert manifest["target"] == "/opt/jason/releases/" + SHA
    assert manifest["root_install_authorized"] is False
    assert manifest["production_services_restart"] is False
    assert manifest["provider_writes"] is False


def test_tar_denies_symlink_even_when_path_is_allowlisted(manifest, archive):
    name = manifest["files"][0]["path"]
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as target:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as original:
            for member in original:
                if member.name == name:
                    replacement = deepcopy(member)
                    replacement.type = tarfile.SYMTYPE
                    replacement.linkname = "/etc/shadow"
                    replacement.size = 0
                    target.addfile(replacement)
                else:
                    target.addfile(member, original.extractfile(member)
                                   if member.isfile() else None)
    with pytest.raises(sparse.SparseSourceDenied, match="UNSAFE_METADATA"):
        sparse.verify_package(output.getvalue(), manifest)


def test_tar_denies_extra_file_and_duplicate_entry(manifest, archive):
    for relative in ("tools/evil.py", manifest["files"][0]["path"]):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as target:
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as original:
                for item in original:
                    target.addfile(item, original.extractfile(item)
                                   if item.isfile() else None)
            bad = sparse._tarinfo(relative, file=True, size=1)
            target.addfile(bad, io.BytesIO(b"z"))
        with pytest.raises(sparse.SparseSourceDenied):
            sparse.verify_package(output.getvalue(), manifest)


def test_tar_denies_file_hash_drift(manifest, archive):
    data = bytearray(archive)
    needle = blobs(SHA, manifest["files"][0]["path"])
    offset = data.find(needle)
    assert offset >= 0
    data[offset] ^= 1
    with pytest.raises(sparse.SparseSourceDenied, match="FILE_TAMPERED"):
        sparse.verify_package(bytes(data), manifest)


def test_tar_denies_untrusted_mode(manifest, archive):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as target:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as original:
            for member in original:
                changed = deepcopy(member)
                if changed.isfile():
                    changed.mode = 0o666
                target.addfile(changed, original.extractfile(member)
                               if member.isfile() else None)
    with pytest.raises(sparse.SparseSourceDenied):
        sparse.verify_package(output.getvalue(), manifest)


def test_manifest_refuses_authority_injection_or_digest_replacement(manifest):
    for key, value in (
        ("owner_release_required", False),
        ("root_install_authorized", True),
        ("production_core_changes", True),
        ("target", "/opt/jason/current"),
        ("scope_sha256", "0" * 64),
        ("files", manifest["files"][:-1]),
    ):
        attempt = deepcopy(manifest)
        attempt[key] = value
        with pytest.raises(sparse.SparseSourceDenied):
            sparse.validate_manifest(attempt)


def test_changed_blob_between_manifest_and_package_is_rejected(manifest):
    def tampered(revision: str, path: str) -> bytes:
        return b"wrong"
    with pytest.raises(sparse.SparseSourceDenied, match="CHANGED_DURING_PACKAGE"):
        sparse.package_bytes(manifest, tampered)


def test_package_does_not_implicitly_install_or_authorize():
    assert sparse.PRODUCTION_APPLY_SUPPORTED is False
    assert not hasattr(sparse, "install_production")
    assert not hasattr(sparse, "deploy_mcp")


def _container(*, new: bool = False) -> dict:
    state = {
        "Id": "replacement-id" if new else "original-id",
        "Image": IMAGE,
        "State": {"Status": "running"},
        "Config": {
            "Env": [
                "JASON_SOURCE_REVISION=" + LKG,
                issuer.FLAG + ("=true" if new else "=false"),
                "JASON_OWNER_RELEASE_ED25519_KEY_PATH=" + issuer.SIGNER_DEST,
                "JASON_PMV4_OWNER_ISSUER_ENABLED=false",
                "CONSTANT_CONTACT_PROFILE=untouched",
            ],
            "User": "1000:1000",
            "Labels": {"com.teamaot.jason.source_revision": LKG},
        },
        "Mounts": [
            {"Type": "bind", "Source": issuer.SIGNER_SRC,
             "Destination": issuer.SIGNER_DEST, "RW": False},
            {"Type": "bind", "Source": "/provider/current",
             "Destination": "/run/provider/current", "RW": False},
        ],
        "NetworkSettings": {"Networks": {"jason-network": {}}},
        "HostConfig": {
            "ReadonlyRootfs": True, "Privileged": False,
            "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
        },
    }
    return state


def _before():
    item = _container()
    return {
        "mcp_id": item["Id"], "runtime_id": "runtime-id",
        "mcp": item, "env": issuer.env_map(item),
        "mounts": issuer.mounts(item),
        "networks": issuer.networks(item), "source_sha": LKG,
    }


def test_issuer_accepts_only_same_image_and_one_flag():
    issuer.verify_changed_only_one_flag(_before(), _container(new=True))


@pytest.mark.parametrize("mutation", [
    lambda c: c["Config"]["Env"].append("OTHER_FEATURE=true"),
    lambda c: c["Config"]["Env"].append(issuer.FLAG + "=false"),
    lambda c: c["Mounts"].append({"Type": "bind", "Source": "/etc",
                                  "Destination": "/container/etc", "RW": True}),
    lambda c: c["NetworkSettings"]["Networks"].update({"untrusted": {}}),
    lambda c: c["HostConfig"].update({"ReadonlyRootfs": False}),
    lambda c: c["Config"].update({"User": "0:0"}),
    lambda c: c.update({"Image": "sha256:" + "f" * 64}),
    lambda c: c["Config"]["Labels"].update({"unreviewed": "true"}),
])
def test_issuer_rejects_every_unrelated_container_change(mutation):
    after = _container(new=True)
    mutation(after)
    with pytest.raises(issuer.IssuerActivationDenied):
        issuer.verify_changed_only_one_flag(_before(), after)


def test_issuer_rejects_identity_reuse_and_duplicate_env():
    after = _container(new=True)
    after["Id"] = "original-id"
    with pytest.raises(issuer.IssuerActivationDenied):
        issuer.verify_changed_only_one_flag(_before(), after)
    after = _container(new=True)
    after["Config"]["Env"].append(issuer.FLAG + "=true")
    with pytest.raises(issuer.IssuerActivationDenied, match="ENV_DUPLICATE"):
        issuer.env_map(after)


def test_uninstalled_source_may_not_execute_as_root(monkeypatch):
    # Even if a privileged test harness fakes effective UID, neither a
    # source checkout nor a normal Python process can invoke the mutation.
    monkeypatch.setattr(issuer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(issuer.sys, "flags", type("Flags", (), {"isolated": 1})())
    monkeypatch.setattr(issuer, "INSTALLED", Path("/root/definitely-not-source.py"))
    with pytest.raises(issuer.IssuerActivationDenied, match="ROOT_INSTALLED"):
        issuer.execute()


def test_issuer_policy_requires_exact_flag_and_locked_source(monkeypatch):
    policy = {
        "schema_version": "1.0", "exact_action": issuer.ACTION,
        "component": "pmv4-stage-a0-owner-issuer",
        "one_shot": True, "source_sha": LKG,
        "mcp_image_sha256": IMAGE, "runtime_image_sha256": RUNTIME_IMAGE,
        "freeze_sha256": FREEZE, "promotion_hold_sha256": FREEZE,
        "script_sha256": sha256(b"script").hexdigest(),
        "trusted_auth_sha256": sha256(b"auth").hexdigest(),
        "native_deployer_sha256": sha256(b"deployer").hexdigest(),
        "owner_release_verifier_sha256": sha256(b"verify").hexdigest(),
        "change": "same-mcp-image-one-env-flag-only",
        "owner_authentication": "fresh-entra-oauth-exact-action",
        "production_services": [issuer.LIVE], "provider_writes": False,
    }
    data = {
        issuer.POLICY: json.dumps(policy).encode(),
        issuer.INSTALLED: b"script",
        issuer.AUTH: b"auth",
        issuer.DEPLOYER: b"deployer",
        issuer.OWNER_VERIFIER: b"verify",
    }
    monkeypatch.setattr(issuer, "read_root_file", lambda path, **kw: data[path])
    assert issuer.trusted_policy()["source_sha"] == LKG
    for item, value in (("one_shot", False), ("provider_writes", True),
                        ("production_services", [issuer.LIVE, issuer.RUNTIME]),
                        ("script_sha256", "0" * 64),
                        ("change", "replace-runtime-too")):
        copy = dict(policy)
        copy[item] = value
        data[issuer.POLICY] = json.dumps(copy).encode()
        with pytest.raises(issuer.IssuerActivationDenied):
            issuer.trusted_policy()
    data[issuer.POLICY] = json.dumps(policy).encode()


def test_issuer_unsigned_external_request_has_no_alternate_execution_path():
    assert issuer.ACTION == "pmv4-stage-a0-same-image-owner-issuer-v1"
    assert issuer.ROLLBACK != issuer.LIVE
    assert issuer.DEPLOYER.as_posix().startswith("/usr/local/lib/jason/")
    assert issuer.FLAG not in ("JASON_SOURCE_REVISION", "JASON_PMV4_OWNER_ISSUER_ENABLED")


def test_issuer_owner_ed25519_proof_binds_exact_single_flag():
    from datetime import datetime, timezone
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from implementation.kernel import signed_owner_release as native

    key = Ed25519PrivateKey.generate()
    policy = {
        "source_sha": LKG,
        "runtime_image_sha256": RUNTIME_IMAGE,
        "mcp_image_sha256": IMAGE,
        "freeze_sha256": FREEZE,
    }
    at = datetime.now(timezone.utc)
    oid = native.OWNER_OID
    proof = issuer.issue_bound_proof(
        oid, policy, module=native, signer=key, trust=key.public_key(), at=at,
    )
    assert proof["payload"]["owner_oid"] == oid
    assert proof["payload"]["one_release_only"] is True
    assert proof["payload"]["scope_sha256"] == issuer.action_scope_sha256(policy)
    for changed in (
        {**policy, "mcp_image_sha256": RUNTIME_IMAGE},
        {**policy, "source_sha": SHA},
        {**policy, "freeze_sha256": "f" * 64},
    ):
        with pytest.raises(native.OwnerReleaseProofDenied,
                           match="TRANSACTION_BINDING_MISMATCH"):
            native.verify_exact_owner_release(
                proof, public_key=key.public_key(),
                expected_candidate_sha=changed["source_sha"],
                expected_rollback_sha=changed["source_sha"],
                expected_release_id="release-" + changed["source_sha"][:16],
                expected_scope_sha256=issuer.action_scope_sha256(changed),
                expected_manifest_sha256=proof["payload"]["manifest_sha256"],
                expected_freeze_sha256=changed["freeze_sha256"],
                at=at,
            )


def test_issuer_owner_proof_rejects_wrong_root_trust():
    from datetime import datetime, timezone
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from implementation.kernel import signed_owner_release as native

    signing = Ed25519PrivateKey.generate()
    foreign = Ed25519PrivateKey.generate()
    policy = {
        "source_sha": LKG,
        "runtime_image_sha256": RUNTIME_IMAGE,
        "mcp_image_sha256": IMAGE,
        "freeze_sha256": FREEZE,
    }
    with pytest.raises(native.OwnerReleaseProofDenied):
        issuer.issue_bound_proof(
            native.OWNER_OID, policy, module=native,
            signer=signing, trust=foreign.public_key(),
            at=datetime.now(timezone.utc),
        )


def test_disposable_sparse_stage_and_exact_empty_rollback(tmp_path, manifest, archive):
    sandbox = tmp_path / "isolated"
    sandbox.mkdir(mode=0o700)
    result = sparse.stage_disposable(sandbox, manifest, archive)
    assert result["status"] == "exact_sparse_source_verified"
    sparse.verify_disposable(sandbox, manifest)
    end = sparse.rollback_disposable(sandbox, manifest)
    assert end["status"] == "verified_sparse_absence_rollback"
    assert not (sandbox / "opt").exists()


def test_disposable_rollback_fails_closed_on_foreign_file(tmp_path, manifest, archive):
    sandbox = tmp_path / "isolated"
    sandbox.mkdir(mode=0o700)
    sparse.stage_disposable(sandbox, manifest, archive)
    target = sandbox / "opt/jason/releases" / SHA
    unexpected = target / "tools/foreign.py"
    unexpected.write_text("unowned")
    with pytest.raises(sparse.SparseSourceDenied, match="FOREIGN_FILE"):
        sparse.rollback_disposable(sandbox, manifest)
    assert unexpected.read_text() == "unowned"


def test_disposable_rollback_fails_closed_on_digest_drift(tmp_path, manifest, archive):
    sandbox = tmp_path / "isolated"
    sandbox.mkdir(mode=0o700)
    sparse.stage_disposable(sandbox, manifest, archive)
    target = sandbox / "opt/jason/releases" / SHA
    path = target / manifest["files"][0]["path"]
    path.chmod(0o600)
    path.write_text("tampered")
    path.chmod(0o444)
    with pytest.raises(sparse.SparseSourceDenied, match="FOREIGN_FILE"):
        sparse.rollback_disposable(sandbox, manifest)
    assert path.exists()


def test_disposable_interruption_recovers_only_verifiable_objects(tmp_path, manifest, archive):
    sandbox = tmp_path / "isolated"
    sandbox.mkdir(mode=0o700)
    with pytest.raises(InterruptedError):
        sparse.stage_disposable(sandbox, manifest, archive, stop_after=2)
    sparse.verify_disposable(sandbox, manifest, partial=True)
    assert sparse.rollback_disposable(sandbox, manifest, partial=True)["status"] == (
        "verified_sparse_absence_rollback"
    )
    assert not (sandbox / "opt").exists()


def test_disposable_root_metadata_only_on_root_ci(tmp_path, manifest, archive):
    import os
    sandbox = tmp_path / "isolated"
    sandbox.mkdir(mode=0o700)
    if os.geteuid() != 0:
        with pytest.raises(sparse.SparseSourceDenied, match="ROOT_CI_ONLY"):
            sparse.stage_disposable(sandbox, manifest, archive,
                                    root_metadata=True)
    else:
        result = sparse.stage_disposable(sandbox, manifest, archive,
                                         root_metadata=True)
        assert result["source_sha"] == SHA
        sparse.verify_disposable(sandbox, manifest, root_metadata=True)
        assert sparse.rollback_disposable(sandbox, manifest,
                                          root_metadata=True)["status"] == (
            "verified_sparse_absence_rollback"
        )


def test_disposable_rejects_existing_release_and_system_paths(tmp_path, manifest, archive):
    with pytest.raises(sparse.SparseSourceDenied, match="DISPOSABLE_TEST_ROOT"):
        sparse.stage_disposable(Path("/opt/jason/releases"), manifest, archive)
    sandbox = tmp_path / "isolated"
    sandbox.mkdir(mode=0o700)
    sparse.stage_disposable(sandbox, manifest, archive)
    with pytest.raises(sparse.SparseSourceDenied, match="ALREADY_EXISTS"):
        sparse.stage_disposable(sandbox, manifest, archive)


def test_sparse_source_paths_match_native_root_stage_a0_contract():
    from tools import pmv4_stage_a_packet as native
    assert sparse.required_paths() == tuple(sorted(
        set(native.BUNDLE_FILES) | set(native.ROOT_STAGE_A_REQUIRED_SOURCES)
    ))


def test_operator_sparse_git_read_pins_safe_directory(monkeypatch, tmp_path):
    from unittest.mock import patch
    commands = []
    def show(argv, timeout):
        commands.append((argv, timeout))
        return b"immutable"
    with patch.object(sparse.subprocess, "check_output", show):
        reader = sparse.git_object(tmp_path)
        assert reader(SHA, "tools/pmv4_stage_a_native_install.py") == b"immutable"
    assert commands[0][0][:5] == [
        "git", "-c", f"safe.directory={tmp_path}",
        "-C", str(tmp_path),
    ]
    assert commands[0][0][-1] == SHA + ":tools/pmv4_stage_a_native_install.py"
