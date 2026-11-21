#!/usr/bin/env python3
"""Build self-contained, versioned AOT Datto RMM PowerShell diagnostics."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).parent
COMMON = (ROOT / "source" / "common.ps1").read_text()
COMPONENTS = {
    "windows-snapshot": "AOT - Windows Diagnostic Snapshot [WIN]",
    "disk-space-analysis": "AOT - Disk Space Analysis [WIN]",
    "network-dns": "AOT - Network and DNS Diagnostics [WIN]",
}
manifest = {"schema_version": "1.0", "execution": "Windows PowerShell 5.1, SYSTEM, noninteractive",
            "read_only": True, "default_enrollment": "not_enabled", "components": []}
for key, name in COMPONENTS.items():
    source = (ROOT / "source" / (key + ".ps1")).read_text()
    output = "# " + name + "\n# Standalone DRMM script; generated - do not edit manually.\n" + COMMON + "\n" + source
    p = ROOT / "components" / (key + ".ps1")
    p.write_text(output, encoding="utf-8", newline="\n")
    manifest["components"].append({
        "name": name, "artifact": "components/" + key + ".ps1",
        "sha256": hashlib.sha256(output.encode()).hexdigest(),
        "approximate_max_runtime_seconds": {"windows-snapshot": 120, "disk-space-analysis": 150, "network-dns": 120}[key],
        "datto_component_uid": None,
        "observed_provider_execution": False,
    })
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
for item in manifest["components"]:
    print(item["name"], item["sha256"])
