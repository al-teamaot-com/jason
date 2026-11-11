#!/usr/bin/env python3
"""Root-installed independent PMv4 shadow release/recovery entrypoint.

Inspect is read-only. Promotion requires a previously signed exact-scope
Owner decision in the separately rooted PMv4 control store. Recovery may
only restore a previously authorized and pending transaction. No PMV3
engineering controller, Teams card, API-key AI or provider write is invoked.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.pmv4_host_release_guard import IndependentHostGuard, HostGateDenied
from tools.pmv4_shadow_ci import protected_main_ci_verified
from tools.pmv4_shadow_release import (
    PRODUCTION_ROOT, TRUST_PATH, EMPTY_BASELINE,
    ShadowController, ShadowReleaseDenied, read_json, manifest_check,
)
from tools.pmv4_shadow_docker_adapter import DockerShadowAdapter


def trusted_controller():
    """Assemble existing components from host-installed, fixed trusted code."""
    guard = IndependentHostGuard()
    adapter = DockerShadowAdapter(
        root=PRODUCTION_ROOT,
        core_continuity_probe=guard.preexisting_core_health,
    )
    controller = ShadowController(
        PRODUCTION_ROOT, public_key_path=TRUST_PATH,
        protected_ci_check=protected_main_ci_verified,
        activate_shadow=adapter.activate_shadow,
        verify_shadow_and_core=adapter.verify_shadow_and_core,
        restore_shadow=adapter.restore_shadow,
        host_mutation_quiescent=guard.host_mutation_quiescent,
        preexisting_core_health=guard.preexisting_core_health,
        host_release_transaction=guard.host_release_transaction,
    )
    return guard, adapter, controller


def pending_rollback_acceptance(
    adapter: DockerShadowAdapter, guard: IndependentHostGuard,
    previous_dir: Path,
) -> bool:
    if not guard.preexisting_core_health():
        return False
    if previous_dir.name == EMPTY_BASELINE:
        # The first install must restore absence, not a fabricated old image.
        expected = read_json(previous_dir / "baseline.json")
        return (
            expected == {
                "schema_version": "1.0", "service": "jason-pmv4-shadow",
                "baseline": "no_prior_shadow_runtime",
            }
            and adapter._owned_or_absent() is None
        )
    return adapter.verify_shadow_and_core(previous_dir)


def _owner_proof(root: Path, manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    """Read only exact source-bound signed decision, never a caller-supplied token."""
    sha = manifest["candidate_sha"]
    path = root / "control" / "signed-owner-decisions" / (
        "release-" + sha[:16] + ".json"
    )
    document = read_json(path)
    if (
        set(document) != {
            "schema_version", "service", "source", "release_id",
            "owner_principal", "signed_owner_proof",
        }
        or document["schema_version"] != "1.0"
        or document["service"] != "jason-pmv4-shadow"
        or document["source"] != "independently_verified_entra_owner"
        or document["release_id"] != "release-" + sha[:16]
        or not isinstance(document["signed_owner_proof"], dict)
    ):
        raise ShadowReleaseDenied("SHADOW_OWNER_DECISION_STORE_UNTRUSTED")
    return document["signed_owner_proof"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "operation", choices=("inspect", "promote-signed", "reconcile-pending"),
        nargs="?", default="inspect",
    )
    args = p.parse_args(argv)
    if args.operation == "inspect":
        guard = IndependentHostGuard()
        try:
            report = guard.core_health_evidence()
            # The future PMv4 control lock is not provisioned until a governed
            # installer runs. That is a readiness blocker, not host mutation.
            report["cross_release_lock_ready"] = guard.host_mutation_quiescent()
            report["production_mutation"] = False
            report["independent_release_installed"] = (
                PRODUCTION_ROOT.is_dir()
                and (PRODUCTION_ROOT / "control" / "host-mutation.lock").is_file()
            )
            print(json.dumps(report, sort_keys=True))
            return 0
        except (HostGateDenied, ShadowReleaseDenied, OSError, ValueError) as exc:
            print(json.dumps({
                "status": "denied", "reason": str(exc),
                "production_mutation": False,
            }, sort_keys=True))
            return 2

    # No pre-authorized control installation, no mutation. Never accept
    # arbitrary override paths or a proof/approval from command arguments.
    if os.geteuid() != 0:
        raise SystemExit("PMV4_TRUSTED_ROOT_INSTALL_REQUIRED")
    guard, adapter, controller = trusted_controller()
    if args.operation == "reconcile-pending":
        result = controller.reconcile_pending_rollback(
            rollback_acceptance=lambda old: pending_rollback_acceptance(
                adapter, guard, old,
            )
        )
    else:
        manifest = read_json(PRODUCTION_ROOT / "control" / "approved-manifest.json")
        manifest_check(manifest)
        proof = _owner_proof(PRODUCTION_ROOT, manifest)
        result = controller.promote(manifest, proof)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
