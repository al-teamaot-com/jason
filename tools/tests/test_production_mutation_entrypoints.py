from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "production-mutation-entrypoints.json"

MUTATION_MARKERS = (
    re.compile(r"\bdocker\s+(?:rm|run|start|stop|tag|build|buildx|compose)\b"),
    re.compile(r"\bsystemctl\s+(?:enable|restart|start|stop|daemon-reload)\b"),
    re.compile(r"/etc/systemd/system"),
    re.compile(r"\bln\s+-sfn\b"),
)
NAME_MARKERS = (
    "deploy",
    "install",
    "production",
    "cutover",
    "rollback",
    "baseline",
    "reconcile",
    "ops",
    "self_heal",
    "boot-recovery",
    "run_kfs_collector",
)


def registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def candidate_mutators() -> set[str]:
    results: set[str] = set()
    for root_name in ("tools", "infrastructure"):
        for path in (ROOT / root_name).rglob("*"):
            if not path.is_file() or path.suffix not in {".sh", ".py", ".service"}:
                continue
            relative = path.relative_to(ROOT).as_posix()
            if "/tests/" in relative or relative.startswith("tools/tests/"):
                continue
            lower = relative.lower()
            if not any(marker in lower for marker in NAME_MARKERS):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(pattern.search(text) for pattern in MUTATION_MARKERS):
                results.add(relative)
    return results


def test_registry_has_one_unique_existing_record_per_entrypoint():
    data = registry()
    paths = [item["path"] for item in data["entrypoints"]]
    assert len(paths) == len(set(paths))
    for path in paths:
        assert (ROOT / path).exists(), path


def test_all_high_risk_mutation_entrypoints_are_classified():
    classified = {item["path"] for item in registry()["entrypoints"]}
    missing = candidate_mutators() - classified
    assert not missing, "unclassified host mutation entrypoints: " + ", ".join(sorted(missing))


def test_only_explicitly_gated_paths_claim_production_release_authority():
    data = registry()
    allowed_classes = {
        "gated_internal_helper",
        "gated_component_runner",
        "gated_promotion_wrapper",
        "gated_operator_wrapper",
    }
    for item in data["entrypoints"]:
        if item["production_release_authority"]:
            assert item["classification"] in allowed_classes, item


def test_legacy_pending_paths_are_not_declared_production_authority():
    for item in registry()["entrypoints"]:
        if item["classification"] == "legacy_pending_promotion_gate":
            assert item["production_release_authority"] is False
