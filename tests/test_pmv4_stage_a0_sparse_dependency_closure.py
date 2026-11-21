"""Guard the exact root-loader -> sparse source transitive import closure.

Regression: 2026-11-14 Stage A0 root worker rejected an authenticated Owner
request because pmv4_host_install_contract.py was not in the 13-file bundle.
Do not weaken root file-ownership or Git content checks to work around this.
"""
from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path

import pytest

from tools import pmv4_stage_a0_sparse_source as sparse
from tools import pmv4_stage_a_packet as packet
from tools import pmv4_stage_a0_sparse_root_stage as rootstage

REPO = Path(__file__).resolve().parents[1]
MISSING_IN_PREVIOUS_STAGING = "tools/pmv4_host_install_contract.py"


def _native_root_loader_required_modules() -> tuple[str, ...]:
    source = REPO / "tools/release_host_reconcile_worker.py"
    parsed = ast.parse(source.read_text(encoding="utf-8"))
    func = next(
        n for n in parsed.body
        if isinstance(n, ast.FunctionDef) and n.name == "_trusted_native_stage_a0_module"
    )
    required = [
        n for n in ast.walk(func)
        if isinstance(n, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "required_modules"
                for target in n.targets)
    ]
    assert len(required) == 1
    return ast.literal_eval(required[0].value)


def test_native_root_dependency_closure_is_inside_sparse_allowed_source():
    # All deps are mandatory, not merely files imported by an isolated test.
    root_required = set(_native_root_loader_required_modules())
    sparse_required = set(sparse.required_paths())
    assert root_required <= sparse_required, sorted(root_required - sparse_required)
    assert MISSING_IN_PREVIOUS_STAGING in root_required
    assert MISSING_IN_PREVIOUS_STAGING in sparse_required


def test_packet_import_closure_is_included_without_entire_runtime():
    paths = sparse.required_paths()
    assert MISSING_IN_PREVIOUS_STAGING in packet.ROOT_STAGE_A_REQUIRED_SOURCES
    assert set(paths) == (
        set(packet.ROOT_STAGE_A_REQUIRED_SOURCES) | set(packet.BUNDLE_FILES)
    )
    assert len(paths) == 14
    assert len(paths) == len(set(paths))
    assert all(not name.startswith(("implementation/runtime_service/",
                                   "implementation/mcp_service/",
                                   "infrastructure/jason-runtime/",
                                   "infrastructure/jason-mcp/"))
               for name in paths)


def test_new_scope_and_archive_bind_exact_missing_blob():
    candidate, lkg, freeze = "a" * 40, "b" * 40, "c" * 64
    def blob(sha, path):
        assert sha == candidate
        return ("immutable git blob: " + path).encode()
    packet_manifest = sparse.source_manifest(
        candidate, blob, freeze_sha256=freeze, current_lkg=lkg,
    )
    archive = sparse.package_bytes(packet_manifest, blob)
    sparse.verify_package(archive, packet_manifest)
    missing = [row for row in packet_manifest["files"]
               if row["path"] == MISSING_IN_PREVIOUS_STAGING]
    assert len(missing) == 1
    assert missing[0]["sha256"] == sha256(blob(candidate, MISSING_IN_PREVIOUS_STAGING)).hexdigest()
    assert missing[0]["uid"] == missing[0]["gid"] == 0
    assert missing[0]["mode"] == "0444"
    assert packet_manifest["production_services_restart"] is False
    assert packet_manifest["production_core_changes"] is False
    assert packet_manifest["root_install_authorized"] is False
    assert rootstage.trusted_policy.__name__ == "trusted_policy"


def test_old_13_file_scope_does_not_silently_validate_as_new_scope():
    candidate, lkg, freeze = "a" * 40, "b" * 40, "c" * 64
    old_files = tuple(path for path in sparse.required_paths()
                      if path != MISSING_IN_PREVIOUS_STAGING)
    assert len(old_files) == 13
    manifest = sparse.source_manifest(
        candidate, lambda _sha,path: path.encode(),
        freeze_sha256=freeze, current_lkg=lkg,
    )
    truncated = dict(manifest)
    truncated["files"] = [row for row in manifest["files"]
                          if row["path"] != MISSING_IN_PREVIOUS_STAGING]
    with pytest.raises(sparse.SparseSourceDenied,match="MANIFEST_SCOPE_INVALID"):
        sparse.validate_manifest(truncated)


def test_one_source_file_was_missing_in_prior_prod_stage_without_changing_main():
    # An explicit long-term regression: revising the source list in a later
    # PR cannot silently authorize changes to the already approved 13-file
    # production source stage. A new immutable manifest + Owner review is required.
    assert "only-14-pinned-stage-a0-source-files" in (REPO / "tools/pmv4_stage_a0_sparse_root_stage.py").read_text()
    assert "only-13-pinned-stage-a0-source-files" not in (REPO / "tools/pmv4_stage_a0_sparse_root_stage.py").read_text()



def test_disposable_fully_isolated_native_loader_imports_all_exact_sparse_files(tmp_path):
    """Exercise Python's real import graph in a -I isolated temp-only tree.

    This does not invoke the native installer, import from production release
    sources, or change any protected root path. It catches missing transient
    dependencies beyond the root loader's manually maintained file tuple.
    """
    import shutil
    import subprocess
    import sys

    for relative in sparse.required_paths():
        source = REPO / relative
        assert source.is_file() and not source.is_symlink()
        dest = tmp_path / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)

    isolated_source = r"""
from pathlib import Path
import importlib.util
import sys
import types

base = Path(sys.argv[1])
for name, relative in (
    ("tools", "tools"),
    ("implementation", "implementation"),
    ("implementation.kernel", "implementation/kernel"),
):
    package = types.ModuleType(name)
    package.__path__ = [str(base / relative)]
    package.__package__ = name
    sys.modules[name] = package
candidate = base / "tools/pmv4_stage_a_native_install.py"
spec = importlib.util.spec_from_file_location(
    "pmv4_a0_native_import_only_lab", candidate,
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert callable(getattr(module, "execute_native_stage_a0_request", None))
print("PMV4_NATIVE_ISOLATED_IMPORT_CLOSURE=PASS")
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", isolated_source, str(tmp_path)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr[-2500:]
    assert "PMV4_NATIVE_ISOLATED_IMPORT_CLOSURE=PASS" in result.stdout
