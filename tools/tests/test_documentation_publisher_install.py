"""Exact documentation component deployment boundaries; no live service calls."""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import json
import os
import stat

import pytest
from tools import documentation_publisher_install as d


def root_cli(monkeypatch, inspect, owner):
    monkeypatch.setattr(d, "os", SimpleNamespace(geteuid=lambda: 0))
    monkeypatch.setattr(d, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1)))
    monkeypatch.setattr(d, "primitives", lambda: ({}, {"locks": nullcontext, "owner": owner}))
    monkeypatch.setattr(d, "inspect", inspect)


def test_no_root_or_no_isolation_denies_before_loading_authority(monkeypatch):
    monkeypatch.setattr(d, "primitives", lambda: pytest.fail("authority loaded before root boundary"))
    with pytest.raises(d.DocumentationInstallDenied, match="ISOLATED_ROOT_REQUIRED"):
        d.main(["--source-sha", "a" * 40, "--apply"])


def test_preflight_never_requests_owner_or_constructs_mutation(monkeypatch, capsys):
    root_cli(monkeypatch, lambda *a: ({"action": d.ACTION}, {}),
             lambda *a: pytest.fail("preflight asked for Owner"))
    monkeypatch.setattr(d, "Package", lambda *a: pytest.fail("preflight reached mutation"))
    d.main(["--source-sha", "a" * 40])
    assert json.loads(capsys.readouterr().out)["status"] == "documentation_read_only_root_preflight_passed"


def test_owner_denial_precedes_package_or_service_operations(monkeypatch):
    def denied(scope):
        raise d.DocumentationInstallDenied("OWNER_DENIED")
    root_cli(monkeypatch, lambda *a: ({"action": d.ACTION}, {}), denied)
    monkeypatch.setattr(d, "Package", lambda *a: pytest.fail("mutation before Owner decision"))
    with pytest.raises(d.DocumentationInstallDenied, match="OWNER_DENIED"):
        d.main(["--source-sha", "a" * 40, "--apply"])


def test_scope_change_after_owner_denies_without_mutating_or_stopping_service(monkeypatch):
    seen = []
    calls = iter([({"action": d.ACTION}, {}), ({"action": "changed"}, {})])
    root_cli(monkeypatch, lambda *a: next(calls), lambda *a: "verified-owner")
    monkeypatch.setattr(d, "Package", lambda *a: SimpleNamespace(
        base_created=False, apply=lambda *a: seen.append("apply")))
    with pytest.raises(d.DocumentationInstallDenied, match="APPROVED_SCOPE_CHANGED"):
        d.main(["--source-sha", "a" * 40, "--apply"])
    assert seen == []


def test_production_transaction_rejects_alternate_destinations(tmp_path):
    with pytest.raises(d.DocumentationInstallDenied, match="PRODUCTION_PATH_OVERRIDE"):
        d.Package({}, "a" * 40, base=tmp_path, dropin=tmp_path / "foreign")


@pytest.fixture
def package(tmp_path):
    if os.geteuid() != 0:
        pytest.skip("disposable UID0 filesystem fixture")
    c, _ = d.primitives()
    base = tmp_path / "package"
    dropin = tmp_path / "service.d" / "reviewed.conf"
    return d.Package(c, "a" * 40, base=base, dropin=dropin, production=False)


def test_root_package_and_exact_override_restore_preserve_durable_approval(package):
    payload = {name: ("reviewed " + name).encode() for name in d.FILES}
    package.apply(payload, {"owner_oid": "verified-owner", "scope": "exact"})
    for name, raw in payload.items():
        path = package.base / package.source_sha / name
        assert path.read_bytes() == raw and path.stat().st_uid == 0
        assert stat.S_IMODE(path.stat().st_mode) == 0o444
    assert package.dropin.read_bytes() == d.dropin_bytes(package.source_sha)
    assert stat.S_IMODE((package.base / "approval.json").stat().st_mode) == 0o400
    package.restore()
    assert not package.dropin.exists() and not package.dropin.parent.exists()
    assert (package.base / "approval.json").is_file()


def test_foreign_override_is_never_overwritten_on_rollback(package):
    package.apply({name: b"reviewed" for name in d.FILES}, {})
    package.dropin.write_bytes(b"foreign")
    with pytest.raises(d.DocumentationInstallDenied, match="FOREIGN_SERVICE_OVERRIDE"):
        package.restore()
    assert package.dropin.read_bytes() == b"foreign"


def test_partial_source_copy_failure_never_activates_incomplete_package(package):
    real_write = package.c["write"]
    count = 0
    def fail(path, raw, *args):
        nonlocal count
        count += 1
        if count == 3:
            raise OSError("injected source-copy failure")
        return real_write(path, raw, *args)
    package.c = {**package.c, "write": fail}
    with pytest.raises(OSError):
        package.apply({name: b"reviewed" for name in d.FILES}, {})
    package.restore()
    assert package.base_created and not package.created
    assert not package.dropin.exists()
    assert (package.base / "approval.json").is_file()
