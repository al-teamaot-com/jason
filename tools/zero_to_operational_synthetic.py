from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from bootstrap.candidate_bootstrap import bootstrap_candidate
from bootstrap.candidate_ready import (
    enabled_provider_ids,
    evaluate_candidate_ready,
    required_network_names,
    required_unit_names,
)
from bootstrap.clean_install import HostObservation
from bootstrap.install_runtime import load_resources
from jason_runtime.deployment_identity import FileDeploymentManifestProvider
from kernel.client_boundaries.contracts import (
    BoundaryStatus,
    ClientBoundary,
)
from kernel.client_boundaries.repositories import BoundaryConflictError
from kernel.client_boundaries.sqlite import (
    SQLiteClientBoundaryRepository,
    SQLiteClientBoundaryStore,
)
from orchestrator.event_store import (
    OrchestrationEvent,
    SQLiteOrchestrationEventStore,
)
from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
)
from tools.full_recovery_builtin_adapters import BUILTIN_ADAPTERS
from tools.full_recovery_export import load_collection_spec
from tools.full_recovery_export_package import (
    create_encrypted_full_recovery_export,
    write_recovery_package_atomic,
)
from tools.full_recovery_package import decrypt_recovery_package
from tools.full_recovery_restore import (
    acknowledge_reenrollment,
    apply_recovery_restore_plan,
    plan_recovery_restore,
)
from tools.reproducible_upgrade import (
    execute_candidate_upgrade,
    plan_upgrade,
)
from tools.zero_to_operational import run_zero_to_operational


class SyntheticAcceptanceError(RuntimeError):
    pass


class SyntheticZeroToOperationalExecutor:
    def __init__(
        self,
        *,
        repository_root: str | Path,
        workspace: str | Path,
    ) -> None:
        self.repo = Path(repository_root)
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.root_a = self.workspace / "jason-a"
        self.root_b = self.workspace / "jason-b"
        self.root_c = self.workspace / "jason-c"
        self.release_a = self.workspace / "release-a.tar.gz"
        self.source_a = "a" * 40
        self.source_next = "b" * 40
        self.config_path = self.repo / "config/examples/msp-configuration.example.json"
        self.policy_path = self.repo / "config/examples/msp-policy.example.json"
        self.resources = load_resources(
            self.repo / "config/bootstrap-resources.v1.json",
            self.repo / "config/schemas/bootstrap-resources.schema.json",
        )
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.ready_schema = json.loads(
            (
                self.repo
                / "config/schemas/candidate-readiness-evidence.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.recovery_inventory = json.loads(
            (
                self.repo / "config/recovery-state-inventory.v1.json"
            ).read_text(encoding="utf-8")
        )
        self.recovery_payload_schema = json.loads(
            (
                self.repo
                / "config/schemas/full-recovery-payload-manifest.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.collection_spec = load_collection_spec(
            self.repo / "config/full-recovery-collection.v1.json",
            self.repo / "config/schemas/full-recovery-collection.schema.json",
        )
        self.host = HostObservation(
            os_id="ubuntu",
            os_version="24.04",
            architecture="x86_64",
            python_version="3.12.3",
            docker_version="Docker version synthetic",
            compose_version="Docker Compose version synthetic",
        )
        self.recovery_private = X25519PrivateKey.generate()
        self.signer_private = Ed25519PrivateKey.generate()
        self.manifest_a: dict[str, Any] | None = None
        self.manifest_next: dict[str, Any] | None = None
        self.full_export_path: Path | None = None
        self.boundary_id = "acceptance-boundary-a"

    def _make_release_archive(self) -> str:
        files = {
            "implementation/pyproject.toml": (
                b'[project]\nname = "jason-platform"\nversion = "0.1.0"\n'
            ),
            "implementation/autonomous_remediation/playbook_registry.json": (
                b'{"schema_version":"1.0","playbooks":[]}\n'
            ),
            "tools/delegation_maintenance.py": b"print('synthetic')\n",
            "tools/openclaw_authority_health_snapshot.py": b"print('synthetic')\n",
        }
        with tarfile.open(self.release_a, "w:gz") as archive:
            for name, content in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        return hashlib.sha256(self.release_a.read_bytes()).hexdigest()

    def _bootstrap(
        self,
        root: Path,
        *,
        instance_id: str = "jason-acceptance",
        clean: bool = True,
    ):
        if clean and root.exists():
            shutil.rmtree(root)
        digest = (
            hashlib.sha256(self.release_a.read_bytes()).hexdigest()
            if self.release_a.exists()
            else self._make_release_archive()
        )
        return bootstrap_candidate(
            target_root=root,
            release_archive=self.release_a,
            release_artifact_sha256=digest,
            source_sha=self.source_a,
            msp_configuration_path=self.config_path,
            msp_policy_path=self.policy_path,
            schema_root=self.repo / "config/schemas",
            resources_path=self.repo / "config/bootstrap-resources.v1.json",
            resources_schema_path=(
                self.repo / "config/schemas/bootstrap-resources.schema.json"
            ),
            repository_root=self.repo,
            instance_id=instance_id,
            host=self.host,
        )

    def _manifest(self, root: Path) -> dict[str, Any]:
        return dict(
            FileDeploymentManifestProvider(
                root / "var/lib/jason/deployment-manifest.json"
            ).read()
        )

    def _ready(self, root: Path) -> Mapping[str, Any]:
        manifest = self._manifest(root)
        evidence = {
            "schema_version": "1.0",
            "instance_id": manifest["instance_id"],
            "deployment_identity_sha256": manifest["identity_sha256"],
            "bootstrap_status": "ready_for_runtime_activation",
            "available_secret_references": [
                item["secret_reference"]
                for item in self.config["providers"].values()
                if item.get("enabled") and item.get("secret_reference")
            ],
            "networks": {
                name: "present"
                for name in required_network_names(self.resources)
            },
            "units": {
                name: "enabled"
                for name in required_unit_names(self.resources)
            },
            "runtime_health": {
                "status": "healthy",
                "deployment_identity_sha256": manifest["identity_sha256"],
            },
            "governance_health": {"status": "healthy"},
            "providers": {
                provider: "ready"
                for provider in enabled_provider_ids(self.config)
            },
        }
        result = evaluate_candidate_ready(
            target_root=root,
            resources=self.resources,
            msp_configuration=self.config,
            evidence=evidence,
            evidence_schema=self.ready_schema,
        )
        if result.status != "READY":
            raise SyntheticAcceptanceError(
                "candidate READY failed: " + ",".join(result.blockers)
            )
        return {
            "ready_status": result.status,
            "checks": dict(result.checks),
            "deployment_identity_sha256": result.deployment_identity_sha256,
        }

    def _prepare_openbao_recovery_artifacts(self, root: Path) -> None:
        backup = root / "opt/jason/backups/openbao"
        backup.mkdir(parents=True, exist_ok=True)
        snapshot = backup / "openbao-raft-acceptance.snap"
        snapshot.write_bytes(b"synthetic-openbao-secret-store" * 80)
        snapshot.chmod(0o600)
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        sidecar = Path(str(snapshot) + ".sha256")
        sidecar.write_text(f"{digest}  {snapshot.name}\n", encoding="utf-8")
        sidecar.chmod(0o600)

        init = root / "opt/jason/bootstrap/secrets/openbao/init.json"
        init.parent.mkdir(parents=True, exist_ok=True)
        init.write_text(
            json.dumps(
                {
                    "unseal_keys_b64": ["share-a", "share-b", "share-c"],
                    "unseal_shares": 3,
                    "unseal_threshold": 2,
                    "root_token": "synthetic-root-token",
                }
            ),
            encoding="utf-8",
        )
        init.chmod(0o600)

        trusted = root / "var/lib/jason/openclaw/trusted-keys"
        trusted.mkdir(parents=True, exist_ok=True)
        registry = trusted / "registry.json"
        registry.write_text('{"keys":[]}', encoding="utf-8")
        registry.chmod(0o600)

    def _export(self, root: Path, name: str) -> tuple[Path, str]:
        self._prepare_openbao_recovery_artifacts(root)
        package, _ = create_encrypted_full_recovery_export(
            target_root=root,
            collection_spec=self.collection_spec,
            state_inventory=self.recovery_inventory,
            external_adapters=BUILTIN_ADAPTERS,
            recipient_public_key=self.recovery_private.public_key(),
            recipient_key_id="synthetic-owner-recovery",
            signer_private_key=self.signer_private,
            signer_key_id="synthetic-recovery-signer",
        )
        output = self.workspace / f"{name}.jrp.json"
        output.unlink(missing_ok=True)
        write_recovery_package_atomic(package, output=output)
        data = output.read_bytes()
        return output, hashlib.sha256(data).hexdigest()

    def _target_manifest(self, current: Mapping[str, Any]) -> dict[str, Any]:
        return build_deployment_manifest(
            DeploymentManifestInputs(
                deployment_id="candidate-upgrade-" + self.source_next[:8],
                instance_id=str(current["instance_id"]),
                environment="candidate",
                release_version="0.1.1",
                source_sha=self.source_next,
                artifact_digest="sha256:" + "2" * 64,
                deployment_revision=str(
                    current["configuration"]["deployment_revision"]
                ),
                msp_configuration_revision=str(
                    current["configuration"]["msp_configuration_revision"]
                ),
                msp_policy_revision=str(
                    current["configuration"]["msp_policy_revision"]
                ),
                playbook_revision=str(
                    current["configuration"]["playbook_revision"]
                ),
                components=tuple(
                    ComponentIdentity(
                        name=str(item["name"]),
                        kind=str(item["kind"]),
                        required=bool(item["required"]),
                        release_version="0.1.1",
                        source_sha=self.source_next,
                        artifact_digest="sha256:" + "2" * 64,
                    )
                    for item in current["components"]
                ),
                schemas=tuple(
                    SchemaIdentity(
                        store=str(item["store"]),
                        version=str(item["version"]),
                    )
                    for item in current["schemas"]
                ),
                providers=tuple(
                    ProviderIdentity(
                        provider_id=str(item["provider_id"]),
                        enabled=bool(item["enabled"]),
                        capability_bundle_revision=item.get(
                            "capability_bundle_revision"
                        ),
                    )
                    for item in current["providers"]
                ),
                runtime=RuntimeIdentity(
                    os=str(current["runtime"]["os"]),
                    architecture=str(current["runtime"]["architecture"]),
                    python=str(current["runtime"]["python"]),
                    container_runtime=str(
                        current["runtime"]["container_runtime"]
                    ),
                    compose=str(current["runtime"]["compose"]),
                ),
            )
        )

    def _checkpoint(self, root: Path, name: str) -> dict[str, Any]:
        path, digest = self._export(root, name)
        return {
            "schema_version": "1.0",
            "source_deployment_identity_sha256": self._manifest(root)[
                "identity_sha256"
            ],
            "recovery_package_sha256": digest,
            "verified": True,
            "restorable": True,
            "_path": str(path),
        }

    def execute_phase(
        self,
        phase: str,
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if phase == "install":
            result = self._bootstrap(self.root_a)
            self.manifest_a = self._manifest(self.root_a)
            return {
                "status": "PASS",
                "summary": "Jason-A installed from immutable synthetic release.",
                "bootstrap_status": result["readiness"]["status"],
                "release_source_sha": self.source_a,
            }

        if phase == "initialize_state":
            required = (
                "var/lib/jason/authority/authority.sqlite3",
                "var/lib/jason/authority/client-boundaries.sqlite3",
                "var/lib/jason/openclaw/orchestration-events.sqlite3",
                "var/lib/jason/openclaw/approval-continuations.sqlite3",
            )
            missing = [
                item for item in required if not (self.root_a / item).is_file()
            ]
            if missing:
                raise SyntheticAcceptanceError(
                    "missing initialized state: " + ",".join(missing)
                )
            return {
                "status": "PASS",
                "summary": "Core durable state initialized.",
                "state_store_count": len(required),
            }

        if phase == "start_candidate":
            return {
                "status": "PASS",
                "summary": (
                    "Synthetic candidate activation boundary reached; "
                    "no host services started in synthetic mode."
                ),
                "activation_mode": "synthetic",
            }

        if phase == "verify_manifest_identity":
            manifest = self._manifest(self.root_a)
            if manifest["platform"]["source_sha"] != self.source_a:
                raise SyntheticAcceptanceError("manifest source identity mismatch")
            return {
                "status": "PASS",
                "summary": "Deployment Manifest identity validated.",
                "deployment_identity_sha256": manifest["identity_sha256"],
            }

        if phase == "verify_ready":
            evidence = self._ready(self.root_a)
            return {
                "status": "PASS",
                "summary": "Candidate READY contract passed.",
                **evidence,
            }

        if phase == "verify_configuration":
            stored_config = json.loads(
                (self.root_a / "etc/jason/msp-configuration.json").read_text()
            )
            stored_policy = json.loads(
                (self.root_a / "etc/jason/msp-policy.json").read_text()
            )
            if stored_config != self.config:
                raise SyntheticAcceptanceError("MSP configuration changed")
            expected_policy = json.loads(self.policy_path.read_text())
            if stored_policy != expected_policy:
                raise SyntheticAcceptanceError("MSP policy changed")
            return {
                "status": "PASS",
                "summary": "MSP configuration and policy validated unchanged.",
            }

        if phase == "verify_governance":
            authority = self.root_a / "var/lib/jason/authority/authority.sqlite3"
            import sqlite3
            with sqlite3.connect(authority) as db:
                tables = {
                    row[0]
                    for row in db.execute(
                        "select name from sqlite_master where type='table'"
                    )
                }
            required = {"identities", "authority_grants"}
            if not required.issubset(tables):
                raise SyntheticAcceptanceError("authority schema incomplete")
            return {
                "status": "PASS",
                "summary": "Authority/governance durable schema present.",
                "authority_table_count": len(tables),
            }

        if phase == "verify_isolation":
            path = self.root_a / "var/lib/jason/authority/client-boundaries.sqlite3"
            store = SQLiteClientBoundaryStore(path)
            repository = SQLiteClientBoundaryRepository(store)
            now = datetime.now(timezone.utc)
            first = ClientBoundary(
                id=self.boundary_id,
                client_id="client-a",
                provider="synthetic-provider",
                external_tenant_id="tenant-shared",
                primary_domain="client-a.example",
                profile="synthetic",
                application_id="app",
                status=BoundaryStatus.VALIDATED,
                consent_transaction_id="consent-a",
                created_at=now,
                validated_at=now,
            )
            repository.add(first)
            conflict = ClientBoundary(
                id="acceptance-boundary-b",
                client_id="client-b",
                provider="synthetic-provider",
                external_tenant_id="tenant-shared",
                primary_domain="client-b.example",
                profile="synthetic",
                application_id="app",
                status=BoundaryStatus.VALIDATED,
                consent_transaction_id="consent-b",
                created_at=now,
                validated_at=now,
            )
            try:
                repository.add(conflict)
            except BoundaryConflictError:
                conflict_blocked = True
            else:
                conflict_blocked = False
            finally:
                store.close()
            if not conflict_blocked:
                raise SyntheticAcceptanceError(
                    "client isolation conflict was not rejected"
                )
            return {
                "status": "PASS",
                "summary": "Conflicting active provider boundary was rejected.",
                "conflict_blocked": True,
            }

        if phase == "verify_provider_connectivity":
            return {
                "status": "PASS",
                "summary": (
                    "Synthetic provider canaries marked healthy; "
                    "real provider connectivity is reserved for host-mode acceptance."
                ),
                "provider_mode": "synthetic",
                "provider_count": len(enabled_provider_ids(self.config)),
            }

        if phase == "exercise_governed_workflow":
            path = self.root_a / "var/lib/jason/openclaw/orchestration-events.sqlite3"
            store = SQLiteOrchestrationEventStore(path)
            event = OrchestrationEvent(
                event_type="acceptance.governed.workflow",
                execution_id="acceptance-execution-1",
                correlation_id="acceptance-correlation-1",
                organization_id="0",
                principal_id="synthetic-owner",
                capability_name="acceptance.synthetic.read",
                stage="verified",
                payload={
                    "authority_checked": True,
                    "mutation_performed": False,
                },
            )
            store.append_event(event)
            readback = store.get(event.event_id)
            store.close()
            if readback is None or not readback.payload["authority_checked"]:
                raise SyntheticAcceptanceError(
                    "governed workflow audit event readback failed"
                )
            return {
                "status": "PASS",
                "summary": "Governed synthetic workflow audit evidence persisted.",
                "event_id": event.event_id,
                "mutation_performed": False,
            }

        if phase == "upgrade":
            current = self._manifest(self.root_a)
            checkpoint = self._checkpoint(
                self.root_a,
                "pre-upgrade-checkpoint",
            )
            target = self._target_manifest(current)
            target_release = (
                self.root_a
                / "opt/jason/releases"
                / self.source_next
            )
            shutil.copytree(
                self.root_a / "opt/jason/releases" / self.source_a,
                target_release,
            )
            plan = plan_upgrade(
                current_manifest=current,
                target_manifest=target,
                migration_catalog={"schema_version": "1.0", "migrations": []},
                checkpoint_receipt={
                    key: value
                    for key, value in checkpoint.items()
                    if not key.startswith("_")
                },
            )
            result = execute_candidate_upgrade(
                target_root=self.root_a,
                plan=plan,
                current_manifest=current,
                target_manifest=target,
                migration_apply=lambda step, root: None,
                migration_reverse=lambda step, root: None,
                verify_target=lambda target_manifest, root: True,
            )
            if result["status"] != "upgraded":
                raise SyntheticAcceptanceError("candidate upgrade failed")
            self.manifest_next = target
            return {
                "status": "PASS",
                "summary": "Candidate upgraded with real checkpoint receipt.",
                "upgrade_plan_sha256": plan.plan_sha256,
                "target_identity_sha256": target["identity_sha256"],
            }

        if phase == "verify_upgraded_identity_health":
            if self.manifest_next is None:
                raise SyntheticAcceptanceError("upgrade target manifest missing")
            current = self._manifest(self.root_a)
            if current["identity_sha256"] != self.manifest_next["identity_sha256"]:
                raise SyntheticAcceptanceError(
                    "upgraded manifest identity mismatch"
                )
            return {
                "status": "PASS",
                "summary": "Upgraded Deployment Manifest identity verified.",
                "deployment_identity_sha256": current["identity_sha256"],
            }

        if phase == "rollback":
            if self.manifest_a is None or self.manifest_next is None:
                raise SyntheticAcceptanceError("rollback manifests unavailable")
            checkpoint = self._checkpoint(
                self.root_a,
                "pre-rollback-checkpoint",
            )
            plan = plan_upgrade(
                current_manifest=self.manifest_next,
                target_manifest=self.manifest_a,
                migration_catalog={"schema_version": "1.0", "migrations": []},
                checkpoint_receipt={
                    key: value
                    for key, value in checkpoint.items()
                    if not key.startswith("_")
                },
            )
            result = execute_candidate_upgrade(
                target_root=self.root_a,
                plan=plan,
                current_manifest=self.manifest_next,
                target_manifest=self.manifest_a,
                migration_apply=lambda step, root: None,
                migration_reverse=lambda step, root: None,
                verify_target=lambda target_manifest, root: True,
            )
            if result["status"] != "upgraded":
                raise SyntheticAcceptanceError("candidate rollback failed")
            return {
                "status": "PASS",
                "summary": "Candidate rolled back to known-good release.",
                "restored_identity_sha256": self._manifest(self.root_a)[
                    "identity_sha256"
                ],
            }

        if phase == "create_full_recovery_export":
            path, digest = self._export(
                self.root_a,
                "full-recovery-acceptance",
            )
            self.full_export_path = path
            return {
                "status": "PASS",
                "summary": "Encrypted Full Recovery Export created.",
                "package_sha256": digest,
                "package_size_bytes": path.stat().st_size,
            }

        if phase == "destroy_recreate_restore":
            if self.full_export_path is None:
                raise SyntheticAcceptanceError("recovery package missing")
            shutil.rmtree(self.root_b, ignore_errors=True)
            package = json.loads(
                self.full_export_path.read_text(encoding="utf-8")
            )
            members = decrypt_recovery_package(
                package,
                recipient_private_key=self.recovery_private,
                signer_public_key=self.signer_private.public_key(),
            )
            plan = plan_recovery_restore(
                decrypted_members=members,
                state_inventory=self.recovery_inventory,
                payload_manifest_schema=self.recovery_payload_schema,
                target_root=self.root_b,
                expected_source_deployment_identity_sha256=(
                    self.manifest_a["identity_sha256"]
                    if self.manifest_a is not None
                    else ""
                ),
            )
            plan = acknowledge_reenrollment(
                plan=plan,
                completed_state_classes=("host-bound-identity",),
            )
            if plan.status != "ready_for_restore":
                raise SyntheticAcceptanceError(
                    "restore plan blocked: " + ",".join(plan.blockers)
                )
            restored = apply_recovery_restore_plan(
                plan=plan,
                decrypted_members=members,
            )
            self._bootstrap(self.root_b, clean=False)
            return {
                "status": "PASS",
                "summary": "Jason-B restored then bootstrapped from released tooling.",
                "restored_payload_count": len(restored["restored"]),
            }

        if phase == "verify_restored_ready_equivalence":
            ready = self._ready(self.root_b)
            if self.manifest_a is None:
                raise SyntheticAcceptanceError("source manifest missing")
            restored_manifest = self._manifest(self.root_b)
            if (
                restored_manifest["identity_sha256"]
                != self.manifest_a["identity_sha256"]
            ):
                raise SyntheticAcceptanceError(
                    "restored deployment identity differs from source"
                )
            store = SQLiteClientBoundaryStore(
                self.root_b
                / "var/lib/jason/authority/client-boundaries.sqlite3"
            )
            repository = SQLiteClientBoundaryRepository(store)
            boundary = repository.get(self.boundary_id)
            store.close()
            if boundary is None or boundary.client_id != "client-a":
                raise SyntheticAcceptanceError(
                    "restored client-boundary durable state missing"
                )
            return {
                "status": "PASS",
                "summary": "Jason-B READY and durable client mapping restored.",
                "deployment_identity_sha256": restored_manifest[
                    "identity_sha256"
                ],
                "boundary_restored": True,
                **ready,
            }

        if phase == "repeat_clean_environment":
            self._bootstrap(self.root_c)
            ready = self._ready(self.root_c)
            if self.manifest_a is None:
                raise SyntheticAcceptanceError("source manifest missing")
            manifest_c = self._manifest(self.root_c)
            if manifest_c["identity_sha256"] != self.manifest_a["identity_sha256"]:
                raise SyntheticAcceptanceError(
                    "repeat clean environment identity is not reproducible"
                )
            return {
                "status": "PASS",
                "summary": "Second clean synthetic environment reproduced identity and READY.",
                "deployment_identity_sha256": manifest_c["identity_sha256"],
                **ready,
            }

        raise SyntheticAcceptanceError(f"unsupported phase: {phase}")


def run_synthetic_zero_to_operational(
    *,
    repository_root: str | Path,
    workspace: str | Path,
):
    executor = SyntheticZeroToOperationalExecutor(
        repository_root=repository_root,
        workspace=workspace,
    )
    return run_zero_to_operational(
        scenario_id="jason-v1-synthetic-zero-to-operational",
        mode="synthetic",
        executor=executor,
    )
