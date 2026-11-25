"""Deterministic replica of the 2026-11-06 *observed* protected root history.

The historical policy SHA256 values, two receipt transitions, and commit SHAs
were observed by a separately authorized READ-ONLY root diagnostic. Policy
bytes are reconstructed exclusively from a publicly reviewed Git source
snapshot. No root files, secrets, service commands, or production state used.

Receipt bytes are synthetic but signed-format-equivalent: exact historical
SHA/delta/phase/ancestry structure is replicated and tested for integrity.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).resolve().parents[1]
SOURCE_FILE = TOOLS / "protected_root_policy_migration.py"
HISTORICAL_POLICY = Path(__file__).parent / "fixtures/pmv31_authority_original_policy.json"
spec = importlib.util.spec_from_file_location("pmv31_history_replay", SOURCE_FILE)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

BASE1974 = "aca94fdc0bfa551162f6ea99d7ddded311786414"
AUTHORITY = "743c75eaa541dfcb1efb1cd80746728395fcfe97"
PRE_TEAMS = "c2b559488d761cb10a6da35092b391de5b5e9c69"
TEAMS = "7e7b13af05881201a683624a2e40509ebbd79b78"
LKG = "ee8d0652533c3e426fd73c96bf1de5d3a7753001"
PMV31 = "fb9d647368fa850af7b3f8321a7e2189682dc6c9"
EXPECTED_HASHES = (
    "709164967c5d5dd0982d9774a1bfeb8f1aa3668d6d6e4e43c6eec209d389a82a",
    "6473be851479381982d9232e55a5400a7e0a9890bc7715fcf5172c33553720a0",
    "afc2b58d2cfbdc81d0e98ecf2ec121c3877894cfd0f830db5a949b3dab75b038",
)
# These were independently verified with git merge-base against the live host.
REVIEWED_LINEAGE_EDGES = frozenset({
    (BASE1974, AUTHORITY), (AUTHORITY, PRE_TEAMS),
    (PRE_TEAMS, TEAMS), (TEAMS, LKG),
})


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def policy(data: bytes) -> dict:
    return json.loads(data)


def receipt(original: bytes, after: bytes, candidate: str, rollback: str, plan: dict,
            prior_bytes: bytes | None = None) -> bytes:
    obj = {
        "schema_version": "1.0", "phase": "applied",
        "candidate_sha": candidate, "rollback_sha": rollback,
        "original_sha256": sha(original),
        "applied_sha256": sha(after),
        "staged_sha256": sha(after),
        "original_policy_base64": base64.b64encode(original).decode("ascii"),
        "reviewed_delta": {name: sorted(units) for name, units in plan.items()},
        "authorized_by": "exact_owner_approval_and_ccc_material_review",
        "recorded_at": "2026-11-06T00:00:00+00:00",
    }
    if prior_bytes is not None:
        obj["prior_active_receipt_base64"] = base64.b64encode(prior_bytes).decode("ascii")
        obj["prior_active_receipt_sha256"] = sha(prior_bytes)
    return (json.dumps(obj, sort_keys=True, indent=2) + "\n").encode()


def observed_replica(monkeypatch, tmp_path):
    before = HISTORICAL_POLICY.read_bytes()
    base = policy(before)
    authority = m._overlay_policy(base, m.APPROVED_DELTA)
    authority_policy = policy(authority)
    teams = m._overlay_policy(authority_policy, m.APPROVED_HELD_OFFER_DELTA)
    teams_policy = policy(teams)
    pmv31 = m._overlay_policy(teams_policy, m.APPROVED_PM_V31_PROVIDER_HEALTH_DELTA)
    assert (sha(before), sha(authority), sha(teams)) == EXPECTED_HASHES
    first_receipt = receipt(before, authority, AUTHORITY, BASE1974, m.APPROVED_DELTA)
    current_receipt = receipt(
        authority, teams, TEAMS, PRE_TEAMS, m.APPROVED_HELD_OFFER_DELTA,
        prior_bytes=first_receipt,
    )
    source = {
        BASE1974: base, AUTHORITY: authority_policy,
        PRE_TEAMS: authority_policy, TEAMS: teams_policy,
        LKG: teams_policy, PMV31: policy(pmv31),
    }
    ledger = tmp_path / "ledger"
    ledger.mkdir(mode=0o700)
    active = ledger / "active.json"
    active.write_bytes(current_receipt)
    root = tmp_path / "production-desired-state.json"
    root.write_bytes(teams)
    control = tmp_path / "production-control-state.json"
    control.write_text(json.dumps({
        "schema_version": "1.0",
        "last_known_good": {"manifest": {"revision": LKG}},
    }))
    monkeypatch.setattr(m, "POLICY", root)
    monkeypatch.setattr(m, "LEDGER_DIR", ledger)
    monkeypatch.setattr(m, "ACTIVE", active)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "_require_root", lambda: None)
    monkeypatch.setattr(m, "_approval", lambda *args: None)
    monkeypatch.setattr(m, "_root_only", lambda path: Path(path).read_bytes())
    monkeypatch.setattr(m, "_ledger_dir", lambda: None)
    monkeypatch.setattr(m, "_source_policy", lambda version: source[version])
    monkeypatch.setattr(m, "_reviewed_git_policy", lambda version: source[version])
    monkeypatch.setattr(m.os, "fchown", lambda *args: None)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)

    def checked_ancestry(args, **kwargs):
        if args[-3] != "--is-ancestor" or (args[-2], args[-1]) not in REVIEWED_LINEAGE_EDGES:
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(m.subprocess, "run", checked_ancestry)
    return root, teams, active, current_receipt, pmv31


@pytest.mark.parametrize("cycle", (1, 2))
def test_observed_root_chain_exact_sha_stage_apply_and_symmetric_rollback(
        monkeypatch, tmp_path, cycle):
    root, initial, active, receipt_bytes, final = observed_replica(monkeypatch, tmp_path)
    assert m.preview_exact_migration(PMV31, LKG) == "OWNER_CCC_REVIEWED_DELTA_ONLY"
    assert root.read_bytes() == initial
    assert active.read_bytes() == receipt_bytes
    assert m.stage_for_candidate(PMV31, LKG) == "STAGED_ALLOWED_ONLY"
    staged = root.read_bytes()
    assert set(policy(staged)["allowed_system_units"]) == (
        set(policy(initial)["allowed_system_units"]) |
        m.APPROVED_PM_V31_PROVIDER_HEALTH_DELTA["allowed_system_units"]
    )
    assert m.apply_for_candidate(PMV31, LKG) == "APPLIED_REQUIRED_AFTER_HEALTH"
    assert root.read_bytes() == final
    third = json.loads(active.read_bytes())
    assert base64.b64decode(third["prior_active_receipt_base64"]) == receipt_bytes
    assert m.restore_for_baseline(LKG) == "RESTORED"
    assert root.read_bytes() == initial
    assert active.read_bytes() == receipt_bytes
    assert (tmp_path/"ledger"/("restored-"+PMV31+".json")).is_file()
    # A second, independent run is required. Pytest gives each cycle a new
    # fixture, not a reused or already-restored state.


@pytest.mark.parametrize("failure_stage", ("before_stage","after_stage","after_apply"))
def test_observed_chain_forced_rollback_preserves_original_bytes(
        monkeypatch, tmp_path, failure_stage):
    root, initial, active, receipt_bytes, _ = observed_replica(monkeypatch, tmp_path)
    if failure_stage != "before_stage":
        assert m.stage_for_candidate(PMV31, LKG) == "STAGED_ALLOWED_ONLY"
    if failure_stage == "after_apply":
        assert m.apply_for_candidate(PMV31, LKG) == "APPLIED_REQUIRED_AFTER_HEALTH"
    if failure_stage == "before_stage":
        # No PMv3.1 stage occurred. The historical receipt belongs to its own
        # older rollback target; fail closed, never rewrite its protected chain.
        with pytest.raises(m.MigrationRefused, match="rollback target"):
            m.restore_for_baseline(LKG)
    else:
        assert m.restore_for_baseline(LKG) == "RESTORED"
    assert root.read_bytes() == initial
    assert active.read_bytes() == receipt_bytes


@pytest.mark.parametrize("fault",("parent_checksum","grandparent_original","depth_overrun","lineage_mismatch"))
def test_observed_chain_refuses_unreviewed_root_ledger(
        monkeypatch, tmp_path, fault):
    root, initial, active, receipt_bytes, _ = observed_replica(monkeypatch, tmp_path)
    target = json.loads(active.read_bytes())
    if fault == "parent_checksum":
        target["prior_active_receipt_sha256"] = "0"*64
    if fault == "grandparent_original":
        grandparent = json.loads(base64.b64decode(target["prior_active_receipt_base64"]))
        grandparent["original_sha256"] = "0"*64
        raw = (json.dumps(grandparent, sort_keys=True, indent=2)+"\n").encode()
        target["prior_active_receipt_base64"] = base64.b64encode(raw).decode("ascii")
        target["prior_active_receipt_sha256"] = sha(raw)
    if fault == "depth_overrun":
        grandparent = json.loads(base64.b64decode(target["prior_active_receipt_base64"]))
        grandparent["prior_active_receipt_base64"] = base64.b64encode(b"{}").decode("ascii")
        grandparent["prior_active_receipt_sha256"] = sha(b"{}")
        raw = (json.dumps(grandparent, sort_keys=True, indent=2)+"\n").encode()
        target["prior_active_receipt_base64"] = base64.b64encode(raw).decode("ascii")
        target["prior_active_receipt_sha256"] = sha(raw)
    if fault == "lineage_mismatch":
        monkeypatch.setattr(
            m.subprocess, "run", lambda *args,**kwargs: SimpleNamespace(returncode=1)
        )
    if fault != "lineage_mismatch":
        active.write_text(json.dumps(target))
    with pytest.raises(m.MigrationRefused):
        m.preview_exact_migration(PMV31, LKG)
    with pytest.raises(m.MigrationRefused):
        m.stage_for_candidate(PMV31, LKG)
    assert root.read_bytes() == initial
    assert active.read_bytes() == (receipt_bytes if fault == "lineage_mismatch" else json.dumps(target).encode())


@pytest.mark.parametrize("cycle", (1, 2))
def test_combined_real_history_host_stage_approval_install_and_forced_baseline_restore(
        monkeypatch, tmp_path, cycle):
    """Bounded nonproduction rehearsal of BOTH previously failing components.

    This runs real migration stage/apply/restore functions plus real reviewed
    unit installer file writes in an isolated directory; only systemctl and
    canonical worktree management are mocked. No root privileges are used.
    """
    from unittest.mock import patch

    root, initial, active, ledger_bytes, _ = observed_replica(monkeypatch,tmp_path)
    install_spec = importlib.util.spec_from_file_location(
        "pmv31_replay_installer_" + str(cycle),
        TOOLS/"install_release_manager.py",
    )
    assert install_spec is not None and install_spec.loader is not None
    installer = importlib.util.module_from_spec(install_spec)
    install_spec.loader.exec_module(installer)
    unit_root = tmp_path / "isolated-systemd-user"
    unit_root.mkdir()
    monkeypatch.setattr(installer, "UNIT_DIR", unit_root)
    monkeypatch.setattr(installer, "ensure_authoritative_approval_worktree", lambda: None)

    assert m.stage_for_candidate(PMV31,LKG)=="STAGED_ALLOWED_ONLY"
    with patch.object(installer.subprocess, "run",
                      lambda *args, **kwargs: SimpleNamespace(returncode=0)):
        assert installer.install_approval_only_units(activate=True)
    service=unit_root/"jason-release-approval-only.service"
    override=unit_root/"jason-release-approval-only.service.d"/installer.APPROVAL_OVERRIDE
    assert service.is_file()
    reviewed_override=override.read_bytes()
    assert b"--repo /home/al/.local/lib/jason/release-approval-source " in reviewed_override
    assert m.apply_for_candidate(PMV31,LKG)=="APPLIED_REQUIRED_AFTER_HEALTH"

    # Force the native rollback sequence: restore root policy and historical
    # receipt, then reconcile the *real* previous LKG's service file bytes.
    assert m.restore_for_baseline(LKG)=="RESTORED"
    lkg_service=(Path(__file__).parent/"fixtures"/
                 "pmv31_baseline_approval_only_unit_ee8d0652.service").read_bytes()
    service.write_bytes(lkg_service)
    assert b"--repo /home/al/.local/lib/jason/engineering-worker-source " in service.read_bytes()
    assert override.read_bytes()==reviewed_override
    effective=[line for line in override.read_text().splitlines()
               if line.startswith("ExecStart=")]
    assert len(effective)==2 and effective[0]=="ExecStart="
    assert effective[1].endswith("approval-only-held")
    assert "--repo /home/al/.local/lib/jason/release-approval-source " in effective[1]
    assert root.read_bytes()==initial
    assert active.read_bytes()==ledger_bytes
    assert (tmp_path/"ledger"/("restored-"+PMV31+".json")).is_file()
