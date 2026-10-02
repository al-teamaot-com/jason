from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil

from bootstrap.clean_install import (
    apply_layout,
    build_plan,
    observe_host,
    read_json,
)
from bootstrap.install_runtime import (
    evaluate_candidate_readiness,
    initialize_state_stores,
    load_resources,
    stage_portable_systemd_units,
    stage_release_archive,
    write_bootstrap_runtime_manifest,
)
from bootstrap.candidate_manifest import generate_candidate_deployment_manifest


def _write_configuration(
    *,
    target_root: Path,
    msp_configuration_path: Path,
    msp_policy_path: Path,
) -> dict[str, str]:
    target = target_root / "etc/jason"
    target.mkdir(parents=True, exist_ok=True)

    config = read_json(msp_configuration_path)
    policy = read_json(msp_policy_path)

    config_target = target / "msp-configuration.json"
    policy_target = target / "msp-policy.json"
    config_target.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    policy_target.write_text(
        json.dumps(policy, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "msp_configuration": str(config_target),
        "msp_policy": str(policy_target),
    }


def bootstrap_candidate(
    *,
    target_root: str | Path,
    release_archive: str | Path,
    release_artifact_sha256: str,
    source_sha: str,
    msp_configuration_path: str | Path,
    msp_policy_path: str | Path,
    schema_root: str | Path,
    resources_path: str | Path,
    resources_schema_path: str | Path,
    repository_root: str | Path,
    instance_id: str,
    host=None,
) -> dict:
    root = Path(target_root)
    if root == Path("/"):
        raise PermissionError("candidate bootstrap may not target the live filesystem root")

    observation = host or observe_host()
    plan = build_plan(
        environment="candidate",
        target_root=root,
        msp_configuration_path=msp_configuration_path,
        msp_policy_path=msp_policy_path,
        schema_root=schema_root,
        host=observation,
    )
    bootstrap_identity = apply_layout(plan)
    config_paths = _write_configuration(
        target_root=root,
        msp_configuration_path=Path(msp_configuration_path),
        msp_policy_path=Path(msp_policy_path),
    )

    resources = load_resources(resources_path, resources_schema_path)
    release = stage_release_archive(
        archive_path=release_archive,
        expected_artifact_sha256=release_artifact_sha256,
        source_sha=source_sha,
        target_root=root,
    )
    state = initialize_state_stores(
        target_root=root,
        resources=resources,
    )
    services = stage_portable_systemd_units(
        repository_root=repository_root,
        target_root=root,
        resources=resources,
    )
    runtime_manifest = write_bootstrap_runtime_manifest(
        target_root=root,
        release=release,
        state=state,
        services=services,
        resources=resources,
    )
    readiness = evaluate_candidate_readiness(
        target_root=root,
        resources=resources,
    )

    deployment_manifest, deployment_manifest_path = (
        generate_candidate_deployment_manifest(
            target_root=root,
            instance_id=instance_id,
            release=release,
            state_stores=state,
            resources=resources,
            msp_configuration=read_json(msp_configuration_path),
            msp_configuration_revision=plan.msp_configuration_revision,
            msp_policy_revision=plan.msp_policy_revision,
            host=observation,
        )
    )

    result = {
        "schema_version": "1.0",
        "environment": "candidate",
        "target_root": str(root),
        "bootstrap_identity": str(bootstrap_identity),
        "configuration": config_paths,
        "release": asdict(release),
        "state_stores": [asdict(item) for item in state],
        "systemd_units": [asdict(item) for item in services],
        "runtime_manifest": str(runtime_manifest),
        "deployment_manifest": {
            "path": str(deployment_manifest_path),
            "identity_sha256": deployment_manifest["identity_sha256"],
        },
        "readiness": readiness,
    }
    output = root / "var/lib/jason/candidate-bootstrap-result.json"
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result["result_path"] = str(output)
    return result


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    repo = _root()
    parser = argparse.ArgumentParser(
        description="Build a non-production Jason candidate filesystem from an immutable release"
    )
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--release-archive", required=True)
    parser.add_argument("--release-sha256", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--msp-config", required=True)
    parser.add_argument("--msp-policy", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument(
        "--schema-root",
        default=str(repo / "config/schemas"),
    )
    parser.add_argument(
        "--resources",
        default=str(repo / "config/bootstrap-resources.v1.json"),
    )
    parser.add_argument(
        "--resources-schema",
        default=str(repo / "config/schemas/bootstrap-resources.schema.json"),
    )
    args = parser.parse_args()

    result = bootstrap_candidate(
        target_root=args.target_root,
        release_archive=args.release_archive,
        release_artifact_sha256=args.release_sha256,
        source_sha=args.source_sha,
        msp_configuration_path=args.msp_config,
        msp_policy_path=args.msp_policy,
        schema_root=args.schema_root,
        resources_path=args.resources,
        resources_schema_path=args.resources_schema,
        repository_root=repo,
        instance_id=args.instance_id,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["readiness"]["status"] == "ready_for_runtime_activation" else 3


if __name__ == "__main__":
    raise SystemExit(main())
