"""Release material, real SQLite/HTTP switches, and conflict-safe rollback."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import pytest

from tools import sharepoint_install_package as package
from connectors.microsoft_graph.site_access_registry import SharePointSiteAccess
from connectors.microsoft_graph.site_access_admin import GovernedSiteAccessAdministration
from connectors.microsoft_graph.site_control_http import make_handler


def baseline():
    return {"runtime_source": "a" * 40, "runtime_image": "sha256:" + "b" * 64,
            "mcp_image": "sha256:" + "c" * 64,
            "observed_at": datetime.now(timezone.utc).isoformat()}


def container():
    return {"Image": "sha256:" + "b" * 64,
            "Env": ["EXISTING=preserve-exactly", "SECRET_FIXTURE=never-in-review-material"],
            "Cmd": ["python", "-m", "existing-service"], "Entrypoint": ["existing-entry"],
            "User": "1000:1000", "Healthcheck": {"Test": ["CMD", "existing-health"]},
            "HostConfig": {"Mounts": [{"Type": "bind", "Source": "/existing/source",
                "Target": "/existing/data", "ReadOnly": True}],
                "RestartPolicy": {"Name": "unless-stopped"}, "ReadonlyRootfs": True,
                "CapDrop": ["ALL"], "PortBindings": {"8000/tcp": []},
                "NetworkMode": "existing-private-network"}}


def test_native_runtime_projection_preserves_unrelated_material_and_rolls_back():
    before = container()
    saved = deepcopy(before)
    after = package.container_projection(before, role="jason-runtime",
                                         candidate_image="sha256:" + "d" * 64)
    assert before == saved
    assert after["Image"] == "sha256:" + "d" * 64
    assert set(before["Env"]) <= set(after["Env"])
    assert {k: v for k, v in after.items() if k not in ("Image", "Env", "HostConfig")} == {
        k: v for k, v in before.items() if k not in ("Image", "Env", "HostConfig")}
    assert after["HostConfig"]["Mounts"] == before["HostConfig"]["Mounts"] + package.MOUNTS
    assert {k: v for k, v in after["HostConfig"].items() if k != "Mounts"} == {
        k: v for k, v in before["HostConfig"].items() if k != "Mounts"}
    assert package.rollback_container(after, before, after) == before


def test_grafana_keeps_existing_image_and_changes_only_forwarding():
    before = container()
    before["Env"].append("GF_DATAPROXY_SEND_USER_HEADER=false")
    after = package.container_projection(before, role="jason-grafana")
    assert after["Image"] == before["Image"]
    assert after["HostConfig"] == before["HostConfig"]
    assert after["Env"][:-1] == before["Env"][:-1]
    assert after["Env"][-1] == "GF_DATAPROXY_SEND_USER_HEADER=true"
    with pytest.raises(package.PackageDenied, match="GRAFANA_IMAGE"):
        package.container_projection(before, role="jason-grafana", candidate_image="sha256:" + "e" * 64)


@pytest.mark.parametrize("change", ("profile", "mount", "duplicate", "legacy-bind"))
def test_conflicts_deny_before_any_container_action(change):
    before = container()
    if change == "profile":
        before["Env"].append("JASON_SHAREPOINT_READER_PROFILE=foreign-profile")
    elif change == "mount":
        before["HostConfig"]["Mounts"].append({**package.MOUNTS[0], "Source": "/unreviewed"})
    elif change == "legacy-bind":
        before["HostConfig"]["Binds"] = ["/unreviewed:" + package.MOUNTS[0]["Target"] + ":ro"]
    else:
        before["Env"].append("EXISTING=duplicate")
    saved = deepcopy(before)
    with pytest.raises(package.PackageDenied):
        package.container_projection(before, role="jason-runtime", candidate_image="sha256:" + "d" * 64)
    assert before == saved


def test_unknown_service_and_changed_rollback_fail_closed():
    before = container()
    with pytest.raises(package.PackageDenied, match="CONTAINER_SCOPE"):
        package.container_projection(before, role="jason-pmv4-ticket-core")
    after = package.container_projection(before, role="jason-grafana")
    newer = deepcopy(after)
    newer["Env"].append("LATER_ACCEPTED_CHANGE=preserve")
    with pytest.raises(package.PackageDenied, match="CHANGED_SINCE_INSTALL"):
        package.rollback_container(newer, before, after)
    assert "LATER_ACCEPTED_CHANGE=preserve" in newer["Env"]


def test_policy_adds_only_own_entries_and_denies_stale_rollback():
    before = {"schema_version": "1.0", "allowed_running_containers": ["keep-container"],
              "allowed_system_units": ["keep.timer"], "unrelated": {"preserve": True}}
    change = package.policy_changes(before)
    assert change["after"]["unrelated"] == before["unrelated"]
    assert change["after"]["allowed_running_containers"] == ["keep-container", package.CONTAINER]
    assert change["after"]["allowed_system_units"] == ["keep.timer", package.SERVICE, package.TIMER]
    assert package.rollback_policy(change["after"], change) == before
    assert package.policy_changes(change["after"])["additions"] == {
        "allowed_running_containers": [], "allowed_system_units": []}
    newer = deepcopy(change["after"])
    newer["allowed_system_units"].append("later-accepted.timer")
    with pytest.raises(package.PackageDenied, match="POLICY_CHANGED"):
        package.rollback_policy(newer, change)
    assert newer["allowed_system_units"][-1] == "later-accepted.timer"


def test_plan_is_one_exact_site_and_contains_no_fabricated_authority():
    plan = package.installation_plan("a" * 40, baseline())
    site = plan["initial_site_request"]
    assert site["site_id"] == package.SITE and site["desired_enabled"] is True
    assert site["other_initial_sites_enabled"] == []
    assert site["independent_owner_approval_recorded"] is False
    assert site["production_applied"] is False
    assert plan["production_authority"] is False and plan["production_ready"] is False
    assert plan["daily_discovery"]["timer_enabled_last"] is True
    assert plan["installation_steps"][-1]["action"] == "accept_then_enable_timer"
    assert "native_runtime_projection_admission" in plan["required_live_evidence"]
    assert "SECRET_FIXTURE" not in json.dumps(plan)


def test_http_decision_and_separate_process_revocation_readback(tmp_path):
    # Real HTTP boundary and real SQLite; synthetic identity is never asserted
    # to Jason or mistaken for a live Owner approval.
    registry = SharePointSiteAccess(str(tmp_path / "sites.sqlite3"), tenant_id=package.TENANT)
    registry.discover([
        {"tenant_id": package.TENANT, "site_id": package.SITE, "name": "Accounting fixture", "web_url": package.SITE_URL},
        {"tenant_id": package.TENANT, "site_id": "other-fixture", "name": "Other fixture", "web_url": "https://absolnet.sharepoint.com/sites/other-fixture"},
    ])
    class SyntheticAuthority:
        def can_change_site_access(self, **kw):
            return kw["authenticated_principal"] == "owner-fixture"
    service = GovernedSiteAccessAdministration(registry, SyntheticAuthority())
    token = "synthetic-test-service-token-32-characters-only"
    handler = make_handler(administration=service, service_token=token,
                           allowed_grafana_owners=frozenset({"owner-fixture"}),
                           approval_verifier=lambda actor, site, enabled: actor == "owner-fixture")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def post(enabled, revision, actor):
        req = Request(f"http://127.0.0.1:{server.server_port}/sharepoint-control/site-access",
                      data=json.dumps({"site_id": package.SITE, "enabled": enabled,
                          "expected_revision": revision, "reason": "synthetic-exact-test"}).encode(),
                      headers={"Authorization": "Bearer " + token,
                               "X-Grafana-User": actor, "Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=5) as response:
            return json.load(response)
    try:
        with pytest.raises(HTTPError) as denied:
            post(True, 1, "unapproved-fixture")
        assert denied.value.code == 403
        enabled = post(True, 1, "owner-fixture")
        assert enabled["site"]["enabled"] == 1
        with pytest.raises(HTTPError) as stale:
            post(False, 1, "owner-fixture")
        assert stale.value.code == 409
        post(False, 2, "owner-fixture")
        code = ("from connectors.microsoft_graph.site_access_registry import SharePointSiteAccess;"
                "r=SharePointSiteAccess(" + repr(registry.path) + ",tenant_id=" + repr(package.TENANT) + ");"
                "assert all(s['enabled']==0 for s in r.sites());"
                "assert next(s for s in r.sites() if s['site_id']==" + repr(package.SITE) + ")['revision']==3")
        subprocess.run([__import__('sys').executable, "-c", code], check=True, timeout=10)
        with pytest.raises(PermissionError):
            registry.require_site_access(tenant_id=package.TENANT, site_id=package.SITE)
        with pytest.raises(PermissionError):
            registry.require_site_access(tenant_id="foreign-tenant", site_id=package.SITE)
        # Rediscovery/rollback must retain the newer explicit revoke decision.
        registry.discover([{ "tenant_id": package.TENANT, "site_id": package.SITE,
            "name": "Accounting fixture", "web_url": package.SITE_URL }])
        assert next(s for s in registry.sites() if s["site_id"] == package.SITE)["revision"] == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def source_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for path in package.FIXED_FILES:
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("source fixture\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    return repo, sha


def test_package_is_reproducible_and_detects_payload_tampering(source_repo, tmp_path):
    repo, sha = source_repo
    a, b = tmp_path / "a.zip", tmp_path / "b.zip"
    observed = baseline()
    result = package.prepare(repo, sha, observed, a)
    package.prepare(repo, sha, observed, b)
    assert a.read_bytes() == b.read_bytes()
    assert result["site_approval_applied"] is False
    with zipfile.ZipFile(a) as src:
        contents = {name: src.read(name) for name in src.namelist()}
    contents["source/" + package.FIXED_FILES[0]] += b"tampered"
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        for name, blob in contents.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o100444 << 16
            archive.writestr(info, blob)
    with pytest.raises(package.PackageDenied, match="PAYLOAD_DRIFT"):
        package.verify(repo, sha, bad)


def test_rehashed_plan_cannot_expand_site_scope(source_repo, tmp_path):
    repo, sha = source_repo
    path = tmp_path / "original.zip"
    package.prepare(repo, sha, baseline(), path)
    with zipfile.ZipFile(path) as src:
        files = {name: src.read(name) for name in src.namelist()}
    plan = json.loads(files["plan.json"])
    plan["initial_site_request"]["other_initial_sites_enabled"] = ["unapproved-site"]
    files["plan.json"] = package.canonical(plan)
    manifest = json.loads(files["manifest.json"])
    manifest["files_sha256"]["plan.json"] = package.digest(files["plan.json"])
    files["manifest.json"] = package.canonical(manifest)
    bad = tmp_path / "expanded.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        for name, blob in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o100444 << 16
            archive.writestr(info, blob)
    with pytest.raises(package.PackageDenied, match="PLAN_DRIFT"):
        package.verify(repo, sha, bad)


def test_dirty_source_replacement_and_protected_output_are_denied(source_repo, tmp_path):
    repo, sha = source_repo
    existing = tmp_path / "keep.zip"
    existing.write_bytes(b"preserve")
    with pytest.raises(package.PackageDenied, match="OUTPUT_PATH_OR_REPLACEMENT"):
        package.prepare(repo, sha, baseline(), existing)
    assert existing.read_bytes() == b"preserve"
    with pytest.raises(package.PackageDenied, match="PROTECTED_OUTPUT"):
        package.prepare(repo, sha, baseline(), Path("/etc/jason-sharepoint-test.zip"))
    (repo / "untracked").write_text("dirty")
    with pytest.raises(package.PackageDenied, match="SOURCE_DIRTY_OR_MISMATCH"):
        package.prepare(repo, sha, baseline(), tmp_path / "dirty.zip")


def test_archives_reject_duplicate_or_extra_entries(source_repo, tmp_path):
    repo, sha = source_repo
    path = tmp_path / "original.zip"
    package.prepare(repo, sha, baseline(), path)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("../../unreviewed", b"never extract")
    with pytest.raises(package.PackageDenied, match="ARCHIVE_FILE_SET"):
        package.verify(repo, sha, path)


def test_archive_symlink_metadata_is_denied_even_with_original_payload(source_repo, tmp_path):
    repo, sha = source_repo
    path = tmp_path / "original.zip"
    package.prepare(repo, sha, baseline(), path)
    with zipfile.ZipFile(path) as src:
        files = {name: src.read(name) for name in src.namelist()}
    bad = tmp_path / "symlink.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        for name, blob in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o120777 if name == "plan.json" else 0o100444) << 16
            archive.writestr(info, blob)
    with pytest.raises(package.PackageDenied, match="ARCHIVE_MEMBER_TYPE"):
        package.verify(repo, sha, bad)


def test_shared_boundary_store_is_pinned_in_sidecar_and_package():
    # The read-only sidecar must not inherit a pre-repair SQLite module
    # from the pinned Runtime base. Every copied shared source needs
    # exact package custody as well.
    root = Path(__file__).resolve().parents[2]
    module = "implementation/kernel/client_boundaries/sqlite.py"
    assert module in package.FIXED_FILES
    assert "implementation/kernel/tests/test_client_boundaries_sqlite.py" in package.FIXED_FILES
    recipe = (root / "infrastructure/sharepoint-site-control/Dockerfile").read_text()
    assert f"COPY --chown=0:1000 {module} /app/{module}" in recipe
