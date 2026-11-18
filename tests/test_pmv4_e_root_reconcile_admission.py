"""Root-host reconciliation preflight must never re-create old PMv3 workers.

Source tests only: root identity, marker, installed root trust are synthetic.
No real production services, Git releases, provider work or sudo calls.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import stat

import pytest

from tools import pmv4_e_root_reconcile_admission as rootguard


SOURCE=Path(__file__).resolve().parents[1]


@pytest.fixture
def marker(tmp_path,monkeypatch):
    p=tmp_path/"accepted.json"
    p.write_text('{"schema_version":"1.0"}')
    p.chmod(0o444)
    monkeypatch.setattr(rootguard.os,"geteuid",lambda:0)
    return p


class FakeVerifiedUnitGuard:
    def __init__(self,source_revision:str,*,bad=False):
        self.sha=source_revision
        self.bad=bad
        self.calls=[]
    def read_root_marker(self,path):
        self.calls.append(path)
        if self.bad:
            raise PermissionError("verified root marker denied")
        return {"schema_version":"1.0","state":"accepted",
                "source_sha":self.sha}


def test_absent_marker_preserves_legacy_host_reconcile_without_invoking_guard(
    tmp_path,monkeypatch,
):
    monkeypatch.setattr(rootguard.os,"geteuid",lambda:0)
    source="a"*40
    guard=FakeVerifiedUnitGuard(source,bad=True)
    result=rootguard.decide(
        source_revision=source,
        marker=tmp_path/"no-existing-release.json",
        guard=guard,require_installed=False)
    assert result["mode"]=="legacy"
    assert result["cutover_accepted"] is False
    assert result["production_mutations"] is False
    assert not guard.calls


def test_root_accepted_marker_promotes_only_one_matching_exact_revision(marker):
    source="a"*40
    guard=FakeVerifiedUnitGuard(source)
    result=rootguard.decide(source_revision=source,
        marker=marker,guard=guard,require_installed=False)
    assert result["mode"]=="replacement"
    assert result["source_revision"]==source
    assert result["cutover_accepted"] is True
    assert result["production_mutations"] is False
    assert guard.calls==[marker]


def test_root_accepted_marker_for_different_release_fails_closed(marker):
    guard=FakeVerifiedUnitGuard("f"*40)
    with pytest.raises(rootguard.RootReconcileAdmissionDenied,
                       match="SOURCE_OR_RECEIPT_NOT_EXACT"):
        rootguard.decide(source_revision="a"*40,
            marker=marker,guard=guard,require_installed=False)


def test_invalid_root_acceptance_never_selects_legacy_fallback(marker):
    guard=FakeVerifiedUnitGuard("a"*40,bad=True)
    with pytest.raises(rootguard.RootReconcileAdmissionDenied,
                       match="ROOT_ACCEPTED_PROOF_INVALID"):
        rootguard.decide(source_revision="a"*40,
            marker=marker,guard=guard,require_installed=False)


def test_present_but_unreadable_marker_must_not_select_legacy(tmp_path,monkeypatch):
    monkeypatch.setattr(rootguard.os,"geteuid",lambda:0)
    marker=tmp_path/"accepted.json"
    marker.write_text("root-owned but blocked")
    original=Path.lstat
    def denied(path):
        if path==marker:
            raise PermissionError("simulated protected read denial")
        return original(path)
    monkeypatch.setattr(Path,"lstat",denied)
    with pytest.raises(rootguard.RootReconcileAdmissionDenied,
                       match="MARKER_UNAVAILABLE"):
        rootguard.decide(source_revision="a"*40,
            marker=marker,guard=FakeVerifiedUnitGuard("a"*40),
            require_installed=False)


@pytest.mark.parametrize("source",[
    "main","", "0"*39, "g"*40, "a"*40+"extra",
])
def test_unreviewed_release_revision_denied_before_marker_lookup(
    tmp_path,monkeypatch,source,
):
    monkeypatch.setattr(rootguard.os,"geteuid",lambda:0)
    with pytest.raises(rootguard.RootReconcileAdmissionDenied,
                       match="SOURCE_REVISION_NOT_EXACT"):
        rootguard.decide(source_revision=source,
            marker=tmp_path/"missing.json",require_installed=False)


def test_unprivileged_cannot_claim_accepted_root_host_release(
    tmp_path,monkeypatch,
):
    monkeypatch.setattr(rootguard.os,"geteuid",lambda:1000)
    with pytest.raises(rootguard.RootReconcileAdmissionDenied,
                       match="ROOT_IDENTITY_REQUIRED"):
        rootguard.decide(source_revision="a"*40,
            marker=tmp_path/"missing.json",require_installed=False)


def test_installed_root_trust_contract_not_user_substitutable(tmp_path):
    with pytest.raises(rootguard.RootReconcileAdmissionDenied,
                       match="ROOT_SOURCE_CANNOT_BE_SUBSTITUTED"):
        rootguard.checked_trust_root(tmp_path)


def test_no_production_mutation_in_root_reconcile_guard():
    source=(SOURCE/"tools/pmv4_e_root_reconcile_admission.py").read_text()
    for bad in (
        "systemctl start","systemctl stop","systemctl disable",
        "docker compose","docker restart","subprocess.run(",
        "os.replace(","os.chmod(","os.chown(","sudo ",
    ):
        assert bad not in source
    assert "root_only" not in source or "ROOT_IDENTITY_REQUIRED" in source


def test_existing_release_host_script_routes_accepted_marker_before_mutations():
    source=(SOURCE/"tools/reconcile_production_host_services.sh").read_text()
    entry=source.index('PMV4_E_MARKER=')
    first_change=source.index('mkdir -p "$RELEASE_ROOT"')
    assert entry<first_change
    assert 'PMV4_E_HOST_MODE=legacy' in source
    assert 'if [ -e "$PMV4_E_MARKER" ] || [ -L "$PMV4_E_MARKER" ]; then' in source
    assert 'PMV4_E_HOST_MODE="$(/usr/bin/python3 -I -B "$PMV4_E_HOST_GUARD"' in source
    assert 'if [ "$PMV4_E_HOST_MODE" != replacement ]; then' in source
    assert 'exit 14' in source[entry:first_change]


def test_old_installers_are_within_explicit_legacy_only_branches():
    source=(SOURCE/"tools/reconcile_production_host_services.sh").read_text()
    for old,new in (
        ("install_support_repair_host_worker.py","jason-pmv4-engineering.timer"),
        ("install_release_host_reconciler.py","jason-pmv4-component-reconcile.path"),
        ("install_release_manager.py","jason-pmv4-component-release.timer"),
        ("install_release_control_transition.py","jason-pmv4-component-transition.timer"),
    ):
        assert old in source
        assert new in source
    assert source.count('if [ "$PMV4_E_HOST_MODE" = replacement ]; then')>=5
    assert source.count("ERROR: retired")>=2
    assert "PMV4_E_LEGACY_ROOT_POLICY_STAGE=SKIPPED_ACCEPTED_REPLACEMENT" in source


def test_host_reconciliation_is_shell_parse_valid():
    import subprocess
    source=SOURCE/"tools/reconcile_production_host_services.sh"
    run=subprocess.run(["/usr/bin/bash","-n",str(source)],
        capture_output=True,text=True,timeout=10)
    assert run.returncode==0,run.stderr


def test_shell_mode_output_contract_is_not_json(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(rootguard.os,"geteuid",lambda:0)
    monkeypatch.setattr(rootguard,"TRUST_ENTRY",Path(rootguard.__file__).resolve())
    monkeypatch.setattr(rootguard,"decide",lambda **_:{"mode":"replacement","cutover_accepted":True})
    assert rootguard.main(["--source-revision","a"*40,"--mode-only"])==0
    output=capsys.readouterr().out
    assert output=="replacement\\n"


def test_host_script_requests_scalar_mode_only():
    source=(SOURCE/"tools/reconcile_production_host_services.sh").read_text()
    assert '--source-revision "$SOURCE_REVISION" --mode-only)' in source
