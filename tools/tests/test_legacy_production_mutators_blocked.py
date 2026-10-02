from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BLOCKED = (
    "infrastructure/showcase/deploy_autonomy_flight_recorder.sh",
    "infrastructure/showcase/deploy_production_health_dashboard.sh",
    "infrastructure/showcase/deploy_usage_dashboard.sh",
    "infrastructure/showcase/install_showcase.sh",
    "tools/install_ccc_scheduler.sh",
    "tools/install_observability_assurance.sh",
    "tools/install_openclaw_authority_operations.sh",
    "tools/reconcile_production_host_services.sh",
)

MUTATION_MARKERS = (
    "docker compose",
    "docker run",
    "systemctl ",
    "sudo systemctl",
    "install -o ",
    "sudo install ",
    "ln -sfn ",
)


def test_legacy_production_mutators_fail_closed_before_first_mutation():
    for relative in BLOCKED:
        text = (ROOT / relative).read_text(encoding="utf-8")
        gate = text.index("PRODUCTION_PROMOTION_GATE=BLOCKED legacy mutator")
        exit_gate = text.index("exit 42", gate)
        mutation_indexes = [
            text.index(marker)
            for marker in MUTATION_MARKERS
            if marker in text
        ]
        assert mutation_indexes, relative
        assert exit_gate < min(mutation_indexes), relative


def test_block_cannot_be_enabled_with_environment_boolean():
    for relative in BLOCKED:
        text = (ROOT / relative).read_text(encoding="utf-8")
        prefix = text[: text.index("exit 42") + len("exit 42")]
        assert "approved=true" not in prefix.lower()
        assert "ALLOW_" not in prefix
        assert "JASON_PRODUCTION_PROMOTION_PERMIT" not in prefix
