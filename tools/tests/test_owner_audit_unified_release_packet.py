"""Immutable source-only admission proof for one unified licensed Owner/audit MCP image.

No production Root, identity/session, Docker, network, signing or provider access.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "config/jason-owner-audit-unified-scoped-release.json"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
OWNER = "ec891ae49428357ccae8fa3b990c021a124b41d9"
AUDIT = "1bb2fe561b1189b3c46363a84ecf3eaaa39f5877"
UNIFIED = "6f5d2896a80ec4f4b995430fe4fedf3ef1340943"
UNIFIED_PREVIOUS = "cddf6c38d4516d14c2840a5475dbd59c95f7306a"
ORIGINAL_TOOLS_SHA = "6ea28fc61d43096a8def64750ee2d5ad76c92486e6539c1a08660bfdbe037d64"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def git(*argv: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *argv])


def source_packet() -> dict:
    return json.loads(PACKET.read_text(encoding="utf-8"))


def verify_scope(packet: dict) -> None:
    assert packet["schema_version"] == "1.0"
    assert packet["stage"] == "source_image_isolated_preproduction_only"
    assert packet["candidate_sha"] == UNIFIED
    assert packet["original_last_known_good_sha"] == LKG
    assert packet["licensed_owner_source_sha"] == OWNER
    assert packet["audit_issuer_source_sha"] == AUDIT
    assert packet["source_scope_files"] == sorted(packet["source_sha256"])
    changed = git("diff", "--name-only", LKG, UNIFIED).decode().splitlines()
    assert changed == packet["source_scope_files"]
    assert len(changed) == 14
    for name in changed:
        assert sha256(git("show", UNIFIED + ":" + name)).hexdigest() == packet["source_sha256"][name]


def verify_denied_authority(packet: dict) -> None:
    for key in (
        "live_production_release_performed", "native_release_authorized",
        "owner_signature_recorded", "archive_adoption_performed",
        "production_changed",
    ):
        assert packet[key] is False
    s = packet["exact_change_scope"]
    assert s["only_protected_container"] == "jason-mcp-pilot"
    assert s["original_tool_count"] == 37
    assert s["candidate_tool_count"] == 38
    assert s["original_tool_name_set_sha256"] == ORIGINAL_TOOLS_SHA
    assert s["added_owner_tool"] == "approve_audit_journal_adoption"
    assert s["provider_writes_allowed"] is False
    assert s["standing_grants_allowed"] is False
    assert s["require_independently_verified_licensed_owner_oauth"] is True
    assert s["require_independently_signed_exact_root_release_scope"] is True
    assert s["require_native_root_breaker_and_drift_pass"] is True
    assert s["archive_stage_requires_separate_live_signed_offer"] is True
    assert s["proposed_environment"] == {
        "JASON_AOT_ADMIN_APPROVER_PROFILE": "jason-owner-v1",
        "JASON_AUDIT_JOURNAL_OWNER_ISSUER_ENABLED": "true",
    }
    assert packet["local_pure_source_tests_passed"] == 56
    assert packet["isolated_image_baseline_tools_unchanged"] is True
    assert packet["isolated_image_unverified_owner_denied"] is True
    assert packet["isolated_image_audit_issuer_default_disabled"] is True


def test_exact_source_ancestry_is_reachable_from_reviewed_main():
    assert git("rev-list", "--parents", "-n", "1", UNIFIED).decode().strip() == f"{UNIFIED} {UNIFIED_PREVIOUS}"
    assert git("rev-list", "--parents", "-n", "1", UNIFIED_PREVIOUS).decode().strip() == f"{UNIFIED_PREVIOUS} {OWNER}"
    assert git("rev-list", "--parents", "-n", "1", OWNER).decode().strip() == f"{OWNER} {LKG}"
    assert git("rev-list", "--parents", "-n", "1", AUDIT).decode().split()[1] == LKG
    assert subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", UNIFIED, "HEAD"]).returncode == 0


def test_exact_sources_are_sha256_bound_to_14_changes():
    verify_scope(source_packet())


def test_only_original_mcp_container_changes_and_release_stays_unauthorized():
    verify_denied_authority(source_packet())


def test_images_are_exact_nonidentical_source_bound_candidates():
    packet = source_packet()
    image = packet["candidate_mcp_image_id"]
    rollback = packet["original_mcp_rollback_image_id"]
    runtime = packet["unchanged_runtime_image_id"]
    assert all(isinstance(x, str) and DIGEST.fullmatch(x) for x in (image, rollback, runtime))
    assert len({image, rollback, runtime}) == 3
    assert image == "sha256:7ae7bb3b39d226fbf5684408737ce11b57b2b75604e883014af50e9a5c6b94f0"
    assert packet["candidate_image_scope_label"] == "licensed-owner-plus-audit-issuer-only"
    assert packet["supersedes_candidate_sha"] == UNIFIED_PREVIOUS
    assert packet["original_freeze_sha256"] == "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"


def test_reviewed_candidate_has_one_issuer_and_one_licensed_owner_policy():
    text = git("show", UNIFIED + ":implementation/mcp_service/src/jason_mcp/server.py").decode()
    assert text.count("def approve_audit_journal_adoption(") == 1
    assert text.count("def _licensed_jason_owner(") == 1
    assert "JASON_AUDIT_JOURNAL_OWNER_ISSUER_ENABLED" in text
    assert "JASON_AOT_ADMIN_APPROVER_PROFILE" in text
    dockerfile = git("show", UNIFIED + ":infrastructure/jason-audit-owner-issuer/Dockerfile").decode()
    assert 'LABEL com.teamaot.jason.scope="licensed-owner-plus-audit-issuer-only"' in dockerfile
    assert 'com.teamaot.jason.scope="audit-journal-owner-issuer-only"' not in dockerfile


def test_changed_source_hash_fails_closed():
    packet = source_packet()
    name = packet["source_scope_files"][0]
    packet["source_sha256"][name] = "0" * 64
    with pytest.raises(AssertionError):
        verify_scope(packet)


def test_relabelled_release_or_weakened_owner_scope_fails_closed():
    packet = source_packet()
    packet["native_release_authorized"] = True
    with pytest.raises(AssertionError):
        verify_denied_authority(packet)
    packet = source_packet()
    packet["exact_change_scope"]["require_independently_verified_licensed_owner_oauth"] = False
    with pytest.raises(AssertionError):
        verify_denied_authority(packet)
