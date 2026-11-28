from copy import deepcopy
from hashlib import sha256
import json

import pytest

from tools import scoped_backport_controller_upgrade as upgrade
from tools.scoped_backport_release import ScopedBackportDenied


def make_plan(*, prior=b"previous controller", pinned=True):
    policy = dict.fromkeys(upgrade.REUSABLE_POLICY_FIELDS)
    policy.update(
        schema_version="3.0",
        per_release_review_required=True,
        file_sha256={"host": sha256(prior).hexdigest() if pinned else "0" * 64},
    )
    return upgrade.plan_upgrade("a" * 40, "b" * 40, prior, b"previous controller",
                                b"new controller", json.dumps(policy).encode())


def test_scope_changes_only_controller_pin_and_preserves_rollback():
    plan = make_plan()
    old, new = map(json.loads, (plan.files[1].before, plan.files[1].after))
    expected = deepcopy(old)
    expected["file_sha256"]["host"] = sha256(plan.files[0].after).hexdigest()
    assert new == expected
    assert plan.scope()["files"][1]["before_sha256"] == sha256(plan.files[1].before).hexdigest()


@pytest.mark.parametrize("args", [{"prior": b"foreign"}, {"pinned": False}])
def test_foreign_controller_or_policy_denied(args):
    with pytest.raises(ScopedBackportDenied):
        make_plan(**args)


@pytest.mark.parametrize("fault", ["claim", "second_replace", "verify", None])
def test_upgrade_and_rollback_with_disposable_files(tmp_path, fault):
    plan = make_plan()
    paths = {file.path: tmp_path / file.path.name for file in plan.files}
    for file in plan.files:
        paths[file.path].write_bytes(file.before)
    calls = []

    def claim(received):
        assert received.scope_sha256 == plan.scope_sha256
        assert all(paths[file.path].read_bytes() == file.before for file in plan.files)
        calls.append("claim")
        if fault == "claim":
            raise RuntimeError("approval denied")

    def replace(path, before, after, mode):
        assert paths[path].read_bytes() == before
        if fault == "second_replace" and path == upgrade.POLICY:
            raise RuntimeError("second write interrupted")
        paths[path].write_bytes(after)

    def restore(changes):
        for path, before, after, mode in reversed(changes):
            actual = paths[path].read_bytes()
            assert actual in (before, after)
            paths[path].write_bytes(before)

    def verify(received, rolled_back):
        assert received == plan
        for file in plan.files:
            assert paths[file.path].read_bytes() == (file.before if rolled_back else file.after)
        if fault == "verify" and not rolled_back:
            raise RuntimeError("verification failed")

    def run():
        upgrade.apply_under_held_transaction(
            plan, revalidate=lambda: plan, consume_and_record_rollback=claim,
            replace=replace, restore=restore, verify=verify,
        )

    if fault:
        with pytest.raises(RuntimeError):
            run()
    else:
        run()
    assert calls == ["claim"]
    assert all(paths[file.path].read_bytes() == (file.before if fault else file.after)
               for file in plan.files)


@pytest.mark.parametrize("fault", ["approval", "quiescence", "replacement", None])
def test_root_adapter_checks_scope_and_restores_listeners(monkeypatch, tmp_path, fault):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from tools import scoped_backport_controller_upgrade_root as root

    plan = make_plan()
    manifest = {"release_id": "prior"}
    scope = dict(plan.scope(), installer_sha="c" * 40, reviewed_sha="d" * 40)
    approval_id = "owner-mcp-" + "3" * 32
    ledger = tmp_path / "ledger"
    consumed = tmp_path / "consumed.json"
    listener = "active"
    contents = {item.path: item.before for item in plan.files}
    host = SimpleNamespace(
        release_lock=lambda _: nullcontext(),
        snapshot_protected=lambda: {"core": "same"},
        verify_protected_unchanged=lambda protected: protected == {"core": "same"},
    )

    def authorize(*args):
        if fault == "approval":
            raise PermissionError("denied")
        return approval_id

    def triggers(command):
        nonlocal listener
        listener = "active" if command == "start" else "inactive"

    def check_workers():
        assert listener == "inactive"
        if fault == "quiescence":
            raise RuntimeError("busy")

    def replace(path, before, after, mode):
        assert listener == "inactive" and consumed.is_file() and contents[path] == before
        if fault == "replacement" and path == upgrade.POLICY:
            raise RuntimeError("write interrupted")
        contents[path] = after

    def restore(changes):
        assert listener == "inactive"
        for path, before, after, _ in reversed(changes):
            assert contents[path] in (before, after)
            contents[path] = before

    def verify(current, rolled_back):
        assert listener == "active"
        assert all(contents[f.path] == (f.before if rolled_back else f.after) for f in current.files)

    monkeypatch.setattr(root, "LEDGER", ledger)
    monkeypatch.setattr(root, "state", lambda _: listener)
    monkeypatch.setattr(root, "terminal_offer", lambda: (host, manifest))
    monkeypatch.setattr(root, "make_plan", lambda *_: plan)
    monkeypatch.setattr(root, "maintenance_scope", lambda *_: scope)
    monkeypatch.setattr(root, "verify_decision", authorize)
    monkeypatch.setattr(root, "consumption_path", lambda _: consumed)
    monkeypatch.setattr(root, "set_triggers", triggers)
    monkeypatch.setattr(root, "check_workers", check_workers)
    monkeypatch.setattr(root, "atomic_exact_root_file", replace)
    monkeypatch.setattr(root, "restore_attempted_root_files", restore)
    monkeypatch.setattr(root, "verify_files", verify)
    monkeypatch.setattr(root.live.readback, "verify_live", lambda: None)
    monkeypatch.setattr(root.live, "root_directory", lambda path: path.is_dir())
    monkeypatch.setattr(root.live, "atomic_root_json", lambda path, data: path.write_text(json.dumps(data)))

    if fault:
        with pytest.raises((PermissionError, RuntimeError)):
            root.apply(plan, scope, {}, host, manifest)
    else:
        root.apply(plan, scope, {}, host, manifest)

    assert listener == "active"
    assert consumed.exists() == (fault != "approval")
    assert all(contents[f.path] == (f.before if fault else f.after) for f in plan.files)


@pytest.mark.parametrize("prior", ["pending", "foreign", "verified", "rolled_back"])
def test_maintenance_inspects_prior_transaction_without_scheduling(tmp_path, monkeypatch, prior):
    from types import SimpleNamespace
    from tools import scoped_backport_controller_upgrade_root as root

    manifest = dict(schema_version="3.0", release_id="prior", scope_sha256="a" * 64,
                    release_policy_sha256="b" * 64)
    path = tmp_path / "journal.json"
    host = SimpleNamespace(_journal_path=lambda _: path)
    monkeypatch.setattr(root.dispatcher, "load_installed", lambda: (host, manifest, {}))
    monkeypatch.setattr(root.dispatcher, "scheduled_approved",
                        lambda *args: pytest.fail("maintenance dispatched a release"))
    monkeypatch.setattr(root, "require_normal_deployment_enabled", lambda *args: None)
    monkeypatch.setattr(root.dispatcher, "AUTH", tmp_path)
    monkeypatch.setattr(root.live, "root_json", lambda p: json.loads(p.read_bytes()))
    if prior != "pending":
        path.write_text(json.dumps({
            "release_id": "prior", "manifest_sha256": root.digest(manifest),
            "scope_sha256": "foreign" if prior == "foreign" else manifest["scope_sha256"],
            "outcome": "production_components_verified" if prior == "verified" else "rollback_verified",
        }))
    checked = []
    monkeypatch.setattr(root, "verify_successful_predecessor", lambda *args: checked.append(args))
    if prior in ("rolled_back", "verified"):
        assert root.terminal_offer() == (host, manifest)
        assert len(checked) == int(prior == "verified")
    else:
        with pytest.raises(ScopedBackportDenied, match={
            "pending": "ACTIVE_RELEASE", "foreign": "SCOPE_MISMATCH",

        }[prior]):
            root.terminal_offer()


@pytest.mark.parametrize("change", ["none", "host", "image", "revision", "id", "configuration", "scope"])
def test_verified_prior_requires_live_evidence(monkeypatch, change):
    from tools import scoped_backport_controller_upgrade_root as root

    manifest = {"release_id": "prior", "scope_sha256": "scope", "release_policy_sha256": "policy",
                "targets": [{"name": "runtime"}], "protected_services": []}
    prior = dict(manifest, manifest_sha256=root.digest(manifest), host_revision="host",
                 components={"runtime": {"container_id": "old", "image_id": "image", "revision": "revision"}})
    current = deepcopy(prior)
    row = current["components"]["runtime"]
    row["container_id"] = "reconciled"
    if change in ("image", "revision"):
        row[{"image": "image_id", "revision": "revision"}[change]] = "changed"
    if change == "host":
        current["host_revision"] = "changed"
    if change == "scope":
        current["scope_sha256"] = "changed"
    monkeypatch.setattr(root.live.readback, "verify_live", lambda: current)
    monkeypatch.setattr(root.live.readback, "validate", lambda value: value)
    monkeypatch.setattr(root.live, "required_container",
                        lambda name: {"Id": "changed" if change == "id" else "reconciled"})
    monkeypatch.setattr(root.live, "config_fingerprint", lambda item: "changed" if change == "configuration" else "hash")
    journal = dict(proposed_readback=prior, mutation_attempted=True, original_configs={"runtime": "hash"},
                   protected_before={})
    if change == "none":
        root.verify_successful_predecessor(manifest, journal)
    else:
        with pytest.raises(ScopedBackportDenied):
            root.verify_successful_predecessor(manifest, journal)


@pytest.mark.parametrize("change", ["none", "peer_config", "peer_image", "peer_identity",
                                      "peer_snapshot_missing", "foreign_target", "missing_target"])
def test_verified_scoped_predecessor_checks_unchanged_peers(monkeypatch, change):
    from tools import scoped_backport_controller_upgrade_root as root
    manifest = {"release_id": "prior", "scope_sha256": "scope", "release_policy_sha256": "policy",
                "targets": [{"name": "runtime"}], "protected_services": ["gateway"]}
    prior = dict(manifest, manifest_sha256=root.digest(manifest), host_revision="host", components={
        "runtime": {"container_id": "target-before-boot", "image_id": "runtime-image", "revision": "runtime-rev"},
        "gateway": {"container_id": "peer-before-boot", "image_id": "gateway-image", "revision": "gateway-rev"},
    })
    current = deepcopy(prior)
    current["components"]["runtime"]["container_id"] = "target-live"
    current["components"]["gateway"]["container_id"] = "peer-live"
    journal = dict(proposed_readback=prior, mutation_attempted=True,
                   original_configs={"runtime": "runtime-old-hash"}, candidate_configs={"runtime": "runtime-new-hash"},
                   protected_before={"gateway": {"id": "peer-before-boot", "image": "gateway-image", "running": True,
                                                 "status": "running", "oom": False, "configuration_sha256": "gateway-hash"}})
    items = {"runtime": {"Id": "target-live", "fingerprint": "runtime-new-hash"},
             "gateway": {"Id": "peer-live", "fingerprint": "gateway-hash"}}
    if change == "peer_config": items["gateway"]["fingerprint"] = "foreign"
    elif change == "peer_image": journal["protected_before"]["gateway"]["image"] = "foreign"
    elif change == "peer_identity": journal["protected_before"]["gateway"]["id"] = "foreign"
    elif change == "peer_snapshot_missing": journal["protected_before"].clear()
    elif change == "foreign_target": journal["candidate_configs"]["gateway"] = "gateway-hash"
    elif change == "missing_target": journal["candidate_configs"].clear()
    monkeypatch.setattr(root.live.readback, "verify_live", lambda: current)
    monkeypatch.setattr(root.live.readback, "validate", lambda value: value)
    monkeypatch.setattr(root.live, "required_container", lambda name: items[name])
    monkeypatch.setattr(root.live, "config_fingerprint", lambda item: item["fingerprint"])
    if change == "none":
        root.verify_successful_predecessor(manifest, journal)
    else:
        with pytest.raises(ScopedBackportDenied):
            root.verify_successful_predecessor(manifest, journal)
