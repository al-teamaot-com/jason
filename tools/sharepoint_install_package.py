#!/usr/bin/env python3
"""Assemble an immutable SharePoint installation/rollback REVIEW package.

This is a pure configuration planner and source bundler, not a release engine.
There is deliberately no apply command, privilege escalation, provider login,
Owner signer, production database write or Docker execution. The installed
native Release Manager must admit and execute the reviewed changes separately.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import zipfile

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
APP = "c5692fec-3f78-44db-9a15-59c3e3bcac58"
SP = "36b03282-289c-4da3-8243-accb0b1e7f1e"
SITE = "absolnet.sharepoint.com,8f4cd7bf-72b8-4f7e-9803-c47abcbb232f,e5b7a724-dc9b-406b-aed8-2961f1f71153"
SITE_URL = "https://absolnet.sharepoint.com/sites/AOTAccountingDocuments"
HOSTS = ["absolnet.sharepoint.com", "absolnet-web.sharepoint.com"]
PROFILE = "aot-sharepoint-read-v1"
ROLE_DIR = "/opt/jason/bootstrap/secrets/openbao/microsoft-graph-sharepoint-read-approle"
VOLUME = "jason-sharepoint-site-state"
CONTAINER = "jason-sharepoint-site-control"
SERVICE = "jason-sharepoint-discovery.service"
TIMER = "jason-sharepoint-discovery.timer"
SHA = re.compile(r"[0-9a-f]{40}")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}")
ENV = {
    "JASON_SHAREPOINT_READER_PROFILE": PROFILE,
    "JASON_SHAREPOINT_AOT_TENANT_ID": TENANT,
    "JASON_SHAREPOINT_BOUNDARY_DB": "/var/lib/jason/authority/client-boundaries.sqlite3",
    "JASON_SHAREPOINT_SITE_ACCESS_DB": "/var/lib/jason/sharepoint/sites.sqlite3",
    "JASON_SHAREPOINT_OPENBAO_ROLE_ID_PATH": "/run/jason-secrets/openbao/sharepoint/role-id",
    "JASON_SHAREPOINT_OPENBAO_SECRET_ID_PATH": "/run/jason-secrets/openbao/sharepoint/secret-id",
}
MOUNTS = [
    {"Type": "bind", "Source": ROLE_DIR,
     "Target": "/run/jason-secrets/openbao/sharepoint", "ReadOnly": True},
    {"Type": "volume", "Source": VOLUME,
     "Target": "/var/lib/jason/sharepoint", "ReadOnly": False},
]
FIXED_FILES = (
    "tools/sharepoint_install_package.py",
    "tools/sharepoint_boundary_bootstrap.py",
    "tools/sharepoint_release_preflight.py",
    "tools/sharepoint_site_access_service.py",
    "tools/sharepoint_grafana_install.py",
    "tools/tests/test_sharepoint_install_package.py",
    "implementation/connectors/core/openbao_secrets.py",
    "implementation/runtime_service/src/jason_runtime/microsoft_sharepoint.py",
    "implementation/runtime_service/src/jason_runtime/sharepoint_read_activation.py",
    "implementation/runtime_service/src/jason_runtime/sharepoint_reads.py",
    "implementation/runtime_service/src/jason_runtime/composition.py",
    "implementation/orchestrator/sharepoint_capability_catalog.py",
    "docs/releases/SharePoint-Install-Rollback-20261123.md",
)
PREFIXES = ("infrastructure/sharepoint-site-control/",
            "implementation/connectors/microsoft_graph/")


class PackageDenied(PermissionError):
    pass


def need(condition, code):
    if not condition:
        raise PackageDenied("SHAREPOINT_PACKAGE_" + code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest(value):
    return sha256(value).hexdigest()


def initial_site_request():
    """Record the exact requested target, never manufacture an Owner decision."""
    return {
        "tenant_id": TENANT, "site_id": SITE, "site_url": SITE_URL,
        "desired_enabled": True,
        "request_source": "owner_conversation_2026-11-23",
        "live_graph_identity_revalidation_required": True,
        "independent_owner_verification_required": True,
        "independent_owner_approval_recorded": False,
        "production_applied": False,
        "other_initial_sites_enabled": [],
        "document_content_release": "unchanged_separately_governed",
        "provider_permission_changes": False,
    }


def policy_changes(before):
    """Compute only three additive policy entries, preserving the whole policy."""
    after = deepcopy(before)
    need(before.get("schema_version") == "1.0", "POLICY_SCHEMA")
    additions = {}
    for key, values in (
        ("allowed_running_containers", [CONTAINER]),
        ("allowed_system_units", [SERVICE, TIMER]),
    ):
        old = before.get(key)
        need(isinstance(old, list) and all(type(x) is str for x in old)
             and len(old) == len(set(old)), "POLICY_LIST")
        additions[key] = [x for x in values if x not in old]
        after[key] += additions[key]
    return {"before": deepcopy(before), "after": after, "additions": additions}


def rollback_policy(current, change):
    # Never overwrite a newer accepted production policy with a stale backup.
    need(current == change["after"], "POLICY_CHANGED_SINCE_INSTALL")
    need(policy_changes(change["before"]) == change, "POLICY_ROLLBACK_MATERIAL")
    return deepcopy(change["before"])


def container_projection(before, *, role, candidate_image=None):
    """Plan the native container delta; no Docker command is executed here.

    Input is a PRIVATE root-owned before-image normalized to Docker's create
    configuration. Do not serialize live Config.Env into a review package.
    """
    need(role in ("jason-runtime", "jason-grafana"), "CONTAINER_SCOPE")
    need(isinstance(before, dict) and isinstance(before.get("HostConfig"), dict)
         and isinstance(before.get("Env"), list), "CONTAINER_BEFORE_IMAGE")
    result = deepcopy(before)
    env = {}
    order = []
    for item in before["Env"]:
        need(type(item) is str and "=" in item, "CONTAINER_ENV")
        key, value = item.split("=", 1)
        need(key not in env, "DUPLICATE_ENV")
        env[key] = value
        order.append(key)
    additions = ENV if role == "jason-runtime" else {"GF_DATAPROXY_SEND_USER_HEADER": "true"}
    if role == "jason-runtime":
        need(isinstance(candidate_image, str) and IMAGE.fullmatch(candidate_image), "PINNED_RUNTIME_IMAGE")
        result["Image"] = candidate_image
    else:
        need(candidate_image is None, "GRAFANA_IMAGE_CHANGE_DENIED")
    for key, value in additions.items():
        allowed = ("", value, "false") if role == "jason-grafana" else ("", value)
        need(key not in env or env[key] in allowed, "FOREIGN_PROFILE")
        if key not in env:
            order.append(key)
        env[key] = value
    result["Env"] = [key + "=" + env[key] for key in order]
    if role == "jason-runtime":
        mounts = result["HostConfig"].setdefault("Mounts", [])
        need(isinstance(mounts, list), "MOUNT_SCHEMA")
        reserved = {mount["Target"] for mount in MOUNTS}
        for bind in result["HostConfig"].get("Binds") or []:
            need(isinstance(bind, str) and ":" in bind, "BIND_SCHEMA")
            need(bind.split(":")[1] not in reserved, "MOUNT_CONFLICT")
        for wanted in MOUNTS:
            existing = [m for m in mounts if m.get("Target") == wanted["Target"]]
            need(not existing or existing == [wanted], "MOUNT_CONFLICT")
            if not existing:
                mounts.append(deepcopy(wanted))
    return result


def rollback_container(current, before, installed):
    need(current == installed, "CONTAINER_CHANGED_SINCE_INSTALL")
    return deepcopy(before)


def installation_plan(source_sha, baseline):
    need(isinstance(source_sha, str) and SHA.fullmatch(source_sha), "EXACT_SOURCE_SHA")
    need(set(baseline) == {"runtime_image", "mcp_image", "runtime_source", "observed_at"},
         "BASELINE_FIELDS")
    need(all(IMAGE.fullmatch(baseline[k]) for k in ("runtime_image", "mcp_image"))
         and SHA.fullmatch(baseline["runtime_source"])
         and isinstance(baseline["observed_at"], str) and baseline["observed_at"],
         "BASELINE_IDENTITY")
    steps = [
        ("seal_before_images", "Native root preflight seals current protected policy, container configurations, exact authority binding and Grafana UID absence; verify source, CI, freeze, rollback, locks and Owner proof."),
        ("admit_exact_policy_delta", "Add only jason-sharepoint-site-control and the discovery service/timer to the effective root policy, retaining all existing entries and a private before-image."),
        ("validate_aot_boundary", "Run the existing exact-SHA app-only certificate/token/Graph bootstrap, then create/read back only the dedicated AOT SharePoint-read binding; audit before advancing."),
        ("provision_private_state", "Provision the shared site-state volume and private service token; mount existing dedicated AppRole read-only; verify UID1000 access without printing secrets or widening host ACLs."),
        ("discover_disabled_sites", "Deploy the exact sidecar image, complete app-only discovery across the two exact allowed hosts, and confirm every newly discovered site starts disabled."),
        ("enable_accounting_site", "Independently verify the Owner and exact Accounting site identity; use the governed administration service with expected revision and audit, then read back this one enabled site."),
        ("activate_native_reader", "Use the native exact-image Release Manager transaction to add the explicit profile, tenant, credential mounts and shared registry; preserve unrelated settings and protected Ticket Core."),
        ("activate_grafana_controls", "Through native container configuration replacement enable only authenticated user forwarding on the existing Grafana image; create only the two reviewed Grafana UIDs and verify Owner toggle/readback."),
        ("accept_then_enable_timer", "Verify permitted reads, disabled/cross-tenant denials, immediate revoke, protected peers and drift; install exact 04:30 America/New_York units and enable the timer only after acceptance."),
    ]
    rollback = [
        "Disable only the newly installed discovery timer first; record and retain the service's prior enable/active state.",
        "Use the native runtime rollback with its private exact before-image; remove only newly introduced SharePoint profile/mounts and restore the pinned prior image.",
        "Remove only newly created Grafana dashboard/datasource UIDs after ownership/readback checks; restore the prior Grafana container configuration and original image.",
        "Stop/remove only the new site-control component and its owned unit files; retain the site registry, discovery/audit history and private token reference.",
        "Restore the effective root policy only when it still exactly matches this transaction's after-image; on concurrent changes stop and reconcile rather than overwrite newer policy.",
        "Revoke only the binding created by this transaction if unchanged and no later consumer exists, using Jason's boundary service; never restore the entire live authority database.",
        "Preserve all later site decisions, audit events and authority grants; restore neither the site database nor the authority database from a whole-file backup.",
        "Revalidate protected peers, original freeze/hold, native drift and observability; retain all receipts and report unresolved rollback conflicts.",
    ]
    return {
        "schema_version": "1.0", "kind": "sharepoint_install_rollback_review_package",
        "repository": "al-teamaot-com/jason", "source_sha": source_sha,
        "production_authority": False, "production_ready": False,
        "production_changes_performed": False,
        "native_release_required": True, "root_before_images_required": True,
        "baseline_observation_not_release_acceptance": deepcopy(baseline),
        "reader": {"tenant_id": TENANT, "application_id": APP,
                   "service_principal_id": SP, "client_id": "client-aot-internal",
                   "permission_profile": "sharepoint-read", "activation_profile": PROFILE,
                   "allowed_hosts": HOSTS},
        "initial_site_request": initial_site_request(),
        "runtime_environment_delta": ENV, "runtime_mount_delta": MOUNTS,
        "grafana_environment_delta": {"GF_DATAPROXY_SEND_USER_HEADER": "true"},
        "grafana_create_only_uids": ["jason-sharepoint-control", "jason-sharepoint-site-access"],
        "grafana_existing_uid_policy": "deny_conflict_or_reuse_without_modification; never overwrite an unrecoverable stored secret",
        "daily_discovery": {"on_calendar": "*-*-* 04:30:00 America/New_York",
                            "new_sites_enabled": False, "timer_enabled_last": True},
        "installation_steps": [{"order": i, "action": action, "requirements": requirements}
                               for i, (action, requirements) in enumerate(steps, 1)],
        "rollback_steps": [{"order": i, "requirements": text}
                           for i, text in enumerate(rollback, 1)],
        "protected_services_never_restarted": ["jason-pmv4-ticket-core", "jason-mcp-pilot", "jason-teams-gateway", "openbao"],
        "excluded": ["SharePoint file writes", "tenant consent changes", "credential rotation",
                     "bank-statement organizer activation", "PMv4 or shared approval-engine changes"],
        "required_live_evidence": ["current_source_and_CI", "root_policy_before_image",
            "native_runtime_projection_admission", "independent_owner_site_decision",
            "app_only_Graph_site_identity", "validated_boundary_readback",
            "governed_MCP_read_and_denials", "authenticated_Grafana_round_trip",
            "timer_triggered_real_discovery", "protected_peers_and_rollback_readback"],
    }


def _git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], timeout=45)


def _source_files(repo, source_sha):
    raw = _git(repo, "ls-tree", "-rz", "--full-tree", source_sha)
    selected = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        head, name = entry.split(b"\t", 1)
        name = name.decode("utf-8")
        if name not in FIXED_FILES and not name.startswith(PREFIXES):
            continue
        need(head.startswith(b"100644 blob ") or head.startswith(b"100755 blob "), "SOURCE_NOT_REGULAR")
        need(not name.startswith("/") and ".." not in Path(name).parts, "SOURCE_PATH")
        selected[name] = _git(repo, "show", source_sha + ":" + name)
    need(set(FIXED_FILES) <= set(selected), "SOURCE_CLOSURE_INCOMPLETE")
    return selected


def prepare(repo, source_sha, baseline, destination):
    repo, destination = Path(repo), Path(destination)
    need(SHA.fullmatch(source_sha), "EXACT_SOURCE_SHA")
    need(destination.is_absolute() and ".." not in destination.parts
         and destination.resolve() == destination and not destination.exists()
         and not destination.is_symlink(), "OUTPUT_PATH_OR_REPLACEMENT")
    need(not any(destination == p or p in destination.parents for p in map(Path,
         ("/opt/jason", "/etc", "/var/lib/jason", "/run"))), "PROTECTED_OUTPUT")
    need(_git(repo, "rev-parse", "HEAD").decode().strip() == source_sha
         and not _git(repo, "status", "--porcelain").strip(), "SOURCE_DIRTY_OR_MISMATCH")
    files = _source_files(repo, source_sha)
    plan = installation_plan(source_sha, baseline)
    payload = {"plan.json": canonical(plan)}
    payload.update({"source/" + name: data for name, data in files.items()})
    manifest = {"schema_version": "1.0", "source_sha": source_sha,
                "files_sha256": {name: digest(data) for name, data in sorted(payload.items())},
                "production_authority": False}
    payload["manifest.json"] = canonical(manifest)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 23, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100444 << 16
            archive.writestr(info, data)
    return verify(repo, source_sha, destination)


def verify(repo, source_sha, package):
    need(isinstance(source_sha, str) and SHA.fullmatch(source_sha), "EXACT_SOURCE_SHA")
    source = _source_files(Path(repo), source_sha)
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        expected_names = {"manifest.json", "plan.json"} | {"source/" + n for n in source}
        need(len(names) == len(set(names)) and set(names) == expected_names, "ARCHIVE_FILE_SET")
        need(all((info.external_attr >> 16) & 0o170000 == 0o100000
                 and not info.flag_bits & 1 for info in archive.infolist()), "ARCHIVE_MEMBER_TYPE")
        need(sum(x.file_size for x in archive.infolist()) < 16 * 1024 * 1024, "ARCHIVE_SIZE")
        manifest = json.loads(archive.read("manifest.json"))
        plan = json.loads(archive.read("plan.json"))
        need(plan == installation_plan(source_sha, plan["baseline_observation_not_release_acceptance"]), "PLAN_DRIFT")
        expected = {"plan.json": digest(canonical(plan))}
        expected.update({"source/" + name: digest(data) for name, data in source.items()})
        need(manifest == {"schema_version": "1.0", "source_sha": source_sha,
                          "files_sha256": dict(sorted(expected.items())),
                          "production_authority": False}, "MANIFEST_DRIFT")
        need(all(digest(archive.read(name)) == checksum for name, checksum in expected.items()), "PAYLOAD_DRIFT")
    return {"status": "review_package_verified", "source_sha": source_sha,
            "package_sha256": digest(Path(package).read_bytes()),
            "source_file_count": len(source), "production_ready": False,
            "production_changes_performed": False, "site_approval_applied": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("prepare", "verify"))
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--source-sha", required=True)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--baseline", type=Path)
    args = p.parse_args()
    try:
        if args.command == "prepare":
            need(args.baseline is not None, "BASELINE_REQUIRED")
            result = prepare(args.repo, args.source_sha,
                             json.loads(args.baseline.read_bytes()), args.package)
        else:
            result = verify(args.repo, args.source_sha, args.package)
    except (PackageDenied, ValueError, OSError, KeyError, subprocess.SubprocessError,
            zipfile.BadZipFile) as exc:
        p.exit(2, "DENIED: " + str(exc) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
