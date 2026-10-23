#!/usr/bin/env python3
"""Root-owned worker for bounded Jason host release reconciliation."""

from __future__ import annotations

import importlib.util
import hashlib
import grp
import json
import os
import pwd
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SPOOL = Path("/var/lib/jason/openclaw/release-manager/host-reconcile")
REQUESTS = SPOOL / "requests"
RESULTS = SPOOL / "results"
CANDIDATE_SCRIPTS = SPOOL / "candidate-scripts"
CURRENT = Path("/opt/jason/current")
REPO = Path("/home/al/.local/lib/jason/engineering-source-repo")
SHA = re.compile(r"^[0-9a-f]{40}$")
ROOT_RECOVERY_POLICY = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
SOURCE_DRIFT_POLICY = "config/production-desired-state.json"
POLICY_UNIT_LISTS = (
    "required_system_units", "allowed_system_units",
    "required_user_units", "allowed_user_units",
)

REQUEST_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
# Process one request per systemd activation; DirectoryNotEmpty retriggers for
# remaining requests. Multiple 360s scripts must never overrun one unit start.
MAX_REQUESTS_PER_RUN = 1
HOST_RECONCILE_TIMEOUT_SECONDS = 360
# Pinned historical rollback-only check; never skip the mandatory health start.
LEGACY_LKG_SHA = "aca94fdc0bfa551162f6ea99d7ddded311786414"
LEGACY_HOST_SCRIPT_SHA256 = "d8bf41dfe824b8eb01ae192386907a6657f09c245aa246306597a1162c7d1707"
LEGACY_HEALTH_FROM = 'timeout --signal=TERM --kill-after=5s 240s systemctl start "$unit"'
LEGACY_HEALTH_TO = 'timeout --signal=TERM --kill-after=5s 300s systemctl start "$unit"'
HOST_RECONCILE_LEGACY_ROLLBACK_TIMEOUT_SECONDS = 410


class HostReconcileError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_request(path: Path) -> dict[str, str]:
    expected_uid = pwd.getpwnam("al").pw_uid
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            raise HostReconcileError("request is not a regular file")
        if meta.st_uid != expected_uid:
            raise HostReconcileError("request owner is not the Jason host operator")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            payload = json.load(handle)
    finally:
        os.close(fd)

    request_id = str(payload.get("request_id") or "")
    source_revision = str(payload.get("source_revision") or "").casefold()
    if request_id != path.stem or not REQUEST_ID.fullmatch(request_id):
        raise HostReconcileError("request id is invalid")
    if not SHA.fullmatch(source_revision):
        raise HostReconcileError("source revision must be an exact SHA")
    return {"request_id": request_id, "source_revision": source_revision}


def _mcp_revision() -> str:
    value = subprocess.check_output(
        [
            "docker",
            "inspect",
            "jason-mcp-pilot",
            "--format",
            '{{index .Config.Labels "com.teamaot.jason.source_revision"}}',
        ],
        text=True,
    ).strip().casefold()
    if not SHA.fullmatch(value):
        raise HostReconcileError("live MCP revision is not an exact SHA")
    return value


def _git(*args: str) -> list[str]:
    return [
        "git",
        "-c",
        f"safe.directory={REPO}",
        "-C",
        str(REPO),
        *args,
    ]


def _verify_main(source_revision: str) -> None:
    # Network/source freshness belongs to the unprivileged Release Manager.
    # The root boundary deliberately performs only local immutable/ref checks
    # against the same managed Git source used by Release Manager, never a
    # mutable developer checkout.
    subprocess.run(
        _git("cat-file", "-e", f"{source_revision}^{{commit}}"),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    completed = subprocess.run(
        _git(
            "merge-base",
            "--is-ancestor",
            source_revision,
            "origin/main",
        ),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        raise HostReconcileError("requested host release is not on protected origin/main")




def _protected_root_drift_policy() -> dict[str, object]:
    """Read the root-only policy without following symlinks or weakening mode."""
    fd = os.open(ROOT_RECOVERY_POLICY, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o077:
            raise HostReconcileError("root recovery policy is not root-only mode-0600")
        if meta.st_size > 131072:
            raise HostReconcileError("root recovery policy is unexpectedly large")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            policy = json.load(handle)
    finally:
        os.close(fd)
    if not isinstance(policy, dict) or policy.get("schema_version") != "1.0":
        raise HostReconcileError("root recovery policy schema is invalid")
    return policy


def _declared_units(policy: dict[str, object], field: str) -> set[str]:
    units = policy.get(field)
    if (not isinstance(units, list)
            or any(not isinstance(item, str)
                   or not re.fullmatch(r"jason-[a-z0-9_.@-]{1,120}", item)
                   for item in units)
            or len(units) != len(set(units))):
        raise HostReconcileError("invalid protected drift unit declarations: " + field)
    return set(units)


def _verify_root_policy_covers_candidate(source_revision: str) -> None:
    """Refuse a host install that root's independent drift checker would reject.

    This is intentionally READ-ONLY. Adding a source unit to an independently
    root-approved policy is a material authority change: the host reconciler
    must never silently enlarge its own protected allowlist.
    """
    try:
        raw = subprocess.check_output(
            _git("show", f"{source_revision}:{SOURCE_DRIFT_POLICY}"),
            text=True, timeout=15,
        )
        candidate = json.loads(raw)
    except (subprocess.SubprocessError, ValueError) as exc:
        raise HostReconcileError("exact candidate drift policy could not be verified") from exc
    if not isinstance(candidate, dict) or candidate.get("schema_version") != "1.0":
        raise HostReconcileError("exact candidate drift policy schema is invalid")

    root_policy = _protected_root_drift_policy()
    missing: list[str] = []
    for field in POLICY_UNIT_LISTS:
        declared = _declared_units(candidate, field)
        protected = _declared_units(root_policy, field)
        # A required timer cannot be substituted by a merely allowed entry.
        for unit in sorted(declared - protected):
            missing.append(field + ":" + unit)

    if missing:
        raise HostReconcileError(
            "protected root drift policy missing exact candidate unit declarations: "
            + ", ".join(missing[:16])
            + (" (additional entries omitted)" if len(missing) > 16 else "")
            + "; requires separately authorized root-policy migration before host mutation"
        )


def _trusted_root_policy_helper():
    """Load only the installed root-owned helper, never mutable source."""
    helper = Path(__file__).with_name("protected_root_policy_migration.py")
    meta = helper.lstat()
    if (not stat.S_ISREG(meta.st_mode) or helper.is_symlink()
            or meta.st_uid != 0 or meta.st_mode & 0o022):
        raise HostReconcileError("root policy rollback helper is not securely installed")
    spec = importlib.util.spec_from_file_location("jason_root_policy_migration", helper)
    if spec is None or spec.loader is None:
        raise HostReconcileError("root policy rollback helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _restore_root_policy_for_target(source_revision: str) -> str:
    """Restore audited rollback or retain exact independently committed policy."""
    module = _trusted_root_policy_helper()
    if not module.ACTIVE.is_file():
        return "NO_MIGRATION_ACTIVE"
    receipt = module._json(module._root_only(module.ACTIVE))
    if receipt.get("candidate_sha") == source_revision:
        return "CANDIDATE_POLICY_ACTIVE"
    if receipt.get("rollback_sha") == source_revision:
        return module.prepare_rollback(source_revision)
    # The first migrated candidate can later become the independently
    # root-verified LKG. Its reviewed declarations must then remain in root
    # policy for subsequent exact-source releases. Never restore the old
    # overlay or treat an unrelated active receipt as a fresh approval.
    control = module._json(module._root_only(
        module.ROOT / "production-control-state.json"))
    lkg = ((control.get("last_known_good") or {}).get("manifest") or {})
    breaker = control.get("circuit_breaker") or {}
    if (receipt.get("phase") == "applied"
            and lkg.get("revision") == receipt.get("candidate_sha")
            and lkg.get("complete") is True
            and breaker.get("state") == "closed"):
        data = module._root_only(module.POLICY)
        if module.digest(data) != receipt.get("applied_sha256"):
            raise HostReconcileError("committed root policy differs from reviewed migration")
        return "PREVIOUS_MIGRATION_LKG_VERIFIED"
    raise HostReconcileError("active root policy migration does not belong to target SHA")


def _preflight_candidate_root_policy(source_revision: str) -> str:
    """Read-only reviewed-delta check, never automatic root allowlist writes."""
    try:
        _verify_root_policy_covers_candidate(source_revision)
        return "ALREADY_COVERED"
    except HostReconcileError as exc:
        # Only an exact missing declaration is eligible for the separately
        # authorized, fixed-scope migration path. Any malformed or untrusted
        # policy must remain a hard denial.
        if not str(exc).startswith(
            "protected root drift policy missing exact candidate unit declarations:"
        ):
            raise
    helper = _trusted_root_policy_helper()
    state = helper._json(helper._root_only(
        helper.ROOT / "production-control-state.json"
    ))
    rollback = (((state.get("last_known_good") or {}).get("manifest") or {})
                .get("revision"))
    if not isinstance(rollback, str) or not SHA.fullmatch(rollback):
        raise HostReconcileError("root LKG absent for reviewed migration preflight")
    return helper.preview_exact_migration(source_revision, rollback)


def _candidate_reconcile_script(source_revision: str) -> Path:
    """Materialize the exact candidate reconciliation script from protected Git evidence."""
    CANDIDATE_SCRIPTS.mkdir(parents=True, exist_ok=True)
    try:
        body = subprocess.check_output(
            _git("show", f"{source_revision}:tools/reconcile_production_host_services.sh"),
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise HostReconcileError(
            "candidate host reconciliation script is not materializable from protected source"
        ) from exc
    if source_revision == LEGACY_LKG_SHA:
        if (hashlib.sha256(body.encode("utf-8")).hexdigest() != LEGACY_HOST_SCRIPT_SHA256
                or body.count(LEGACY_HEALTH_FROM) != 1):
            raise HostReconcileError("pinned immutable legacy health script identity mismatch")
        # Only this exact checked source gets a timeout-only replacement.
        # Mandatory full health execution and all pass/fail logic are unchanged.
        body = body.replace(LEGACY_HEALTH_FROM, LEGACY_HEALTH_TO)
    developer_checkout = "/home/al/projects" + "/jason"
    if developer_checkout in body:
        raise HostReconcileError(
            "candidate host reconciliation script depends on developer checkout"
        )
    required = (
        'REPO_ROOT="/home/al/.local/lib/jason/engineering-source-repo"',
        'DOCUMENTATION_SOURCE_REPO="/home/al/.local/lib/jason/documentation-source-repo"',
        'DEVELOPER_CHECKOUT_DEPENDENCY=ABSENT',
        'HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION=',
    )
    missing = [item for item in required if item not in body]
    if missing:
        raise HostReconcileError(
            "candidate host reconciliation contract is incomplete: " + ",".join(missing)
        )
    target = CANDIDATE_SCRIPTS / f"reconcile-{source_revision}.sh"
    temp = target.with_suffix(".sh.tmp")
    temp.write_text(body, encoding="utf-8")
    os.chown(temp, 0, 0)
    os.chmod(temp, 0o700)
    os.replace(temp, target)
    return target




def _historical_post_success_documentation_failure(detail: str, source_revision: str) -> bool:
    """Accept only an old-script documentation-publication failure after critical alignment."""
    required = (
        "JASON_USER_WORKER_RECONCILIATION=PASS",
        "JASON_ROOT_HOST_RECONCILER_RECONCILIATION=PASS",
        "JASON_HOST_SERVICE_RECONCILIATION=PASS",
        "MANAGED_ENGINEERING_SOURCE=PASS",
        "MANAGED_DOCUMENTATION_SOURCE=PASS",
        f"HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION={source_revision}",
        "ERROR: production succeeded but documentation reconciliation publication failed",
    )
    return all(marker in detail for marker in required)

def _write_result(
    request_id: str,
    source_revision: str,
    *,
    success: bool,
    detail: str,
) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "request_id": request_id,
        "source_revision": source_revision,
        "success": bool(success),
        "detail": detail[-4000:],
        "completed_at": now(),
    }
    target = RESULTS / f"{request_id}.json"
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o640)
    gid = grp.getgrnam("jason").gr_gid
    os.chown(temp, 0, gid)
    os.replace(temp, target)


def _process(path: Path) -> None:
    request_id = path.stem
    source_revision = ""
    try:
        request = _read_request(path)
        request_id = request["request_id"]
        source_revision = request["source_revision"]
        _verify_main(source_revision)

        live_mcp = _mcp_revision()
        if live_mcp != source_revision:
            raise HostReconcileError(
                "live MCP revision does not match requested host release"
            )

        # The audited root overlay must be restored before installing a
        # previous immutable release that no longer declares its new units.
        root_policy_result = _restore_root_policy_for_target(source_revision)

        # Prevent the exact failure seen in #1974: host units were installed
        # but root's independent recovery overlay did not declare them.
        policy_preflight = _preflight_candidate_root_policy(source_revision)

        script = _candidate_reconcile_script(source_revision)
        if not script.is_file():
            raise HostReconcileError("candidate host reconciliation script is missing")

        release_dir = Path("/opt/jason/releases") / source_revision
        if release_dir.exists():
            meta = release_dir.lstat()
            if release_dir.is_symlink() or not stat.S_ISDIR(meta.st_mode):
                raise HostReconcileError(
                    "target immutable release path is not a real directory"
                )
            if meta.st_uid != 0:
                raise HostReconcileError(
                    "target immutable release directory is not root-owned"
                )
            os.chmod(release_dir, 0o755)

        script_env = os.environ.copy()
        script_env.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "safe.directory",
                "GIT_CONFIG_VALUE_0": str(REPO),
            }
        )
        previous_umask = os.umask(0o022)
        try:
            completed = subprocess.run(
                [str(script), source_revision],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=(HOST_RECONCILE_LEGACY_ROLLBACK_TIMEOUT_SECONDS
                         if source_revision == LEGACY_LKG_SHA
                         else HOST_RECONCILE_TIMEOUT_SECONDS),
                env=script_env,
            )
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            detail = str(output).strip()
            raise HostReconcileError(
                "candidate host reconciliation script exceeded "
                + str(HOST_RECONCILE_LEGACY_ROLLBACK_TIMEOUT_SECONDS
                      if source_revision == LEGACY_LKG_SHA
                      else HOST_RECONCILE_TIMEOUT_SECONDS) + "s"
                + (": " + detail[-3000:] if detail else "")
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = str(exc.stdout or "").strip()
            if _historical_post_success_documentation_failure(detail, source_revision):
                completed = subprocess.CompletedProcess(
                    args=[str(script), source_revision],
                    returncode=0,
                    stdout=(
                        detail
                        + "\nHISTORICAL_POST_SUCCESS_DOCUMENTATION_FAILURE=DEFERRED_TO_RELEASE_MANAGER"
                    ),
                )
            else:
                raise HostReconcileError(
                    "candidate host reconciliation script failed"
                    + (": " + detail[-3000:] if detail else "")
                ) from exc
        finally:
            os.umask(previous_umask)

        if policy_preflight != "ALREADY_COVERED":
            # The candidate install was required to apply its independent
            # root-reviewed migration. Never accept success if it did not.
            _verify_root_policy_covers_candidate(source_revision)

        release_meta = release_dir.stat()
        if release_meta.st_uid != 0 or (release_meta.st_mode & 0o055) != 0o055:
            raise HostReconcileError(
                "immutable release directory is not safely traversable"
            )
        resolved = CURRENT.resolve().name.casefold()
        if resolved != source_revision:
            raise HostReconcileError(
                "immutable host release did not resolve to requested revision"
            )
        if root_policy_result == "ROLLBACK_ALLOWED_STAGE":
            # Candidate-only units have now been removed by the immutable
            # baseline host script. Verify absence, then restore and archive
            # the exact pre-migration root policy; never mark host PASS sooner.
            module = _trusted_root_policy_helper()
            root_policy_result = module.complete_rollback(source_revision)
            if root_policy_result != "RESTORED":
                raise HostReconcileError("root rollback policy restoration not certified")
        _write_result(
            request_id,
            source_revision,
            success=True,
            detail=("ROOT_POLICY_MIGRATION=" + root_policy_result
                    + "\nROOT_POLICY_PREFLIGHT=" + policy_preflight
                    + "\n" + completed.stdout),
        )
    except Exception as exc:
        _write_result(
            request_id,
            source_revision,
            success=False,
            detail=f"{type(exc).__name__}: {exc}",
        )
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("release host reconciliation worker must run as root")
    REQUESTS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    paths = sorted(
        (
            path
            for path in REQUESTS.iterdir()
            if path.is_file() and path.suffix == ".json"
        ),
        key=lambda item: item.stat().st_mtime,
    )[:MAX_REQUESTS_PER_RUN]
    for path in paths:
        _process(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
