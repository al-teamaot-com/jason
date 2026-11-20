from hashlib import sha256
import io
import json
import os
from pathlib import PurePosixPath
import tarfile

import pytest

from tools import pmv4_e_dispatch_install as install


@pytest.fixture
def files():
    return {name: name.encode() for name in
            [install.WORKER_SOURCE, *install.CONTROLS.values()]}


def archive(files, invalid=None):
    output = io.BytesIO()
    prefix = PurePosixPath(install.PREFIX)
    directories = {prefix}
    for name in files:
        directories.update(parent for parent in (prefix / name).parents
                           if parent.as_posix().startswith(install.PREFIX))
    with tarfile.open(fileobj=output, mode="w") as tar:
        for name in sorted(directories):
            item = tarfile.TarInfo(str(name))
            item.type = tarfile.DIRTYPE
            item.mode = 0o555
            tar.addfile(item)
        for name, raw in files.items():
            item = tarfile.TarInfo(str(prefix / name))
            item.mode = 0o444
            item.size = len(raw)
            tar.addfile(item, io.BytesIO(raw))
        if invalid:
            tar.addfile(invalid)
    return output.getvalue()


def test_archive_is_exact(files):
    assert install.decode_archive(
        archive(files), {name: sha256(data).hexdigest() for name, data in files.items()}
    ) == files


@pytest.mark.parametrize("bad", ["../escape", "tools/link", "tools/extra"])
def test_archive_rejects_traversal_links_and_unreviewed_content(files, bad):
    item = tarfile.TarInfo(install.PREFIX + "/" + bad)
    item.type = tarfile.SYMTYPE if bad.endswith("link") else tarfile.REGTYPE
    item.linkname = "/etc/example"
    item.mode = 0o444
    with pytest.raises(install.Denied, match="ARCHIVE_"):
        install.decode_archive(
            archive(files, item), {name: sha256(data).hexdigest() for name, data in files.items()}
        )


@pytest.fixture
def isolated(tmp_path, monkeypatch, files):
    if os.geteuid() != 0:
        pytest.skip("sealed-directory swaps require the disposable UID0 runner")
    base = tmp_path / "bootstrap"
    base.mkdir()
    trust = base / "trusted"
    install.stage_tree(trust, {"tools/old.py": b"old"})
    worker = tmp_path / "worker.py"
    worker.write_bytes(b"old worker")
    worker.chmod(0o755)
    policy = tmp_path / "policy.json"
    records = tmp_path / "authority" / "records"
    monkeypatch.setattr(install, "BASE", base)
    monkeypatch.setattr(install, "TRUST", trust)
    monkeypatch.setattr(install, "WORKER", worker)
    monkeypatch.setattr(install, "WORKER_BEFORE", install.digest(worker.read_bytes()))
    monkeypatch.setattr(install, "POLICY", policy)
    monkeypatch.setattr(install, "RECORDS", records)
    monkeypatch.setattr(install, "protected", lambda: None)
    previous = install.tree(trust)
    data = {"candidate_sha": "7" * 40}
    receipt = {"scope": {"trust_before_sha256": previous, "policy": data},
               "owner_object_id": "fixture-owner"}
    return files, data, receipt, previous, base


def test_install_and_reversible_readback(isolated):
    files, policy, receipt, previous, base = isolated
    install.install(files, policy, receipt, previous)
    assert install.WORKER.read_bytes() == files[install.WORKER_SOURCE]
    assert json.loads(install.POLICY.read_bytes()) == policy
    assert install.tree(install.TRUST) != previous
    assert install.RECORDS.is_dir()
    install.rollback(files, policy, receipt["scope"])
    assert install.WORKER.read_bytes() == b"old worker"
    assert install.tree(install.TRUST) == previous
    assert not install.RECORDS.parent.exists()
    assert not install.POLICY.exists()
    assert len(list(base.glob("*/rolled-back.json"))) == 1


def test_failed_postcheck_restores_before_images(isolated, monkeypatch):
    files, policy, receipt, previous, base = isolated

    def gate():
        if install.POLICY.exists():
            raise install.Denied("SIMULATED_POSTCHECK_DENIAL")

    monkeypatch.setattr(install, "protected", gate)
    with pytest.raises(install.Denied, match="POSTCHECK"):
        install.install(files, policy, receipt, previous)
    assert install.tree(install.TRUST) == previous
    assert install.WORKER.read_bytes() == b"old worker"
    assert not install.POLICY.exists()
    assert len(list(base.glob("*/rolled-back.json"))) == 1


def test_rollback_denies_a_dispatched_approval(isolated):
    files, policy, receipt, previous, _ = isolated
    install.install(files, policy, receipt, previous)
    (install.RECORDS / "existing.json").write_text("{}")
    with pytest.raises(install.Denied, match="APPROVAL_ALREADY_DISPATCHED"):
        install.rollback(files, policy, receipt["scope"])
    assert install.WORKER.read_bytes() == files[install.WORKER_SOURCE]
    assert install.POLICY.exists()


@pytest.fixture
def repair(isolated, monkeypatch):
    files, policy, receipt, previous, base = isolated
    install.install(files, policy, receipt, previous)
    installed_tree = install.tree(install.TRUST)
    monkeypatch.setattr(install, "REPAIR_FROM", policy["candidate_sha"])
    monkeypatch.setattr(install, "REPAIR_WORKER", install.digest(install.WORKER.read_bytes()))
    monkeypatch.setattr(install, "REPAIR_POLICY", install.digest(install.POLICY.read_bytes()))
    monkeypatch.setattr(install, "REPAIR_TREE", installed_tree)
    updated = {name: data + b" updated" for name, data in files.items()}
    policy = {"candidate_sha": "8" * 40}
    receipt = {
        "scope": {"trust_before_sha256": installed_tree, "queue_cutover": True,
                  "policy": policy},
        "owner_object_id": "fixture-owner",
    }
    return updated, policy, receipt, installed_tree, base


def test_repair_preserves_original_policy_and_approval_state_on_rollback(repair):
    files, policy, receipt, before, _ = repair
    previous_policy = install.POLICY.read_bytes()
    previous_worker = install.WORKER.read_bytes()
    install.install(files, policy, receipt, before)
    assert install.WORKER.read_bytes() == files[install.WORKER_SOURCE]
    assert json.loads(install.POLICY.read_bytes()) == policy
    install.rollback(files, policy, receipt["scope"])
    assert install.POLICY.read_bytes() == previous_policy
    assert install.WORKER.read_bytes() == previous_worker
    assert install.tree(install.TRUST) == before
    assert install.RECORDS.is_dir()


def test_failed_repair_restores_exact_prior_dispatcher(repair, monkeypatch):
    files, policy, receipt, before, _ = repair
    previous_policy = install.POLICY.read_bytes()
    previous_worker = install.WORKER.read_bytes()

    def postcheck():
        if install.POLICY.read_bytes() != previous_policy:
            raise install.Denied("REPAIR_POSTCHECK_FAILED")

    monkeypatch.setattr(install, "protected", postcheck)
    with pytest.raises(install.Denied, match="POSTCHECK"):
        install.install(files, policy, receipt, before)
    assert install.POLICY.read_bytes() == previous_policy
    assert install.WORKER.read_bytes() == previous_worker
    assert install.tree(install.TRUST) == before
    assert install.RECORDS.is_dir()


def test_repair_rejects_changed_prior_policy_before_mutation(repair):
    files, policy, receipt, before, _ = repair
    install.POLICY.chmod(0o600)
    install.POLICY.write_text('{"candidate_sha":"tampered"}')
    install.POLICY.chmod(0o400)
    worker_before = install.WORKER.read_bytes()
    with pytest.raises(install.Denied, match="BASELINE_CHANGED"):
        install.install(files, policy, receipt, before)
    assert install.WORKER.read_bytes() == worker_before
    assert install.tree(install.TRUST) == before


@pytest.mark.parametrize("valid", [True, False])
def test_combined_cutover_uses_original_signer_and_publisher(monkeypatch, valid):
    from pathlib import Path
    from types import SimpleNamespace

    policy = {"candidate_sha": "a" * 40}
    oid = "fixture-owner"
    publisher = (Path(__file__).resolve().parents[2] /
                 "implementation/mcp_service/src/jason_mcp/pmv4_stage_a0_owner_issuer.py").read_bytes()
    monkeypatch.setattr(install, "read", lambda *args: publisher)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        supplied_policy, actor, source = json.loads(kwargs["input"])
        assert supplied_policy == policy and actor == oid
        assert source.encode() == publisher
        assert "offer.signed_request(" in command[8]
        assert 'publisher["_publish_exact_request"]' in command[8]
        return SimpleNamespace(stdout=json.dumps({
            "request_id": "pmv4-e-" + "a" * 16 + "-" + "b" * 32 if valid else "invalid",
            "candidate_sha": policy["candidate_sha"],
        }).encode())

    monkeypatch.setattr(install.subprocess, "run", run)
    if valid:
        assert install.queue_cutover(policy, oid)["candidate_sha"] == policy["candidate_sha"]
    else:
        with pytest.raises(install.Denied, match="READBACK_INVALID"):
            install.queue_cutover(policy, oid)
    assert calls[0][0][:4] == ["/usr/sbin/runuser", "-u", "al", "--"]


@pytest.mark.parametrize("failure", ["native_denial", "wrong_status", None])
def test_combined_decision_requires_readonly_privileged_preflight(monkeypatch, failure):
    from types import SimpleNamespace

    def run(command, **kwargs):
        assert command[:3] == ["/usr/bin/python3", "-I", "-B"]
        assert "gate.evaluate(gate.collect())" in command[4]
        return SimpleNamespace(
            returncode=1 if failure == "native_denial" else 0,
            stderr=b"GateDenied: live prerequisite unavailable",
            stdout=json.dumps({
                "status": "wrong" if failure == "wrong_status" else
                          "read_only_root_preflight_source_conditions_passed",
                "production_mutations": False,
            }).encode(),
        )

    monkeypatch.setattr(install.subprocess, "run", run)
    if failure:
        with pytest.raises(install.Denied, match="PREFLIGHT"):
            install.cutover_preflight()
    else:
        install.cutover_preflight()


@pytest.fixture
def isolated_cutover(repair, monkeypatch, tmp_path):
    files, policy, receipt, before, base = repair
    install.WORKER.chmod(0o755)
    install.WORKER.write_bytes(b"old worker")
    catalog = tmp_path / "catalog.json"
    catalog.write_bytes(install.canonical({"root_worker_sha256": install.WORKER_BEFORE}))
    catalog.chmod(0o600)
    monkeypatch.setattr(install, "CATALOG_POLICY", catalog)
    return files, policy, receipt, before, base, catalog


def test_isolated_install_preserves_shared_worker_and_catalog(isolated_cutover):
    files, policy, receipt, before, base, catalog = isolated_cutover
    worker_before = install.WORKER.read_bytes()
    catalog_before = catalog.read_bytes()
    state = install.install_isolated_source(files, policy, receipt["scope"], "fixture-owner")
    assert install.WORKER.read_bytes() == worker_before
    assert catalog.read_bytes() == catalog_before
    assert json.loads(install.POLICY.read_bytes()) == policy
    assert install.tree(state / "trust-before") == before
    assert install.tree(install.TRUST) != before
    assert json.loads((state / "approval.json").read_bytes())["owner_object_id"] == "fixture-owner"


def test_isolated_install_rolls_back_preparation_on_postcheck_failure(isolated_cutover, monkeypatch):
    files, policy, receipt, before, base, catalog = isolated_cutover
    old_policy = install.POLICY.read_bytes()
    catalog_before = catalog.read_bytes()

    def failed():
        raise install.Denied("SIMULATED_ISOLATED_POSTCHECK")

    monkeypatch.setattr(install, "protected", failed)
    with pytest.raises(install.Denied, match="POSTCHECK"):
        install.install_isolated_source(files, policy, receipt["scope"], "fixture-owner")
    assert install.POLICY.read_bytes() == old_policy
    assert install.tree(install.TRUST) == before
    assert install.WORKER.read_bytes() == b"old worker"
    assert catalog.read_bytes() == catalog_before


def test_isolated_install_rejects_catalog_drift_before_mutation(isolated_cutover):
    files, policy, receipt, before, base, catalog = isolated_cutover
    catalog.chmod(0o600)
    catalog.write_text('{"root_worker_sha256":"changed"}')
    with pytest.raises(install.Denied, match="CATALOG_SHARED_WORKER_PIN_CHANGED"):
        install.install_isolated_source(files, policy, receipt["scope"], "fixture-owner")
    assert install.tree(install.TRUST) == before
    assert not (base / ("isolated-cutover-" + policy["candidate_sha"])).exists()


@pytest.mark.parametrize("native_status", [
    "native_stage_e_six_unit_accepted", "native_stage_e_six_unit_rollback_verified",
])
def test_isolated_native_distinguishes_acceptance_from_rollback(tmp_path, monkeypatch, native_status):
    from types import SimpleNamespace
    candidate = "a" * 40
    request = {"signed_owner_proof": {"payload": {"approval_id": "fixture"}}}
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["input"] == install.canonical(request)
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "candidate_sha": candidate, "status": native_status,
        }).encode())

    monkeypatch.setattr(install.subprocess, "run", run)
    if native_status.endswith("_accepted"):
        assert install.run_isolated_native(candidate, request, tmp_path)["status"] == native_status
    else:
        with pytest.raises(install.Denied, match="NOT_ACCEPTED"):
            install.run_isolated_native(candidate, request, tmp_path)
    assert len(calls) == 1
    assert json.loads((tmp_path / "native-result.json").read_bytes())["status"] == native_status


def test_isolated_native_failure_uses_original_signed_inert_recovery(tmp_path, monkeypatch):
    from types import SimpleNamespace
    request = {"signed_owner_proof": {"payload": {"approval_id": "fixture"}}}
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=2 if len(calls) == 1 else 0, stdout=b"{}")

    monkeypatch.setattr(install.subprocess, "run", run)
    with pytest.raises(install.Denied, match="CUTOVER_FAILED"):
        install.run_isolated_native("a" * 40, request, tmp_path)
    assert calls[0][0][-2:] == ["--stage-and-promote", "--owner-request-stdin"]
    assert calls[1][0][-2:] == ["--recover-inert", "--owner-request-stdin"]
    assert calls[0][1]["input"] == calls[1][1]["input"] == install.canonical(request)
    assert json.loads((tmp_path / "failed-native-attempt.json").read_bytes())[
        "owner_approval_reusable"] is False


@pytest.mark.parametrize("changed", [False, True])
def test_isolated_signer_keeps_exact_scope(monkeypatch, changed):
    from types import SimpleNamespace
    policy = {key: str(index) * size for index, (key, size) in enumerate([
        ("candidate_sha", 40), ("rollback_sha", 40), ("scope_sha256", 64),
        ("manifest_sha256", 64), ("freeze_sha256", 64),
    ], 1)}

    def run(command, **kwargs):
        assert command[:4] == ["/usr/sbin/runuser", "-u", "al", "--"]
        assert "offer.checked_identity()" in command[8]
        supplied_policy, actor = json.loads(kwargs["input"])
        assert supplied_policy == policy and actor == "fixture-owner"
        result = dict(policy)
        if changed:
            result["scope_sha256"] = "changed"
        return SimpleNamespace(stdout=json.dumps(result).encode())

    monkeypatch.setattr(install.subprocess, "run", run)
    if changed:
        with pytest.raises(install.Denied, match="SIGNER_SCOPE_CHANGED"):
            install.signed_cutover_request(policy, "fixture-owner")
    else:
        assert install.signed_cutover_request(policy, "fixture-owner") == policy


def test_isolated_unit_scope_contains_all_twelve_installed_files():
    from tools import pmv4_e_replacement_unit_bundle as bundle
    targets = install.replacement_unit_targets(bundle.generate())
    assert len(targets) == len(set(targets)) == 12
    assert "/etc/systemd/system/jason-pmv4-component-reconcile.service" in targets
    assert "/home/al/.config/systemd/user/jason-pmv4-engineering.timer" in targets
    with pytest.raises(install.Denied, match="SCOPE_INCOMPLETE"):
        install.replacement_unit_targets({})


@pytest.mark.parametrize("denied",[False,True])
def test_new_reviewed_preflight_is_volatile_and_preserves_installed_trust(isolated,monkeypatch,tmp_path,denied):
    from pathlib import Path
    from types import SimpleNamespace
    files,policy,receipt,before,base=isolated
    temporary=tmp_path/"volatile"
    temporary.mkdir(mode=0o700)
    monkeypatch.setattr(install,"PREFLIGHT_TMP",temporary)
    called=[]

    def run(command,**kwargs):
        source=Path(command[-1])
        called.append(source)
        assert source != install.TRUST
        assert source.parent.parent==temporary
        assert (source/"tools/pmv4_e_root_bootstrap_once.py").read_bytes()==files[
            "tools/pmv4_e_root_bootstrap_once.py"]
        assert source.stat().st_uid==0 and source.stat().st_mode & 0o777==0o555
        assert source.parent.stat().st_mode & 0o777==0o700
        assert install.tree(install.TRUST)==before
        return SimpleNamespace(
            returncode=2 if denied else 0,stderr=b"RootPreflightDenied: exact denial",
            stdout=json.dumps({"status":"read_only_root_preflight_source_conditions_passed",
                               "production_mutations":False}).encode())

    monkeypatch.setattr(install.subprocess,"run",run)
    if denied:
        with pytest.raises(install.Denied,match="CUTOVER_PREFLIGHT"):
            install.cutover_preflight(files)
    else:
        install.cutover_preflight(files)
    assert len(called)==1
    assert not called[0].exists()
    assert not list(temporary.iterdir())
    assert install.tree(install.TRUST)==before
    assert not install.POLICY.exists()
    assert install.WORKER.read_bytes()==b"old worker"
