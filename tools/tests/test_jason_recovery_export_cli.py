from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from tools import jason_recovery
from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
)


ROOT = Path(__file__).resolve().parents[2]


def make_sqlite(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("create table evidence(value text)")
        db.execute("insert into evidence values ('synthetic')")
        db.commit()


def prepare_root(tmp_path: Path):
    root = tmp_path / "candidate"
    files = {
        "etc/jason/deployment.json": "{}",
        "etc/jason/msp-configuration.json": "{}",
        "etc/jason/msp-policy.json": "{}",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    manifest = build_deployment_manifest(
        DeploymentManifestInputs(
            deployment_id="candidate-export-plan",
            instance_id="jason-b",
            environment="candidate",
            release_version="0.1.0",
            source_sha="a" * 40,
            artifact_digest="sha256:" + "b" * 64,
            deployment_revision="c" * 64,
            msp_configuration_revision="d" * 64,
            msp_policy_revision="e" * 64,
            playbook_revision="f" * 64,
            components=(
                ComponentIdentity(
                    name="core",
                    kind="runtime",
                    required=True,
                    release_version="0.1.0",
                    source_sha="a" * 40,
                    artifact_digest="sha256:" + "b" * 64,
                ),
            ),
            schemas=(SchemaIdentity("authority", "1"),),
            providers=(ProviderIdentity("autotask", False, "bundle"),),
            runtime=RuntimeIdentity(
                os="ubuntu 24.04",
                architecture="x86_64",
                python="3.12.3",
                container_runtime="Docker 29",
                compose="5",
            ),
        ),
        generated_at=datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc),
    )
    path = root / "var/lib/jason/deployment-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest))

    make_sqlite(root / "var/lib/jason/authority/authority.sqlite3")
    make_sqlite(root / "var/lib/jason/authority/client-boundaries.sqlite3")
    make_sqlite(root / "var/lib/jason/openclaw/orchestration-events.sqlite3")
    make_sqlite(root / "var/lib/jason/openclaw/approval-continuations.sqlite3")
    return root


def test_plan_export_cli_reports_adapter_blockers_without_secret_access(tmp_path, capsys):
    root = prepare_root(tmp_path)
    args = jason_recovery.build_parser().parse_args(
        ["plan-export", "--target-root", str(root)]
    )
    assert jason_recovery.command_plan_export(args) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert (
        "required_adapter_unavailable:governed_secret_export"
        in payload["blockers"]
    )
    assert (
        "required_adapter_unavailable:governed_key_export"
        in payload["blockers"]
    )


def test_plan_export_cli_is_ready_when_required_adapters_are_declared(tmp_path, capsys):
    root = prepare_root(tmp_path)
    args = jason_recovery.build_parser().parse_args(
        [
            "plan-export",
            "--target-root",
            str(root),
            "--available-adapter",
            "governed_secret_export",
            "--available-adapter",
            "governed_key_export",
        ]
    )
    assert jason_recovery.command_plan_export(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready_for_export"
    assert payload["blockers"] == []
