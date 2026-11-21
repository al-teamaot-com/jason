"""Fail-closed source-only composition of V2 health and A0 source closure.

Production Owner consent and root execution are never simulated as approval.
The composite is just an order-constrained CLI launcher; all release
authority remains in existing independent signed Owner/root transactions.
"""
from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/pmv4_a0_health_then_source_owner_local.sh"


def test_owner_chain_is_parseable_and_rejects_unknown_execution_mode():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
    denied = subprocess.run(["bash", str(SCRIPT), "--unsupported"],
                            capture_output=True, text=True, timeout=5)
    assert denied.returncode == 2
    assert "DENIED:" in denied.stderr


def test_both_existing_signed_exact_scopes_are_pinned_independently():
    text = SCRIPT.read_text()
    assert "owner-v2-issuer-aware-v2-local-7b42.sh" in text
    assert "pmv4-a0-closure-owner-local-7b42.sh" in text
    assert "de4519df425d796d1f7cc3e8270c4a427b05ff9621c1955bc6b7d367c43e65eb" in text
    assert "3ba8b330c0d5efd79e2f9a92f2348e703eef42f9b2837b18237522854b7fc49f" in text
    assert 'bash "$HEALTH" --execute' in text
    assert 'bash "$CLOSURE" --execute' in text
    assert text.index('bash "$HEALTH" --execute') < text.index('bash "$CLOSURE" --execute')
    assert 'bash "$HEALTH" --check-only' in text
    assert 'bash "$CLOSURE" --check-only' in text


def test_no_native_production_breaker_or_issuer_bypass_in_wrapper():
    text = SCRIPT.read_text()
    assert "JASON_PMV4_STAGE_A0_ISSUER_ENABLED=true" in text
    for forbidden in ("docker rm", "docker stop", "docker exec", "systemctl reset-failed",
                      "sudo ", "chmod 777", "setenforce 0", "chattr -i",
                      "jason-release-control-transition --force"):
        assert forbidden not in text
    assert 'BREAKERMODE=VERIFIED_CLOSED_AND_FRESH_DRIFT_PASS' in text
    assert 'NEXT=SEPARATE_AUTHENTICATED_STAGE_A0_NATIVE_INSTALL_VIA_JASON_MCP' in text
