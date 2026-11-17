#!/usr/bin/env python3
"""Fail-closed, READ-ONLY source admission for the AOT Autotask catalog release.

This is one pre-production evidence gate *within* the existing Production
Manager. It cannot issue an Owner approval, create a native release record,
install an image, alter a freeze, or authorize promotion. The normal native
release transaction, protected host identity, locks and rollback remain
mandatory. See docs/engineering/reviews/CATALOG_SCOPED_RELEASE_ADMISSION.md.
"""
from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

SHA = re.compile(r"^[a-f0-9]{40}$")
IMAGE = re.compile(r"^sha256:[a-f0-9]{64}$")
HEX = re.compile(r"^[a-f0-9]{64}$")
PROFILE = "aot-autotask-catalog-runtime-mcp-v1"
SNAPSHOT_REF = re.compile(r"^refs/heads/prep/catalog-identity-grants-isolated-[0-9]{8}(?:-[0-9a-f]{8})?$")
MANIFEST_FILE = "config/catalog-scoped-release-admission.json"
ALLOWED_FILES = frozenset({
    ".github/workflows/security-regressions.yml",
    "docs/engineering/reviews/CATALOG_EXACT_GRANT_ADMIN_20261117.md",
    "docs/engineering/reviews/CATALOG_SERVICE_IDENTITY_20261117.md",
    "implementation/mcp_service/src/jason_mcp/catalog_grant_admin.py",
    "implementation/mcp_service/src/jason_mcp/server.py",
    "implementation/mcp_service/tests/test_autotask_catalog_grant_admin.py",
    "implementation/orchestrator/tests/test_execution_plan_binding.py",
    "implementation/runtime_service/src/jason_runtime/autotask_procurement.py",
    "implementation/runtime_service/tests/test_autotask_catalog_service_identity.py",
})
# Entire-file byte equality for catalog-owned modules/tests. Shared server.py
# is compared at the exact reviewed function boundaries instead.
EXACT_BLOBS = frozenset({
    "implementation/mcp_service/src/jason_mcp/catalog_grant_admin.py",
    "implementation/mcp_service/tests/test_autotask_catalog_grant_admin.py",
    "implementation/orchestrator/tests/test_execution_plan_binding.py",
    "implementation/runtime_service/src/jason_runtime/autotask_procurement.py",
    "implementation/runtime_service/tests/test_autotask_catalog_service_identity.py",
})
SERVER_PATH = "implementation/mcp_service/src/jason_mcp/server.py"
SERVER_FUNCTIONS = frozenset({
    "_authority_admin_or_catalog_self", "_authority_grant_audit",
    "list_exact_authority_grants", "grant_exact_authority",
    "revoke_exact_authority_grant",
})
RUNTIME_MODE = {"JASON_AUTOTASK_CATALOG_AUTH_MODE": "jason_managed"}
MCP_MODE = {"JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE": "aot-catalog-self-owner-v1"}
REQUIRED = frozenset({
    "schema_version", "profile", "protected_feature_sha", "snapshot_sha",
    "rollback_sha", "snapshot_ref", "changed_files", "scope_sha256",
    "runtime_image_id", "mcp_image_id", "rollback_runtime_image_id",
    "rollback_mcp_image_id", "freeze_sha256", "runtime_settings",
    "mcp_settings",
})


class CatalogScopeDenied(PermissionError):
    """No source, grant, release, or production permission is inferred."""


def fail(reason: str) -> None:
    raise CatalogScopeDenied("CATALOG_SCOPED_ADMISSION_" + reason)


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        fail("GIT_EVIDENCE_UNAVAILABLE")
    return result.stdout


def exact_revision(value: object) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        fail("REVISION_INVALID")
    return value


def exact_image(value: object) -> str:
    if not isinstance(value, str) or not IMAGE.fullmatch(value):
        fail("IMAGE_ID_INVALID")
    return value


def load_manifest(repo: Path, *, main_sha: str) -> dict[str, Any]:
    """Always load the signed-by-history version, never an edited worktree."""
    exact_revision(main_sha)
    try:
        manifest = json.loads(git(repo, "show", f"{main_sha}:{MANIFEST_FILE}"))
    except (ValueError, UnicodeError) as exc:
        raise CatalogScopeDenied("CATALOG_SCOPED_ADMISSION_MANIFEST_UNPARSEABLE") from exc
    if not isinstance(manifest, dict) or set(manifest) != REQUIRED:
        fail("MANIFEST_SCHEMA_INVALID")
    if manifest["schema_version"] != "1.0" or manifest["profile"] != PROFILE:
        fail("MANIFEST_PROFILE_INVALID")
    for key in ("protected_feature_sha", "snapshot_sha", "rollback_sha"):
        exact_revision(manifest[key])
    for key in ("runtime_image_id", "mcp_image_id", "rollback_runtime_image_id", "rollback_mcp_image_id"):
        exact_image(manifest[key])
    if not isinstance(manifest["scope_sha256"], str) or not HEX.fullmatch(manifest["scope_sha256"]):
        fail("SCOPE_DIGEST_INVALID")
    if not isinstance(manifest["freeze_sha256"], str) or not HEX.fullmatch(manifest["freeze_sha256"]):
        fail("FREEZE_DIGEST_INVALID")
    if not isinstance(manifest["snapshot_ref"], str) or not SNAPSHOT_REF.fullmatch(manifest["snapshot_ref"]):
        fail("SNAPSHOT_REF_INVALID")
    allowed = manifest["changed_files"]
    if (not isinstance(allowed, list) or allowed != sorted(set(allowed))
            or not set(allowed).issubset(ALLOWED_FILES)
            or not set(allowed).intersection(EXACT_BLOBS | {SERVER_PATH})):
        fail("CHANGED_FILES_INVALID")
    if manifest["runtime_settings"] != RUNTIME_MODE or manifest["mcp_settings"] != MCP_MODE:
        fail("DEPLOY_SETTINGS_INVALID")
    if manifest["snapshot_sha"] == manifest["rollback_sha"]:
        fail("EMPTY_SOURCE_DELTA")
    return manifest


def exact_function_source(text: str, name: str) -> bytes:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise CatalogScopeDenied("CATALOG_SCOPED_ADMISSION_SHARED_SOURCE_INVALID") from exc
    matches = [node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        fail("SHARED_FUNCTION_MISSING_OR_DUPLICATE")
    source = ast.get_source_segment(text, matches[0])
    if source is None:
        fail("SHARED_FUNCTION_SOURCE_UNAVAILABLE")
    return source.encode("utf-8")



def noncatalog_top_level(text: str) -> tuple[str, ...]:
    try:
        nodes = ast.parse(text).body
    except SyntaxError as exc:
        raise CatalogScopeDenied("CATALOG_SCOPED_ADMISSION_SHARED_SOURCE_INVALID") from exc
    return tuple(ast.dump(node, include_attributes=False) for node in nodes
                 if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                         and node.name in SERVER_FUNCTIONS))


def verified_source_scope(
    repo: Path, manifest: Mapping[str, Any], *, main_sha: str,
    advertised_snapshot_sha: str,
) -> dict[str, Any]:
    """Validate all code and scope evidence against protected immutable Git."""
    exact_revision(main_sha)
    if advertised_snapshot_sha != manifest["snapshot_sha"]:
        fail("PUBLISHED_SNAPSHOT_CHANGED")
    origin_url = git(repo, "remote", "get-url", "origin").decode().strip().lower()
    if origin_url not in {
        "https://github.com/al-teamaot-com/jason.git",
        "https://github.com/al-teamaot-com/jason",
        "git@github.com:al-teamaot-com/jason.git",
        "ssh://git@github.com/al-teamaot-com/jason.git",
    }:
        fail("REPOSITORY_ORIGIN_INVALID")
    # Never infer main identity from a local developer branch or stale ref.
    remote_main = git(repo, "ls-remote", "origin", "refs/heads/main").decode().strip().split()
    if len(remote_main) != 2 or remote_main != [main_sha, "refs/heads/main"]:
        fail("PROTECTED_MAIN_CHANGED")
    if git(repo, "rev-parse", "refs/remotes/origin/main").decode().strip() != main_sha:
        fail("PROTECTED_MAIN_REF_STALE")
    feature = exact_revision(manifest["protected_feature_sha"])
    snapshot = exact_revision(manifest["snapshot_sha"])
    rollback = exact_revision(manifest["rollback_sha"])
    if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", feature, main_sha],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        fail("FEATURE_NOT_PROTECTED")
    if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", rollback, snapshot],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        fail("SNAPSHOT_BASELINE_MISMATCH")
    selected = git(repo, "diff", "--no-renames", "--name-only", rollback, snapshot).decode().splitlines()
    declared = set(manifest["changed_files"])
    if set(selected) != declared or len(selected) != len(declared):
        fail("SOURCE_PATH_SCOPE_EXPANDED")
    actual_diff_sha = sha256(git(repo, "diff", "--binary", rollback, snapshot)).hexdigest()
    if actual_diff_sha != manifest["scope_sha256"]:
        fail("SNAPSHOT_SCOPE_DIGEST_CHANGED")
    for path in EXACT_BLOBS:
        original = git(repo, "show", f"{snapshot}:{path}")
        if (original != git(repo, "show", f"{feature}:{path}")
                or original != git(repo, "show", f"{main_sha}:{path}")):
            fail("CATALOG_SOURCE_BLOB_CHANGED")
    try:
        original = git(repo, "show", f"{snapshot}:{SERVER_PATH}").decode("utf-8")
        baseline = git(repo, "show", f"{rollback}:{SERVER_PATH}").decode("utf-8")
        protected = git(repo, "show", f"{feature}:{SERVER_PATH}").decode("utf-8")
        current = git(repo, "show", f"{main_sha}:{SERVER_PATH}").decode("utf-8")
    except UnicodeError as exc:
        raise CatalogScopeDenied("CATALOG_SCOPED_ADMISSION_SHARED_SOURCE_INVALID") from exc
    # The snapshot may alter ONLY the five reviewed MCP catalog functions.
    # Any unrelated top-level import, global, endpoint or ticket function edit
    # must fail even if the manifest and feature source were both repinned.
    if noncatalog_top_level(baseline) != noncatalog_top_level(original):
        fail("NONCATALOG_SHARED_SOURCE_DELTA")
    for name in sorted(SERVER_FUNCTIONS):
        scope_fn = exact_function_source(original, name)
        if (scope_fn != exact_function_source(protected, name)
                or scope_fn != exact_function_source(current, name)):
            fail("CATALOG_SHARED_FUNCTION_CHANGED")
    # Exact SEC-007 catalog checks must be present in protected source.
    checks = git(repo, "show", f"{feature}:.github/workflows/security-regressions.yml")
    main_checks = git(repo, "show", f"{main_sha}:.github/workflows/security-regressions.yml")
    for name in ("test_autotask_catalog_grant_admin.py", "test_autotask_catalog_service_identity.py"):
        if name.encode() not in checks or name.encode() not in main_checks:
            fail("CATALOG_SECURITY_CI_MISSING")
    return {
        "verified_main_sha": main_sha,
        "verified_protected_feature_sha": feature,
        "snapshot_source_sha": snapshot,
        "rollback_source_sha": rollback,
        "changed_files": sorted(declared),
        "source_diff_sha256": actual_diff_sha,
        "shared_function_count": len(SERVER_FUNCTIONS),
        "blob_equality_count": len(EXACT_BLOBS),
        "protected_source_checks_present": True,
    }


def verify_live_image_evidence(manifest: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, Any]:
    """Require unmodified baseline, original freeze and dual immutable images."""
    expected = {
        "runtime_revision": manifest["rollback_sha"],
        "mcp_revision": manifest["rollback_sha"],
        "host_revision": manifest["rollback_sha"],
        "runtime_image_id": manifest["rollback_runtime_image_id"],
        "mcp_image_id": manifest["rollback_mcp_image_id"],
        "candidate_runtime_image_id": manifest["runtime_image_id"],
        "candidate_mcp_image_id": manifest["mcp_image_id"],
        "candidate_runtime_label": manifest["snapshot_sha"],
        "candidate_mcp_label": manifest["snapshot_sha"],
        "freeze_sha256": manifest["freeze_sha256"],
    }
    if not isinstance(observed, Mapping) or any(observed.get(k) != v for k,v in expected.items()):
        fail("LIVE_SOURCE_IMAGE_OR_FREEZE_DRIFT")
    if any(observed.get(k) is not True for k in ("runtime_running", "mcp_running", "runtime_healthy")):
        fail("LIVE_RUNTIME_UNHEALTHY")
    if (observed.get("runtime_auth_mode") is not None
            or observed.get("mcp_grant_admin_profile") is not None
            or observed.get("shared_owner_admin_profile") not in (None, "")
            or observed.get("global_owner_allowlist") != "person-al"):
        fail("UNAPPROVED_LIVE_IDENTITY_CHANGE")
    if observed.get("rollback_images_available") is not True:
        fail("ROLLBACK_IMAGES_MISSING")
    return {"rollback_sha":manifest["rollback_sha"],
            "rollback_runtime_image_id":manifest["rollback_runtime_image_id"],
            "rollback_mcp_image_id":manifest["rollback_mcp_image_id"],
            "candidate_runtime_image_id":manifest["runtime_image_id"],
            "candidate_mcp_image_id":manifest["mcp_image_id"],
            "freeze_sha256":manifest["freeze_sha256"],
            "live_runtime_health":"healthy", "live_mcp_running":True,
            "global_owner_permissions_unchanged":True}


def source_scope_receipt(manifest: Mapping[str, Any], source: Mapping[str, Any],
                         live: Mapping[str, Any], ci: Mapping[str, Any]) -> dict[str, Any]:
    """Return a reproducible preflight receipt with NO release authority."""
    if (not isinstance(ci, Mapping) or ci.get("passed") is not True
            or ci.get("failures") != []
            or not isinstance(ci.get("required"), list)
            or "governed-security-regressions" not in ci["required"]):
        fail("PROTECTED_SECURITY_CI_NOT_GREEN")
    result = {
        "schema_version":"1.0",
        "status":"SOURCE_SCOPE_VERIFIED_NOT_PRODUCTION_ELIGIBLE",
        "profile":PROFILE,
        "protected_source":dict(source),
        "dual_image_rollback":dict(live),
        "protected_ci":{"passed":True,"source_sha":manifest["protected_feature_sha"],
                        "required_checks":list(ci["required"])},
        "deployment_configuration":{"runtime":dict(RUNTIME_MODE),"mcp":dict(MCP_MODE)},
        "production_mutations":False,
        "provider_writes":False,
        "owner_approval_recorded":False,
        "native_production_eligible_record_created":False,
        "separate_exact_release_approval_required":True,
        "separate_catalog_test_write_approval_required":True,
        "existing_native_release_promotion_unchanged":True,
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result["receipt_sha256"] = sha256(canonical).hexdigest()
    return result


def _inspect_json(*argv: str) -> dict[str, Any]:
    result = subprocess.run(argv, check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if result.returncode:
        fail("LIVE_DOCKER_EVIDENCE_UNAVAILABLE")
    try:
        values = json.loads(result.stdout)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise CatalogScopeDenied("CATALOG_SCOPED_ADMISSION_DOCKER_EVIDENCE_INVALID") from exc
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        fail("DOCKER_EVIDENCE_SHAPE_INVALID")
    return values[0]


def host_readback(manifest: Mapping[str, Any], *, freeze_path: Path = Path(
        "/var/lib/jason/openclaw/release-manager/production-deployment-freeze"),
                  host_source: Path = Path("/opt/jason/current")) -> dict[str, Any]:
    """Inspect Docker and freeze in memory only. Never return raw environment."""
    runtime = _inspect_json("docker", "inspect", "jason-runtime")
    mcp = _inspect_json("docker", "inspect", "jason-mcp-pilot")
    runtime_image = _inspect_json("docker", "image", "inspect", manifest["runtime_image_id"])
    mcp_image = _inspect_json("docker", "image", "inspect", manifest["mcp_image_id"])
    rollback_runtime = _inspect_json("docker", "image", "inspect", manifest["rollback_runtime_image_id"])
    rollback_mcp = _inspect_json("docker", "image", "inspect", manifest["rollback_mcp_image_id"])
    if not freeze_path.is_file() or freeze_path.is_symlink() or not host_source.is_symlink():
        fail("PRODUCTION_ROOT_EVIDENCE_MISSING")
    try:
        frozen = freeze_path.read_bytes()
        if not isinstance(json.loads(frozen), dict):
            fail("FREEZE_FORMAT_INVALID")
    except (OSError, ValueError) as exc:
        raise CatalogScopeDenied("CATALOG_SCOPED_ADMISSION_FREEZE_UNREADABLE") from exc
    def env_value(container: Mapping[str, Any], key: str) -> str | None:
        raw = (container.get("Config") or {}).get("Env") or []
        if not isinstance(raw, list):
            fail("CONTAINER_ENV_INVALID")
        values = [value.partition("=")[2] for value in raw
                  if isinstance(value, str) and value.partition("=")[0] == key]
        if len(values) > 1:
            fail("DUPLICATE_LIVE_ENVIRONMENT_KEY")
        return values[0] if values else None
    return {
        "runtime_revision": (runtime.get("Config") or {}).get("Labels", {}).get("com.teamaot.jason.source_revision"),
        "mcp_revision": (mcp.get("Config") or {}).get("Labels", {}).get("com.teamaot.jason.source_revision"),
        "host_revision": host_source.resolve(strict=True).name,
        "runtime_image_id": runtime.get("Image"),
        "mcp_image_id": mcp.get("Image"),
        "candidate_runtime_image_id": runtime_image.get("Id"),
        "candidate_mcp_image_id": mcp_image.get("Id"),
        "candidate_runtime_label": (runtime_image.get("Config") or {}).get("Labels", {}).get("com.teamaot.jason.source_revision"),
        "candidate_mcp_label": (mcp_image.get("Config") or {}).get("Labels", {}).get("com.teamaot.jason.source_revision"),
        "runtime_running": (runtime.get("State") or {}).get("Running") is True,
        "mcp_running": (mcp.get("State") or {}).get("Running") is True,
        "runtime_healthy": (runtime.get("State") or {}).get("Health", {}).get("Status") == "healthy",
        "runtime_auth_mode": env_value(runtime, "JASON_AUTOTASK_CATALOG_AUTH_MODE"),
        "mcp_grant_admin_profile": env_value(mcp, "JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE"),
        "shared_owner_admin_profile": env_value(mcp, "JASON_AOT_ADMIN_APPROVER_PROFILE"),
        "global_owner_allowlist": env_value(mcp, "JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES"),
        "rollback_images_available": (rollback_runtime.get("Id") == manifest["rollback_runtime_image_id"]
                                      and rollback_mcp.get("Id") == manifest["rollback_mcp_image_id"]),
        "freeze_sha256": sha256(frozen).hexdigest(),
    }


def verify_native_preflights(manifest: Mapping[str, Any], *, script: Path = Path(
        "/opt/jason/current/tools/deploy_live_container.py")) -> dict[str, Any]:
    """Mandatory read-only deploy preflights; no container replacement."""
    if not script.is_file() or script.is_symlink():
        fail("PINNED_NATIVE_PREFLIGHT_UNAVAILABLE")
    specs = (
        ("runtime", "jason-runtime", "runtime_image_id", RUNTIME_MODE,
         "http://127.0.0.1:8080/healthz"),
        ("mcp", "jason-mcp-pilot", "mcp_image_id", MCP_MODE,
         "http://127.0.0.1:8000/healthz"),
    )
    verified: dict[str, Any] = {}
    for kind, live, key, setting, health in specs:
        env_key, env_value = next(iter(setting.items()))
        argv = [
            "python3", str(script), "--live", live,
            "--image", manifest[key], "--rollback", f"admission-readonly-{live}",
            "--source-revision", manifest["snapshot_sha"],
            "--health-url", health, "--harden", "--set-env",
            env_key + "=" + env_value, "--preflight",
        ]
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        if result.returncode:
            fail("NATIVE_PREFLIGHT_FAILED")
        try:
            fields = {}
            for line in result.stdout.decode("utf-8").splitlines():
                if "=" in line:
                    name, value = line.split("=", 1)
                    if name in fields:
                        fail("NATIVE_PREFLIGHT_DUPLICATE_FIELD")
                    fields[name] = value
        except UnicodeError as exc:
            raise CatalogScopeDenied("CATALOG_SCOPED_ADMISSION_PREFLIGHT_UNREADABLE") from exc
        if (fields.get("PREFLIGHT") != "PASS" or fields.get("LIVE_CONTAINER") != live
                or fields.get("CANDIDATE_IMAGE_ID") != manifest[key]
                or fields.get("SOURCE_IMAGE_ID") != manifest[
                    "rollback_runtime_image_id" if kind == "runtime" else "rollback_mcp_image_id"
                ] or fields.get("SET_ENV_COUNT") != "1"
                or fields.get("ADDITIONAL_READONLY_BIND_COUNT") != "0"):
            fail("NATIVE_PREFLIGHT_READBACK_MISMATCH")
        verified[kind] = {"preflight":"PASS", "image_id": manifest[key],
                          "exact_env_key":env_key, "additional_binds":0}
    return verified


def attest_source_scope(repo: Path, *, native_ci_checks: Any) -> dict[str, Any]:
    """Nonmutating Production Manager admission command (NOT a release)."""
    remote = git(repo, "ls-remote", "origin", "refs/heads/main").decode().strip().split()
    if len(remote) != 2 or remote[1] != "refs/heads/main":
        fail("PROTECTED_MAIN_UNAVAILABLE")
    main_sha = exact_revision(remote[0])
    manifest = load_manifest(repo, main_sha=main_sha)
    published = git(repo, "ls-remote", "origin", manifest["snapshot_ref"]).decode().strip().split()
    if len(published) != 2 or published[1] != manifest["snapshot_ref"]:
        fail("PUBLISHED_SNAPSHOT_UNAVAILABLE")
    source = verified_source_scope(repo, manifest, main_sha=main_sha,
                                   advertised_snapshot_sha=published[0])
    observed = host_readback(manifest)
    live = verify_live_image_evidence(manifest, observed)
    ci = native_ci_checks(manifest["protected_feature_sha"])
    evidence = source_scope_receipt(manifest, source, live, ci)
    evidence["native_readonly_preflight"] = verify_native_preflights(manifest)
    # Bind the same exact preflight outcomes into the auditable final receipt.
    material = dict(evidence)
    material.pop("receipt_sha256")
    evidence["receipt_sha256"] = sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    # An unrelated release or branch update during the preflight must not
    # produce a stale pass. Re-read both independently before returning.
    refreshed = git(repo, "ls-remote", "origin", "refs/heads/main").decode().strip().split()
    if refreshed != [main_sha, "refs/heads/main"]:
        fail("PROTECTED_MAIN_CHANGED_DURING_PREFLIGHT")
    verify_live_image_evidence(manifest, host_readback(manifest))
    return evidence
