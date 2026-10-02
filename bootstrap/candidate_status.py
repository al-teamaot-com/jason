from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request

from bootstrap.candidate_activation import load_candidate_host_identity
from bootstrap.candidate_evidence import collect_candidate_readiness_evidence
from bootstrap.candidate_ready import evaluate_candidate_ready, write_ready_result
from bootstrap.install_runtime import load_resources


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _http_getter(url: str):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
            return int(response.status), payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, {}


def main() -> int:
    repo = _repo_root()
    parser = argparse.ArgumentParser(
        description="Collect and evaluate Jason candidate READY evidence"
    )
    parser.add_argument("--target-root", default="/")
    parser.add_argument("--host-identity")
    parser.add_argument(
        "--msp-config",
        default="/etc/jason/msp-configuration.json",
    )
    parser.add_argument(
        "--resources",
        default=str(repo / "config/bootstrap-resources.v1.json"),
    )
    parser.add_argument(
        "--resources-schema",
        default=str(repo / "config/schemas/bootstrap-resources.schema.json"),
    )
    parser.add_argument(
        "--evidence-schema",
        default=str(repo / "config/schemas/candidate-readiness-evidence.schema.json"),
    )
    parser.add_argument(
        "--secret-attestation",
        default="/var/lib/jason/secret-presence-attestation.json",
    )
    parser.add_argument(
        "--runtime-health-url",
        default="http://127.0.0.1:8080/healthz",
    )
    parser.add_argument("--write-result", action="store_true")
    args = parser.parse_args()

    root = Path(args.target_root)
    identity = None
    if root == Path("/"):
        if not args.host_identity:
            parser.error("--host-identity is required when --target-root=/")
        identity = load_candidate_host_identity(args.host_identity)

    resources = load_resources(args.resources, args.resources_schema)
    config = _load_json(args.msp_config)
    schema = _load_json(args.evidence_schema)
    evidence = collect_candidate_readiness_evidence(
        target_root=root,
        resources=resources,
        msp_configuration=config,
        secret_presence_attestation_path=args.secret_attestation,
        runtime_health_url=args.runtime_health_url,
        runner=lambda command: __import__("subprocess").run(
            list(command),
            text=True,
            capture_output=True,
            check=False,
        ),
        http_getter=_http_getter,
    )
    result = evaluate_candidate_ready(
        target_root=root,
        resources=resources,
        msp_configuration=config,
        evidence=evidence,
        evidence_schema=schema,
        candidate_identity=identity,
    )
    if args.write_result:
        write_ready_result(
            target_root=root,
            result=result,
            candidate_identity=identity,
        )
    print(json.dumps(
        {
            "result": {
                "schema_version": result.schema_version,
                "instance_id": result.instance_id,
                "deployment_identity_sha256": result.deployment_identity_sha256,
                "status": result.status,
                "checks": dict(result.checks),
                "blockers": list(result.blockers),
            },
            "evidence": evidence,
        },
        indent=2,
        sort_keys=True,
    ))
    return 0 if result.status == "READY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
