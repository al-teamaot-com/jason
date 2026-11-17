#!/usr/bin/env python3
"""One immutable post-migration worker handoff packet; never deploys."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from tools import pmv4_c_canonical_resume_root as resume
from tools import pmv4_c_immutable_builder as existing
from tools import pmv4_shadow_ci as protected_ci

HERE = Path(__file__).resolve().parents[1]
ARCHIVE = Path("/srv/jason/archive/engineering-artifacts")


class CanonicalCandidateDenied(RuntimeError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise CanonicalCandidateDenied(reason)


def sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def canon(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def launcher(dest: Path, source_hashes: dict) -> str:
    stage = "/run/jason-pmv4-c-resume-" + dest.name[-40:][:12]
    support = " ".join("'" + name + "'" for name in source_hashes)
    return """#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
MODE="${1:-}"
[[ "${#}" == 1 && ( "${MODE}" == "--check-only" || "${MODE}" == "--execute" ) ]] || exit 2
[[ "$(id -u)" == 1000 ]] || exit 2
ART='""" + str(dest) + """'
STAGE='""" + stage + """'
SUPPORT=(""" + support + """)
cd "$ART"
printf '%s  %s\\n' '""" + sha((HERE/"tools/pmv4_c_canonical_resume_owner.py").read_bytes()) + """' "$ART/tools/pmv4_c_canonical_resume_owner.py" | sha256sum --check --status
printf '%s  %s\\n' '""" + sha((HERE/"tools/pmv4_c_canonical_resume_root.py").read_bytes()) + """' "$ART/tools/pmv4_c_canonical_resume_root.py" | sha256sum --check --status
python3 -B "$ART/tools/pmv4_c_canonical_resume_owner.py" --plan "$ART/root-release-plan.json" --check-only
echo PMV4_C_CANONICAL_EXACT_SOURCE_PREFLIGHT=PASS
echo 'OWNER_CONSENT=false; PRODUCTION_MUTATIONS=false'
if [[ "$MODE" == "--check-only" ]]; then exit 0; fi
[[ -t 0 && -t 1 ]] || { echo 'INTERACTIVE_OWNER_TTY_REQUIRED' >&2; exit 2; }
[[ ! -e "$STAGE" && ! -L "$STAGE" ]] || { echo 'ROOT_STAGE_COLLISION' >&2; exit 2; }
sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE"
sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE/src" "$STAGE/src/tools"
sudo /usr/bin/install -o root -g root -m 0400 "$ART/tools/pmv4_c_canonical_resume_root.py" "$STAGE/installer.py"
for item in "${SUPPORT[@]}"; do
  sudo /usr/bin/install -o root -g root -m 0400 "$ART/src/$item" "$STAGE/src/$item"
done
sudo /usr/bin/python3 -I -B "$STAGE/installer.py" --plan "$ART/root-release-plan.json" --preflight
echo PMV4_C_CANONICAL_PROTECTED_ROOT_PREFLIGHT=PASS
python3 -B "$ART/tools/pmv4_c_canonical_resume_owner.py" --plan "$ART/root-release-plan.json" --authorize
sudo -v
sudo /usr/bin/python3 -I -B "$STAGE/installer.py" --plan "$ART/root-release-plan.json" --execute
sudo /usr/bin/python3 -I -B "$STAGE/installer.py" --plan "$ART/root-release-plan.json" --postflight
echo PMV4_C_CANONICAL_WORKER_HANDOFF_AND_TWO_SCANS=VERIFIED
echo 'PMV4_LATER_STAGES_AUTHORIZED=false'
"""


def build() -> None:
    need(os.geteuid() == 1000, "BUILDER_UID1000_REQUIRED")
    git = ["/usr/bin/git", "-C", str(HERE)]
    candidate = subprocess.check_output(git + ["rev-parse", "HEAD"],
                                        text=True, timeout=10).strip()
    need(not subprocess.check_output(git + ["status", "--porcelain"],
                                     text=True, timeout=10).strip(), "SOURCE_DIRTY")
    main = subprocess.check_output(
        ["/usr/bin/gh", "api", "repos/al-teamaot-com/jason/branches/main",
         "--jq", ".commit.sha"], text=True, timeout=15).strip()
    need(candidate == main, "SOURCE_NOT_PROTECTED_MAIN")
    need(protected_ci.protected_main_ci_verified(candidate), "SOURCE_CI_NOT_GREEN")
    previous = resume.original()
    proof = resume.PRIOR / "root-oneowner-proof.json"
    need(proof.is_file(), "PREVIOUS_CUTOVER_APPROVAL_MISSING")
    base = (resume.PRIOR / "production-desired-state.base.json").read_bytes()
    target = (resume.PRIOR / "production-desired-state.stage-c.json").read_bytes()
    manifest = (resume.PRIOR / "service-manifest.json").read_bytes()
    need(sha(base) == previous["watchdog_base_sha256"] and
         sha(target) == previous["watchdog_candidate_sha256"] and
         sha(manifest) == previous["service_manifest_sha256"], "PRIOR_APPROVED_SOURCE_MISMATCH")
    runtime = existing._docker("jason-runtime")
    mcp = existing._docker("jason-mcp-pilot")
    runtime_env = existing._env(runtime)
    need(runtime.get("Image") == previous["runtime_image_digest"] and
         (runtime.get("State") or {}).get("Running") is True and
         (runtime.get("State") or {}).get("Health",{}).get("Status") == "healthy" and
         runtime_env.get("JASON_TICKET_WORKER_HOSTING") == "embedded" and
         runtime_env.get("JASON_AUTONOMY_WORKER_DB") ==
         "/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3" and
         mcp.get("Image") == previous["mcp_image_digest"] and
         (mcp.get("State") or {}).get("Running") is True,
         "PROTECTED_CONTAINERS_CHANGED")
    need(not existing._docker("jason-runtime").get("Name", "").endswith("-rollback"),
         "RUNTIME_NAME_INVALID")
    files = list(resume.SOURCE_FILES)
    hashes = {rel: sha((HERE / rel).read_bytes()) for rel in files}
    for original, identity in previous["db_identities"].items():
        old = Path(original)
        new = (resume.c.TICKET_TARGET if old.name in
               resume.c.sqlite_handoff.ALLOWED_TICKET else resume.c.SHARED_TARGET) / old.name
        meta = new.lstat()
        need(not old.exists() and not old.is_symlink() and
             not new.is_symlink() and stat.S_ISREG(meta.st_mode) and
             meta.st_dev == identity["device"] and meta.st_ino == identity["inode"] and
             meta.st_uid == meta.st_gid == 1000 and
             stat.S_IMODE(meta.st_mode) == 0o600,
             "CANONICAL_INODE_CHANGED:" + old.name)
    target_art = ARCHIVE / ("pmv4-c-resume-" + candidate)
    staging = ARCHIVE / (".pmv4-c-resume-" + candidate + ".building")
    need(not target_art.exists() and not staging.exists(), "ARTIFACT_ALREADY_EXISTS")
    plan = {
        "schema_version": "1.0",
        "action": resume.ACTION,
        "candidate_sha": candidate,
        "rollback_sha": previous["production_lkg_sha"],
        "production_lkg_sha": previous["production_lkg_sha"],
        "worker_image_digest": previous["worker_image_digest"],
        "runtime_image_digest": previous["runtime_image_digest"],
        "mcp_image_digest": previous["mcp_image_digest"],
        "runtime_container_id": runtime["Id"],
        "mcp_container_id": mcp["Id"],
        "previous_plan_sha256": sha((resume.PRIOR/"root-release-plan.json").read_bytes()),
        "previous_proof_sha256": sha(proof.read_bytes()),
        "freeze_sha256": sha(resume.c.FREEZE.read_bytes()),
        "hold_sha256": sha(resume.c.HOLD.read_bytes()),
        "watchdog_base_sha256": sha(base),
        "watchdog_candidate_sha256": sha(target),
        "service_manifest_sha256": sha(manifest),
        "root_sha256": sha((HERE/"tools/pmv4_c_canonical_resume_root.py").read_bytes()),
        "owner_sha256": sha((HERE/"tools/pmv4_c_canonical_resume_owner.py").read_bytes()),
        "source_hashes": hashes,
        "owner_consents": 1,
        "standing_authority": False,
        "later_stages_authorized": False,
        "no_database_relocation": True,
        "normal_ticket_processing_after_activation": True,
        "two_scan_acceptance": True,
        "service_restarts": ["jason-runtime"],
    }
    plan["scope_sha256"] = sha(canon(plan))
    staging.mkdir(mode=0o700)
    try:
        (staging/"tools").mkdir(mode=0o700)
        (staging/"src"/"tools").mkdir(parents=True, mode=0o700)
        for rel in files:
            dst = staging/"src"/rel
            shutil.copy2(HERE/rel, dst)
            dst.chmod(0o400)
        for fn in ("pmv4_c_canonical_resume_root.py", "pmv4_c_canonical_resume_owner.py"):
            src = HERE/"tools"/fn
            dst = staging/"tools"/fn
            shutil.copy2(src, dst); dst.chmod(0o400)
        for file, data in (
            ("root-release-plan.json", canon(plan)),
            ("service-manifest.json", manifest),
            ("watchdog-base.json", base),
            ("watchdog-candidate.json", target),
        ):
            p = staging/file
            p.write_bytes(data)
            p.chmod(0o400)
        local = staging/"tools"/"pmv4_c_canonical_resume_local.sh"
        local.write_text(launcher(target_art, hashes))
        local.chmod(0o500)
        staging.rename(target_art)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print("PMV4_C_CANONICAL_IMMUTABLE_PACKET=BUILT")
    print("SOURCE_SHA=" + candidate)
    print("SCOPE_SHA256=" + plan["scope_sha256"])
    print("NO_DATABASE_RELOCATION=true; MCP_RESTARTS=0; OWNER_APPROVAL=false")
    print("PRODUCTION_MUTATIONS=false")


if __name__ == "__main__":
    try:
        build()
    except BaseException as exc:
        print("PMV4_C_CANONICAL_BUILDER_DENIED=" + type(exc).__name__ + ":" +
              str(exc)[:160], file=sys.stderr)
        raise SystemExit(2)
