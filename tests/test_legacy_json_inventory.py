"""Source-only inventory assurance for the legacy-to-JSON migration."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("legacy_json_migration_inventory", ROOT / "tools/legacy_json_migration_inventory.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_inventory_is_complete_and_source_hashes_reproducible():
    result = module.build(ROOT)
    assert result["population_count"] == 19
    assert result["markdown"] == 18
    assert result["python"] == 1
    assert len({r["id"] for r in result["entries"]}) == result["population_count"]
    assert all(len(r["source_git_blob_sha"]) == 40 for r in result["entries"])
    assert all(len(r["source_sha256"]) == 64 for r in result["entries"])
    assert all(r["parity_verified"] is False for r in result["entries"])
    assert all(r["isolated_shadow_verified"] is False for r in result["entries"])


def test_python_workflow_has_real_functions_not_just_documentation():
    python_sources = [r for r in module.build(ROOT)["entries"] if r["source_format"] == "python"]
    assert len(python_sources) == 1
    assert python_sources[0]["python_functions"]
    assert python_sources[0]["migration_status"] == "requires_semantic_mapping_and_independent_acceptance"


def test_documented_backupiq_registry_version_mismatch_is_not_silently_resolved():
    entries = {r["id"]: r for r in module.build(ROOT)["entries"]}
    backupiq = entries["backupiq_endpoint_backup"]
    assert backupiq["version"] == "1.2.0"
    assert backupiq["source_declared_version"] == "1.3.0"
    assert backupiq["registry_source_version_conflict"] is True
    assert sum(x["registry_source_version_conflict"] for x in entries.values()) == 1
