"""Root module identity matters: generic root controller must not be copied."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import pmv4_e_root_import_binding as binding
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_root_trust_stage as trust


def test_package_order_and_original_generic_root_module_from_disposable_bundle(
        tmp_path):
    original = tmp_path / "original"
    staged = tmp_path / "stage"
    for relative in binding.NATIVE_FILES:
        target = original / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((packet.ROOT / relative).read_bytes())
    for path in ("tools", "implementation", "implementation/kernel"):
        (original / path).mkdir(exist_ok=True, parents=True)
    for name in binding.NATIVE_FILES:
        (original / name).chmod(0o444)
    for path in ("tools", "implementation", "implementation/kernel"):
        (original / path).chmod(0o555)
    original.chmod(0o555)
    staged_root = trust.RootTrustStager(
        source=packet.ROOT, target=staged, production=False,
        native_signed_started=lambda:True,
        native_host_locked=lambda:True,
        native_freeze_locked=lambda:True,
        native_marker_absent=lambda:True,
        native_replacements_inert=lambda:True,
    )
    hashes = {
        path: sha256((packet.ROOT / path).read_bytes()).hexdigest()
        for path in packet.REVIEWED_PATHS
    }
    staged_root.stage(source_sha="b"*40,exact_hashes=hashes)
    snippet = (
        "import json,sys\n"
        "root,stage=sys.argv[1:3]\n"
        "spec=json.loads(sys.argv[3])\n"
        "sys.path.insert(0,stage)\n"
        "from tools import pmv4_e_root_import_binding as binding\n"
        "sys.modules.pop('tools.pmv4_e_root_import_binding')\n"
        "sys.modules.pop('tools')\n"
        "x=binding.prepare(native_root=__import__('pathlib').Path(root),"
        "stage_root=__import__('pathlib').Path(stage),"
        "approved_hashes=spec,production=False)\n"
        "from tools import independent_component_release as native\n"
        "from tools import pmv4_e_signed_native_ledger as stage_e\n"
        "from implementation.kernel import signed_owner_release as owner\n"
        "from pathlib import Path\n"
        "assert Path(native.__file__).resolve()==Path(root)/"
        "'tools/independent_component_release.py'\n"
        "assert Path(stage_e.__file__).resolve()==Path(stage)/"
        "'tools/pmv4_e_signed_native_ledger.py'\n"
        "assert Path(owner.__file__).resolve()==Path(root)/"
        "'implementation/kernel/signed_owner_release.py'\n"
        "assert issubclass(stage_e.StageESignedNativeLedger,"
        "native.ComponentReleaseController)\n"
        "assert not x['release_authorized']\n"
    )
    cmd = [sys.executable, "-I", "-B", "-c", snippet, str(original),
           str(staged), json.dumps(hashes)]
    result = subprocess.run(
        cmd, cwd=tmp_path, capture_output=True, text=True,
        check=False, timeout=30)
    assert result.returncode == 0, result.stderr
    assert not any(p.name=="__pycache__" for p in staged.rglob("*"))
    staged_root.recover_inert_stage(hashes)


def test_invalid_original_root_file_is_denied_before_module_binding(tmp_path):
    original = tmp_path/"original"
    stage = tmp_path/"stage"
    for root in (original, stage):
        for name in ("tools", "implementation", "implementation/kernel"):
            (root/name).mkdir(parents=True,exist_ok=True)
    hashes={}
    for name in binding.NATIVE_FILES:
        p=original/name
        p.write_bytes((packet.ROOT/name).read_bytes())
        hashes[name]=sha256(p.read_bytes()).hexdigest()
    for name in binding.STAGE_FILES:
        p=stage/name
        p.write_bytes((packet.ROOT/name).read_bytes())
        hashes[name]=sha256(p.read_bytes()).hexdigest()
    altered=original/binding.NATIVE_FILES[0]
    altered.write_bytes(b"untrusted original")
    for name in binding.NATIVE_FILES:
        (original/name).chmod(0o444)
    for name in binding.STAGE_FILES:
        (stage/name).chmod(0o444)
    for base in (original, stage):
        for part in ("tools", "implementation", "implementation/kernel"):
            (base/part).chmod(0o555)
        base.chmod(0o555)
    with pytest.raises(binding.StageERootImportDenied,
                       match="NATIVE_FILE_BYTES_CHANGED"):
        binding.prepare(
            native_root=original,stage_root=stage,
            approved_hashes=hashes,production=False)


def test_production_import_from_ambient_checkout_denied(tmp_path):
    with pytest.raises(binding.StageERootImportDenied,
                       match="CANONICAL_ROOT_INSTALLED_REQUIRED"):
        binding.prepare(
            native_root=tmp_path,stage_root=tmp_path,
            approved_hashes={},production=True)
