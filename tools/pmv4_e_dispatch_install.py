#!/usr/bin/env python3
"""Exact, locally authenticated installation of the inert Stage E dispatcher."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import tempfile
import time

ACTION = "INSTALL-EXACT-PMV4-E-DISPATCHER"
REPAIR_ACTION = "REPAIR-AND-COMPLETE-EXACT-PMV4-E"
REPAIR_FROM = "f792abc67cfa38c85a44f33a54cef576f862b9fe"
REPAIR_WORKER = "60b0166a328fe32d1e8246b9279bfd22fcc083e3734b4f81315ab953ed83727a"
REPAIR_POLICY = "caa84bec47d99ccf3b463ca082d035e108cd14993102b32e363d6677a40b5a34"
REPAIR_TREE = "2389c735751c0dd8bdcc9eae3d23d83b42df162d06623ad1f08a9a31db0b5739"
INSTALLED_ISOLATED_CANDIDATE = "605d783a5602d411381fe26011819f7afd3b4432"
INSTALLED_ISOLATED_TREE = "0b42701872f2389d3add392fdecfc045f6f03090a816d6ceef95971a0c028f29"
INSTALLED_ISOLATED_POLICY = "a6fe1462fe4703e0eb1599927735de14728bf51a41d4de6c322e59a627e587a2"
INSTALLED_ISOLATED_SCOPE = "d9813dc6b39654c6c8f417ab119adceb92cf899e036404d8710555dc6c1b5b3f"
BASE = Path("/usr/local/lib/jason/pmv4-e-bootstrap")
TRUST = BASE / "trusted"
WORKER = BASE.parent / "release_host_reconcile_worker.py"
POLICY = Path("/etc/jason/independent-component-release/pmv4-e-dispatch.json")
RECORDS = Path("/var/lib/jason-owner-release/pmv4-e-dispatch")
CATALOG_POLICY = Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
PREFLIGHT_TMP = Path("/run")
NATIVE_STATE = Path("/var/lib/jason/independent-component-release")
ARTIFACTS = Path("/srv/jason/archive/engineering-artifacts")
MANAGER = Path("/var/lib/jason/openclaw/release-manager")
REQUESTS = MANAGER / "host-reconcile/requests"
FREEZE = MANAGER / "production-deployment-freeze"
HOLD = MANAGER / "auto-promotion-incident-hold"
ROOT_CONTROL = MANAGER / "production-control-state.json"
ROOT_DRIFT = MANAGER / "production-drift.json"
LOCKS = (
    (MANAGER / "production-transaction.lock", 1000, 0o664),
    (Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock"), 0, 0o600),
)
OAUTH = Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_HASH = "24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
WORKER_BEFORE = "dca0c480265426c3c73f9cf8f7b8a9a4c5ab555640bd6953eb127cf3963a1896"
ROLLBACK = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE_HASH = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_HASH = "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
PREFIX = "usr/local/lib/jason/pmv4-e-bootstrap/trusted"
WORKER_SOURCE = "tools/release_host_reconcile_worker.py"
CONTROLS = {
    "bootstrap_sha256": "tools/pmv4_e_root_bootstrap_once.py",
    "scope_guard_sha256": "tools/pmv4_e_source_scope_guard.py",
    "ci_refresh_sha256": "tools/pmv4_e_ci_refresh.py",
}


class Denied(PermissionError):
    pass


def need(ok, reason):
    if not ok:
        raise Denied(reason)


def digest(raw):
    return sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def directory(path, mode=None):
    meta = path.lstat()
    need(path.resolve() == path and stat.S_ISDIR(meta.st_mode)
         and (meta.st_uid, meta.st_gid) == (0, 0)
         and not meta.st_mode & 0o022
         and (mode is None or stat.S_IMODE(meta.st_mode) == mode),
         "UNTRUSTED_ROOT_DIRECTORY:" + path.name)


def read(path, uid, mode, maximum=2_000_000):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        meta = os.fstat(stream.fileno())
        link = path.lstat()
        need(stat.S_ISREG(link.st_mode)
             and (meta.st_dev, meta.st_ino) == (link.st_dev, link.st_ino)
             and meta.st_uid == uid and (uid != 0 or meta.st_gid == 0)
             and meta.st_nlink == 1
             and stat.S_IMODE(meta.st_mode) == mode
             and 0 < meta.st_size <= maximum,
             "UNTRUSTED_FILE:" + path.name)
        raw = stream.read(maximum + 1)
        need(len(raw) == meta.st_size, "FILE_CHANGED:" + path.name)
        return raw


def tree(root):
    directory(root, 0o555)
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            directory(path, 0o555)
        else:
            files[path.relative_to(root).as_posix()] = digest(read(path, 0, 0o444))
    need(bool(files), "EMPTY_TRUST_DIRECTORY")
    return digest(canonical(files))


def decode_archive(raw, hashes):
    files = {}
    folders = set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for entry in archive:
            path = PurePosixPath(entry.name)
            need(path.as_posix() == entry.name.rstrip("/")
                 and ".." not in path.parts and (entry.uid, entry.gid) == (0, 0)
                 and (entry.name.rstrip("/") == PREFIX
                      or entry.name.startswith(PREFIX + "/")),
                 "ARCHIVE_ENTRY_UNTRUSTED")
            if entry.isdir():
                need(entry.mode == 0o555 and path not in folders, "ARCHIVE_DIRECTORY_INVALID")
                folders.add(path)
                continue
            rel = path.relative_to(PREFIX).as_posix()
            need(entry.isfile() and entry.mode == 0o444 and rel in hashes
                 and rel not in files and 0 < entry.size < 1_000_000,
                 "ARCHIVE_FILE_INVALID")
            data = archive.extractfile(entry).read()
            need(digest(data) == hashes[rel], "ARCHIVE_FILE_DIGEST_CHANGED")
            files[rel] = data
    expected = {PurePosixPath(PREFIX)}
    for name in files:
        expected.update(parent for parent in (PurePosixPath(PREFIX) / name).parents
                        if parent.as_posix().startswith(PREFIX))
    need(folders == expected and set(files) == set(hashes)
         and WORKER_SOURCE in files and set(CONTROLS.values()) <= files.keys(),
         "ARCHIVE_INVENTORY_CHANGED")
    return files


def plan(candidate, archive_hash, manifest_hash):
    bundle = ARTIFACTS / ("pmv4-e-root-admin-bundle-" + candidate)
    offer = ARTIFACTS / ("pmv4-e-source-only-" + candidate)
    handoff = json.loads(read(bundle / "handoff-manifest.json", 1000, 0o400))
    manifest = json.loads(read(offer / "manifest.json", 1000, 0o400))
    scope = json.loads(read(offer / "source-scope.json", 1000, 0o400))
    manifest_digest = digest(canonical(manifest))
    scope_digest = digest(canonical(scope))
    archive = read(bundle / ("stage-e-trusted-" + candidate + ".tar"), 1000, 0o400)
    hashes = scope["exact_replacement_files_sha256"]
    need(handoff["candidate_sha"] == manifest["candidate_sha"] == candidate
         and handoff["rollback_sha"] == manifest["rollback_sha"] == ROLLBACK
         and manifest_digest == handoff["manifest_sha256"] == manifest_hash
         and scope_digest == handoff["scope_sha256"] == manifest["source_scope_sha256"]
         and handoff["reviewed_hashes"] == hashes
         and handoff["freeze_sha256"] == manifest["freeze_sha256"] == FREEZE_HASH
         and digest(archive) == handoff["archive_sha256"] == archive_hash,
         "EXACT_ARTIFACT_BINDING_INVALID")
    policy = {
        "schema_version": "1.0", "action": "pmv4_e_cutover",
        "candidate_sha": candidate, "rollback_sha": ROLLBACK,
        "scope_sha256": scope_digest, "manifest_sha256": manifest_digest,
        "freeze_sha256": FREEZE_HASH,
        **{field: hashes[name] for field, name in CONTROLS.items()},
    }
    return decode_archive(archive, hashes), policy


def load_code(raw, name, path):
    namespace = {"__name__": name, "__file__": str(path)}
    exec(compile(raw, str(path), "exec"), namespace)
    return namespace


def current_ci(files, candidate):
    # Verify every archive file before loading any of its code as root.
    run_as_owner = [
        "/usr/sbin/runuser", "-u", "al", "--", "/usr/bin/env", "-i",
        "PATH=/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=/dev/null",
        "GIT_OPTIONAL_LOCKS=0", "GIT_NO_REPLACE_OBJECTS=1",
        "GIT_GRAFT_FILE=/dev/null", "GIT_CONFIG_COUNT=2",
        "GIT_CONFIG_KEY_0=core.fsmonitor", "GIT_CONFIG_VALUE_0=false",
        "GIT_CONFIG_KEY_1=core.hooksPath", "GIT_CONFIG_VALUE_1=/dev/null",
    ]
    upstream = subprocess.run(
        run_as_owner + ["/usr/bin/git", "ls-remote",
                        "https://github.com/al-teamaot-com/jason.git", "refs/heads/main"],
        text=True, capture_output=True, check=True, timeout=45,
    ).stdout.split()
    need(len(upstream) == 2 and upstream[1] == "refs/heads/main"
         and re.fullmatch("[0-9a-f]{40}", upstream[0]), "PROTECTED_MAIN_UNAVAILABLE")
    script = """
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

repo, rollback, candidate, protected_main = sys.argv[1:]
source, hashes = json.load(sys.stdin)
for name, expected in hashes.items():
    raw = subprocess.check_output(["/usr/bin/git", "-C", repo, "show",
                                   candidate + ":" + name], timeout=8)
    if sha256(raw).hexdigest() != expected:
        raise SystemExit("REVIEWED_ARCHIVE_FILE_DIFFERS_FROM_GIT")
namespace = {"__name__": "stage_e_scope"}
exec(compile(source, "<reviewed-scope>", "exec"), namespace)
namespace["verify_pinned_candidate_against_main"](Path(repo), rollback, candidate, protected_main)
"""
    subprocess.run(
        run_as_owner + ["/usr/bin/python3", "-I", "-B", "-c", script,
                        str(ARTIFACTS / "pmv4-e-owner-source-repo"), ROLLBACK,
                        candidate, upstream[0]],
        input=canonical([
            files["tools/manual_release_scope.py"].decode(),
            {name: digest(raw) for name, raw in files.items()},
        ]),
        capture_output=True, check=True, timeout=150,
    )
    module = load_code(files[CONTROLS["ci_refresh_sha256"]], "stage_e_ci", POLICY)
    pinned = module["load_pinned_attestor"](module["SOURCE"], production=True)
    module["paginate_required_checks"](pinned)
    evidence = pinned["verify_ci"](candidate)
    need(evidence["candidate_sha"] == candidate and evidence["required_ci_passed"] is True
         and evidence["protected_main_ancestor"] is True
         and evidence["protected_main"] == upstream[0], "CURRENT_PROTECTED_CI_UNVERIFIED")


def owner(scope):
    raw = read(OAUTH, 0, 0o555, 60_000)
    need(digest(raw) == OAUTH_HASH, "INSTALLED_ENTRA_VERIFIER_CHANGED")
    auth = load_code(raw, "stage_e_owner", OAUTH)
    endpoint = "https://login.microsoftonline.com/" + auth["TENANT"] + "/oauth2/v2.0/"
    client = auth["CLIENT_ID"]
    challenge = auth["_form"](endpoint + "devicecode", {"client_id": client, "scope": auth["SCOPE"]})
    need(all(isinstance(challenge.get(key), str) for key in ("user_code", "device_code", "verification_uri")),
         "ENTRA_DEVICE_CODE_UNAVAILABLE")
    action = scope["action"]
    print("EXACT_ACTION=" + action, flush=True)
    print("CANDIDATE_SHA=" + scope["policy"]["candidate_sha"], flush=True)
    print("ROLLBACK_SHA=" + scope["policy"]["rollback_sha"], flush=True)
    print("INSTALL_SCOPE_SHA256=" + digest(canonical(scope)), flush=True)
    targets = scope.get("installation_targets", (TRUST, WORKER, POLICY, RECORDS))
    print("INSTALL_TARGETS=" + ",".join(map(str, targets)), flush=True)
    print("CUTOVER=" + str(scope.get("queue_cutover", False)).lower(), flush=True)
    print("BROWSER_VERIFICATION_URL=" + challenge["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    interval = max(5, min(20, int(challenge.get("interval", 5))))
    deadline = time.monotonic() + min(600, int(challenge["expires_in"]))
    while time.monotonic() < deadline:
        time.sleep(interval)
        result = auth["_form"](endpoint + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client, "device_code": challenge["device_code"],
        })
        if isinstance(result.get("access_token"), str):
            actor = auth["jwt_owner"](result["access_token"])
            need(input("Type " + action + " to approve this exact scope and rollback: ").strip()
                 == action, "OWNER_CONFIRMATION_MISSING")
            return actor
        if result.get("error") == "slow_down":
            interval = min(20, interval + 5)
        else:
            need(result.get("error") == "authorization_pending", "ENTRA_AUTHENTICATION_DENIED")
    raise Denied("ENTRA_AUTHENTICATION_EXPIRED")


@contextmanager
def locks():
    with ExitStack() as scope:
        for path, uid, mode in LOCKS:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            scope.callback(os.close, fd)
            meta = os.fstat(fd)
            need(stat.S_ISREG(meta.st_mode) and meta.st_uid == uid
                 and stat.S_IMODE(meta.st_mode) == mode and meta.st_nlink == 1,
                 "RELEASE_LOCK_UNTRUSTED")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def protected():
    need(Path("/opt/jason/current").resolve(strict=True).name == ROLLBACK,
         "LIVE_ROLLBACK_CHANGED")
    need(digest(read(FREEZE, 1000, 0o600)) == FREEZE_HASH
         and digest(read(HOLD, 1000, 0o664)) == HOLD_HASH, "PRODUCTION_CONTROL_BYTES_CHANGED")
    control = json.loads(read(ROOT_CONTROL, 0, 0o600))
    drift = json.loads(read(ROOT_DRIFT, 0, 0o600))
    observed = datetime.fromisoformat(drift["observed_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    need(control.get("circuit_breaker", {}).get("state") == "closed"
         and drift.get("status") == "pass" and drift.get("problems") == []
         and 0 <= age <= 180, "PRODUCTION_BREAKER_OR_DRIFT_GATE")
    installed_unit = subprocess.run(
        ["/usr/bin/systemctl", "show", "jason-release-host-reconcile.service",
         "--property=ActiveState", "--value"], check=True, capture_output=True, text=True, timeout=10)
    need(installed_unit.stdout.strip() == "inactive" and not any(REQUESTS.iterdir()),
         "HOST_RECONCILE_WORK_IN_PROGRESS")
    need(not os.path.lexists("/usr/local/lib/jason/pmv4-e-bootstrap/native"), "STAGE_E_ALREADY_STAGED")


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, raw, mode):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(path.parent)


def stage_tree(root, files):
    root.mkdir(mode=0o700)
    for name, raw in files.items():
        target = root / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write(target, raw, 0o444)
    for folder in sorted((p for p in root.rglob("*") if p.is_dir()),
                         key=lambda p: len(p.parts), reverse=True):
        folder.chmod(0o555)
        sync_dir(folder)
    root.chmod(0o555)
    sync_dir(root)


def repair_baseline():
    old = read(POLICY, 0, 0o400)
    need(digest(old) == REPAIR_POLICY
         and json.loads(old).get("candidate_sha") == REPAIR_FROM
         and digest(read(WORKER, 0, 0o755)) == REPAIR_WORKER
         and tree(TRUST) == REPAIR_TREE, "REPAIR_BASELINE_CHANGED")
    accepted = json.loads(read(
        BASE / ("dispatch-install-" + REPAIR_FROM) / "accepted.json", 0, 0o400))
    need(accepted.get("status") == "installed"
         and accepted.get("scope", {}).get("policy") == json.loads(old),
         "PRIOR_DISPATCH_INSTALL_NOT_ACCEPTED")
    directory(RECORDS, 0o700)
    need(not any(RECORDS.iterdir()), "PRIOR_OWNER_REQUEST_ALREADY_DISPATCHED")
    return old


def install(files, policy, receipt, before_tree):
    candidate = policy["candidate_sha"]
    state = BASE / ("dispatch-install-" + candidate)
    directory(BASE)
    directory(WORKER.parent)
    directory(POLICY.parent)
    repair = receipt["scope"].get("queue_cutover", False)
    previous_policy = repair_baseline() if repair else None
    need(not os.path.lexists(state)
         and (repair or not any(os.path.lexists(p) for p in (POLICY, RECORDS))),
         "INSTALL_TARGET_EXISTS_OR_PARTIAL")
    old_worker = read(WORKER, 0, 0o755)
    expected_worker = REPAIR_WORKER if repair else WORKER_BEFORE
    need(digest(old_worker) == expected_worker and tree(TRUST) == before_tree,
         "INSTALL_BASELINE_CHANGED")
    receipt = {
        **receipt, "records_parent_preexisting": os.path.lexists(RECORDS.parent),
        "records_preexisting": os.path.lexists(RECORDS),
    }
    with tempfile.TemporaryDirectory(prefix=".dispatch-install-", dir=BASE) as staging:
        prepared = Path(staging)
        write(prepared / "worker-before.py", old_worker, 0o755)
        write(prepared / "approval.json", canonical(receipt), 0o400)
        if previous_policy is not None:
            write(prepared / "policy-before.json", previous_policy, 0o400)
        stage_tree(prepared / "trust-new", files)
        write(prepared / "worker-new.py", files[WORKER_SOURCE], 0o755)
        os.rename(prepared, state)
        sync_dir(BASE)
    policy_pending = POLICY.with_name("." + POLICY.name + "." + candidate)
    try:
        write(policy_pending, canonical(policy), 0o400)
        RECORDS.parent.mkdir(mode=0o700, exist_ok=True)
        directory(RECORDS.parent)
        if not receipt["records_preexisting"]:
            RECORDS.mkdir(mode=0o700)
            sync_dir(RECORDS.parent)
        protected()
        os.rename(TRUST, state / "trust-before")
        sync_dir(state)
        sync_dir(BASE)
        os.rename(state / "trust-new", TRUST)
        sync_dir(state)
        sync_dir(BASE)
        if repair:
            need(read(POLICY, 0, 0o400) == previous_policy, "REPAIR_POLICY_CHANGED")
            os.replace(policy_pending, POLICY)
        else:
            os.link(policy_pending, POLICY)
            policy_pending.unlink()
        sync_dir(POLICY.parent)
        os.replace(state / "worker-new.py", WORKER)
        sync_dir(state)
        sync_dir(WORKER.parent)
        need(digest(read(WORKER, 0, 0o755)) == digest(files[WORKER_SOURCE])
             and read(POLICY, 0, 0o400) == canonical(policy)
             and tree(TRUST) == digest(canonical({name: digest(raw) for name, raw in files.items()})),
             "INSTALL_READBACK_MISMATCH")
        protected()
        write(state / "accepted.json", canonical({"status": "installed", **receipt}), 0o400)
    except BaseException:
        rollback(files, policy, receipt["scope"])
        raise


def rollback(files, policy, expected_scope):
    candidate = policy["candidate_sha"]
    state = BASE / ("dispatch-install-" + candidate)
    directory(state, 0o700)
    receipt = json.loads(read(state / "approval.json", 0, 0o400))
    need(receipt["scope"] == expected_scope and receipt.get("owner_object_id")
         and not os.path.lexists(state / "rolled-back.json"),
         "ROLLBACK_NOT_AUTHORIZED_OR_ALREADY_COMPLETE")
    before = read(state / "worker-before.py", 0, 0o755)
    installed = read(WORKER, 0, 0o755)
    expected_tree = expected_scope["trust_before_sha256"]
    after_tree = digest(canonical({name: digest(raw) for name, raw in files.items()}))
    old_tree = state / "trust-before"
    have_backup = os.path.lexists(old_tree)
    have_trust = os.path.lexists(TRUST)
    repair = expected_scope.get("queue_cutover", False)
    previous_policy = read(state / "policy-before.json", 0, 0o400) if repair else None
    expected_worker = REPAIR_WORKER if repair else WORKER_BEFORE
    need(not repair or digest(previous_policy) == REPAIR_POLICY, "REPAIR_BEFORE_POLICY_CHANGED")
    need(digest(before) == expected_worker and installed in (before, files[WORKER_SOURCE])
         and (tree(old_tree) == expected_tree if have_backup else
              have_trust and tree(TRUST) == expected_tree)
         and (not have_backup or not have_trust or tree(TRUST) == after_tree),
         "ROLLBACK_BEFORE_IMAGE_CHANGED")
    pending = POLICY.with_name("." + POLICY.name + "." + candidate)
    # A power loss between link and unlink can leave two references to the same file.
    if os.path.lexists(pending) and os.path.lexists(POLICY):
        first, second = pending.lstat(), POLICY.lstat()
        need(stat.S_ISREG(first.st_mode) and first.st_ino == second.st_ino
             and first.st_dev == second.st_dev and first.st_nlink == second.st_nlink == 2,
             "ROLLBACK_POLICY_LINK_CHANGED")
        pending.unlink()
        sync_dir(POLICY.parent)
    for target in (POLICY, pending):
        if os.path.lexists(target):
            need(read(target, 0, 0o400) in (canonical(policy), previous_policy),
                 "ROLLBACK_POLICY_CHANGED")
    if os.path.lexists(RECORDS):
        directory(RECORDS, 0o700)
        need(not any(RECORDS.iterdir()), "STAGE_E_APPROVAL_ALREADY_DISPATCHED")
    if installed != before:
        restore = state / "worker-restore.py"
        if not os.path.lexists(restore):
            write(restore, before, 0o755)
        need(read(restore, 0, 0o755) == before, "ROLLBACK_WORKER_RESTORE_CHANGED")
        os.replace(restore, WORKER)
        sync_dir(WORKER.parent)
        sync_dir(state)
    if previous_policy is not None:
        restore_policy = state / "policy-restore.json"
        if not os.path.lexists(restore_policy):
            write(restore_policy, previous_policy, 0o400)
        need(read(restore_policy, 0, 0o400) == previous_policy, "POLICY_RESTORE_CHANGED")
        os.replace(restore_policy, POLICY)
        sync_dir(POLICY.parent)
    elif os.path.lexists(POLICY):
        POLICY.unlink()
        sync_dir(POLICY.parent)
    if os.path.lexists(pending):
        pending.unlink()
        sync_dir(pending.parent)
    if have_backup:
        if have_trust:
            os.rename(TRUST, state / "trust-failed")
        os.rename(old_tree, TRUST)
        sync_dir(BASE)
        sync_dir(state)
    if os.path.lexists(RECORDS) and not receipt["records_preexisting"]:
        RECORDS.rmdir()
        sync_dir(RECORDS.parent)
    if (not receipt["records_parent_preexisting"] and os.path.lexists(RECORDS.parent)
            and not any(RECORDS.parent.iterdir())):
        RECORDS.parent.rmdir()
        sync_dir(RECORDS.parent.parent)
    need(read(WORKER, 0, 0o755) == before and tree(TRUST) == expected_tree
         and (read(POLICY, 0, 0o400) == previous_policy if repair else
              not os.path.lexists(POLICY)), "ROLLBACK_READBACK_MISMATCH")
    write(state / "rolled-back.json", canonical({"status": "rolled_back", **receipt}), 0o400)




@contextmanager
def reviewed_preflight_source(files):
    """Read-only probe from exact CI/Git-verified bytes, before installation.

    The isolated caller verifies every archive byte via current_ci first.
    Root-private volatile staging permits testing a newly reviewed baseline
    without changing the installed bootstrap trust or any production policy.
    """
    if files is None:
        yield TRUST
        return
    with tempfile.TemporaryDirectory(prefix="jason-pmv4-e-preflight-", dir=PREFLIGHT_TMP) as name:
        base = Path(name)
        directory(base, 0o700)
        staged = base / "reviewed"
        stage_tree(staged, files)
        need(tree(staged) == digest(canonical({key: digest(raw) for key, raw in files.items()})),
             "PREFLIGHT_REVIEWED_SOURCE_CHANGED")
        yield staged


def cutover_preflight(files=None, candidate=None):
    """Read privileged acceptance before asking for the combined decision."""
    script = (
        "import json,sys; sys.path.insert(0,sys.argv[1]); "
        "from tools import pmv4_e_root_cutover_preflight as gate; "
        "print(json.dumps(gate.evaluate(gate.collect()),sort_keys=True))"
    )
    if candidate is not None:
        script = script.replace(
            "from tools import pmv4_e_root_cutover_preflight as gate; ",
            "from tools import pmv4_e_installation_preflight as install; "
            "install.collect(sys.argv[2]); "
            "from tools import pmv4_e_root_cutover_preflight as gate; ")
    with reviewed_preflight_source(files) as source:
        result = subprocess.run(
            ["/usr/bin/python3", "-I", "-B", "-c", script, str(source)]
            + ([candidate] if candidate is not None else []),
            capture_output=True, check=False, timeout=180,
        )
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip().splitlines()
        raise Denied("CUTOVER_PREFLIGHT:" + (detail[-1] if detail else "unavailable"))
    evidence = json.loads(result.stdout)
    need(evidence.get("status") == "read_only_root_preflight_source_conditions_passed"
         and evidence.get("production_mutations") is False,
         "CUTOVER_PREFLIGHT_UNVERIFIED")


def queue_cutover(policy, owner_oid):
    """The existing service signer publishes only the just-approved exact cutover."""
    publisher = ARTIFACTS / (
        "pmv4-e-owner-source-repo/implementation/mcp_service/src/"
        "jason_mcp/pmv4_stage_a0_owner_issuer.py")
    source = read(publisher, 1000, 0o444, 30_000)
    need(digest(source) ==
         "096b3ca7cb8510dff3b695a25f82fc96029ac8ad348e69a9beafa7b44ed7e7e4",
         "ORIGINAL_REQUEST_PUBLISHER_CHANGED")
    script = """
import json
from pathlib import Path
import sys
sys.path[:0] = [sys.argv[1], str(Path(sys.argv[1]) / "implementation")]
from tools import pmv4_e_exact_owner_offer as offer
policy, owner_oid, publisher_source = json.load(sys.stdin)
signer, _, private = offer.checked_identity()
plan = {
    "candidate": policy["candidate_sha"], "rollback": policy["rollback_sha"],
    "scope_sha256": policy["scope_sha256"],
    "manifest_sha256": policy["manifest_sha256"],
    "freeze_sha256": policy["freeze_sha256"],
}
owner = offer.signed_request(plan, signer=signer, private=private, owner_oid=owner_oid)
approval = owner["signed_owner_proof"]["payload"]["approval_id"]
request_id = "pmv4-e-" + policy["candidate_sha"][:16] + "-" + approval[10:]
publisher = {"__name__": "original_request_publisher"}
exec(compile(publisher_source, "<pinned-publisher>", "exec"), publisher)
target = publisher["REQUESTS"] / (request_id + ".json")
publisher["_trusted_requests"](target.parent, production=True)
publisher["_publish_exact_request"](target, {
    "request_id": request_id, "source_revision": policy["candidate_sha"],
    "action": "pmv4_e_cutover", "owner_request": owner,
})
print(json.dumps({"request_id": request_id, "candidate_sha": policy["candidate_sha"]}))
"""
    result = subprocess.run(
        ["/usr/sbin/runuser", "-u", "al", "--", "/usr/bin/python3", "-I", "-B",
         "-c", script, str(TRUST)],
        input=canonical([policy, owner_oid, source.decode()]), cwd="/",
        capture_output=True, check=True, timeout=45,
    )
    payload = json.loads(result.stdout)
    need(type(payload) is dict and payload.get("candidate_sha") == policy["candidate_sha"]
         and re.fullmatch("pmv4-e-" + policy["candidate_sha"][:16] +
                          "-[0-9a-f]{32}", payload.get("request_id", "")),
         "QUEUED_CUTOVER_READBACK_INVALID")
    return payload



def verified_previous_isolated_install(old_policy):
    """Historical installation evidence never supplies a new release approval."""
    prior = BASE / ("isolated-cutover-" + INSTALLED_ISOLATED_CANDIDATE)
    approval = json.loads(read(prior / "approval.json", 0, 0o400))
    need(digest(canonical(approval.get("scope"))) == INSTALLED_ISOLATED_SCOPE
         and approval["scope"].get("policy") == json.loads(old_policy)
         and approval.get("owner_object_id") == "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
         "PREVIOUS_ISOLATED_INSTALL_SCOPE_CHANGED")
    request = json.loads(read(prior / "owner-proof.json", 0, 0o400))
    proof = request["signed_owner_proof"]
    payload = proof["payload"]
    journal = json.loads(read(Path("/var/lib/jason/independent-component-release/stage-e-bootstrap") /
        ("owner-" + payload["approval_id"] + ".json"), 0, 0o600))
    need(journal.get("signed_owner_proof") == proof
         and journal.get("candidate_sha") == INSTALLED_ISOLATED_CANDIDATE
         and journal.get("no_unit_mutations") is True,
         "PREVIOUS_ISOLATED_SIGNED_JOURNAL_CHANGED")
    signer_path = Path("/usr/local/lib/jason/owner_signed_release.py")
    signer_source = read(signer_path, 0, 0o644)
    need(digest(signer_source) == "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3",
         "PREVIOUS_INSTALL_VERIFIER_CHANGED")
    signer = load_code(signer_source, "historical_install_verifier", signer_path)
    at = datetime.fromisoformat(journal["started_at"])
    need(at <= datetime.now(timezone.utc), "PREVIOUS_INSTALL_TIME_UNTRUSTED")
    policy = json.loads(old_policy)
    verified = signer["verify_exact_owner_release"](
        proof, public_key=signer["read_pinned_root_owner_public_key"](
            Path("/etc/jason-owner-release/verified-owner-public-key.json")),
        expected_release_id="release-" + INSTALLED_ISOLATED_CANDIDATE[:16],
        expected_candidate_sha=INSTALLED_ISOLATED_CANDIDATE,
        expected_rollback_sha=ROLLBACK, expected_scope_sha256=policy["scope_sha256"],
        expected_manifest_sha256=policy["manifest_sha256"],
        expected_freeze_sha256=policy["freeze_sha256"], at=at)
    need(verified["owner_oid"] == approval["owner_object_id"],
         "PREVIOUS_INSTALL_OWNER_CHANGED")
    receipts = Path("/var/lib/jason/independent-component-release/receipts")
    for item in receipts.iterdir():
        native = json.loads(read(item, 0, 0o600, 100000))
        need(native.get("candidate_sha") != INSTALLED_ISOLATED_CANDIDATE,
             "PREVIOUS_NATIVE_TRANSACTION_REQUIRES_LEDGER_RECOVERY")


def isolated_baseline():
    directory(BASE)
    before = tree(TRUST)
    need(before in {REPAIR_TREE, INSTALLED_ISOLATED_TREE}
         and digest(read(WORKER, 0, 0o755)) == WORKER_BEFORE,
         "ISOLATED_APPROVED_BASELINE_CHANGED")
    old_policy = read(POLICY, 0, 0o400)
    if before == INSTALLED_ISOLATED_TREE:
        need(digest(old_policy) == INSTALLED_ISOLATED_POLICY,
             "ISOLATED_PREVIOUS_DISPATCH_POLICY_CHANGED")
        verified_previous_isolated_install(old_policy)
    else:
        need(digest(old_policy) == REPAIR_POLICY, "ISOLATED_PREVIOUS_DISPATCH_POLICY_CHANGED")
        accepted = json.loads(read(
            BASE / ("dispatch-install-" + REPAIR_FROM) / "accepted.json", 0, 0o400))
        need(accepted.get("status") == "installed"
             and accepted.get("scope", {}).get("policy") == json.loads(old_policy),
             "ORIGINAL_DISPATCH_INSTALL_RECEIPT_CHANGED")
    catalog = read(CATALOG_POLICY, 0, 0o600, 8192)
    need(json.loads(catalog).get("root_worker_sha256") == WORKER_BEFORE,
         "CATALOG_SHARED_WORKER_PIN_CHANGED")
    return old_policy, digest(catalog)


def install_isolated_source(files, policy, scope, actor):
    """Install only Stage E source and dispatch policy under the existing locks."""
    previous_policy, catalog_digest = isolated_baseline()
    state = BASE / ("isolated-cutover-" + policy["candidate_sha"])
    need(not os.path.lexists(state), "ISOLATED_INSTALL_ALREADY_PRESENT")
    state.mkdir(mode=0o700)
    write(state / "policy-before.json", previous_policy, 0o400)
    write(state / "approval.json", canonical({
        "scope": scope, "owner_object_id": actor,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "catalog_policy_sha256": catalog_digest,
    }), 0o400)
    stage_tree(state / "trust-new", files)
    pending = POLICY.with_name("." + POLICY.name + ".isolated")
    moved = installed = policy_installed = False
    layout=[(BASE / "releases",0o755),*[(NATIVE_STATE/name,0o700)
        for name in ("stage-e-code-before","stage-e-physical-before","stage-e-step-audit")]]
    created=[]
    try:
        for index,(target,mode) in enumerate(layout):
            if not os.path.lexists(target):
                directory(target.parent)
                write(state / ("directory-intent-"+str(index)+".json"),canonical({
                    "path":str(target),"uid":0,"gid":0,"mode":oct(mode)}),0o400)
                target.mkdir(mode=mode)
                os.chmod(target,mode)
                created.append((target,mode))
            directory(target,mode)
        write(pending, canonical(policy), 0o400)
        need(read(POLICY, 0, 0o400) == previous_policy, "DISPATCH_POLICY_CHANGED")
        os.rename(TRUST, state / "trust-before")
        moved = True
        os.rename(state / "trust-new", TRUST)
        installed = True
        os.replace(pending, POLICY)
        policy_installed = True
        sync_dir(BASE)
        sync_dir(state)
        sync_dir(POLICY.parent)
        need(tree(TRUST) == digest(canonical({name: digest(raw) for name, raw in files.items()}))
             and read(POLICY, 0, 0o400) == canonical(policy)
             and digest(read(WORKER, 0, 0o755)) == WORKER_BEFORE,
             "ISOLATED_SOURCE_INSTALL_READBACK_FAILED")
        protected()
        return state
    except BaseException:
        if policy_installed:
            restore = state / "policy-restore.json"
            write(restore, previous_policy, 0o400)
            os.replace(restore, POLICY)
        if installed:
            os.rename(TRUST, state / "trust-failed")
        if moved:
            os.rename(state / "trust-before", TRUST)
        pending.unlink(missing_ok=True)
        for target,mode in reversed(created):
            directory(target,mode)
            need(not any(target.iterdir()), "INSTALL_DIRECTORY_HAS_FOREIGN_CONTENT")
            target.rmdir()
        sync_dir(BASE)
        sync_dir(POLICY.parent)
        raise


def signed_cutover_request(policy, actor):
    """Reuse the existing exact service signer after the one local Owner decision."""
    script = """
import json
from pathlib import Path
import sys
sys.path[:0] = [sys.argv[1], str(Path(sys.argv[1]) / "implementation")]
from tools import pmv4_e_exact_owner_offer as offer
policy, actor = json.load(sys.stdin)
signer, _, private = offer.checked_identity()
plan = {
    "candidate": policy["candidate_sha"], "rollback": policy["rollback_sha"],
    "scope_sha256": policy["scope_sha256"], "manifest_sha256": policy["manifest_sha256"],
    "freeze_sha256": policy["freeze_sha256"],
}
print(json.dumps(offer.signed_request(plan, signer=signer, private=private, owner_oid=actor)))
"""
    result = subprocess.run(
        ["/usr/sbin/runuser", "-u", "al", "--", "/usr/bin/python3", "-I", "-B",
         "-c", script, str(TRUST)], input=canonical([policy, actor]), cwd="/",
        capture_output=True, check=True, timeout=30,
    )
    request = json.loads(result.stdout)
    need(all(request.get(key) == policy[key] for key in (
        "candidate_sha", "rollback_sha", "scope_sha256", "manifest_sha256", "freeze_sha256")),
        "ISOLATED_SIGNER_SCOPE_CHANGED")
    return request


def replacement_unit_targets(files):
    targets = []
    prefix = "infrastructure/pmv4-e-scheduler/systemd/"
    for name in sorted(files):
        if not name.startswith(prefix):
            continue
        relative = PurePosixPath(name).relative_to(prefix)
        if relative.parts[0] == "user":
            root = "/home/al/.config/systemd/user/"
        else:
            need(relative.parts[0] == "system", "UNIT_SCOPE_INVALID")
            root = "/etc/systemd/system/"
        need(len(relative.parts) == 2, "UNIT_SCOPE_INVALID")
        targets.append(root + relative.name)
    need(len(targets) == 12, "SIX_UNIT_SCOPE_INCOMPLETE")
    return targets


def run_isolated_native(candidate, request, state):
    command = ["/usr/bin/python3", "-I", "-B",
               str(TRUST / CONTROLS["bootstrap_sha256"]),
               "--candidate-sha", candidate]
    try:
        result = subprocess.run(
            command + ["--stage-and-promote", "--owner-request-stdin"],
            input=canonical(request), cwd="/", capture_output=True, timeout=1050, check=False,
        )
    except subprocess.TimeoutExpired:
        result = subprocess.CompletedProcess(command, 124, b"", b"")
    if result.returncode:
        write(state / "native-failure.stderr", getattr(result, "stderr", b"") or b"native bootstrap returned no stderr", 0o400)
        write(state / "native-failure.stdout", result.stdout or b"native bootstrap returned no stdout", 0o400)
        # The original recovery rejects cleanup after native STARTED and
        # preserves its independently signed rollback/recovery receipts.
        recovery = subprocess.run(
            command + ["--recover-inert", "--owner-request-stdin"],
            input=canonical(request), cwd="/", capture_output=True, timeout=180, check=False,
        )
        write(state / "failed-native-attempt.json", canonical({
            "candidate_sha": candidate, "native_returncode": result.returncode,
            "signed_inert_recovery_returncode": recovery.returncode,
            "owner_approval_reusable": False,
        }), 0o400)
        details = (getattr(result, "stderr", b"") or b"").decode(errors="replace").strip().splitlines()
        reason = details[-1] if details and re.fullmatch(r"[A-Za-z0-9_:/.-]{1,250}", details[-1]) else "SEE_ROOT_RECEIPTS"
        raise Denied("ISOLATED_NATIVE_CUTOVER_FAILED:" + reason)
    payload = json.loads(result.stdout)
    write(state / "native-result.json", canonical(payload), 0o400)
    need(payload.get("candidate_sha") == candidate
         and payload.get("status") == "native_stage_e_six_unit_accepted",
         "ISOLATED_CUTOVER_NOT_ACCEPTED_SEE_NATIVE_RESULT")
    return payload


def complete_isolated(args, files, policy):
    need(args.before_tree_sha256 == INSTALLED_ISOLATED_TREE and not args.rollback
         and not args.repair_and_cutover, "ISOLATED_MODE_ARGUMENTS_INVALID")
    scope = {
        "action": "COMPLETE-EXACT-ISOLATED-PMV4-E", "policy": policy,
        "queue_cutover": True,
        "archive_sha256": args.archive_sha256, "trust_before_sha256": args.before_tree_sha256,
        "protected_shared_worker_sha256": WORKER_BEFORE,
        "installer_sha256": digest(Path(__file__).read_bytes()),
        "installation_targets": [str(TRUST), str(POLICY),
            "/usr/local/lib/jason/pmv4-e-bootstrap/native",
            str(BASE / "releases"), str(BASE / "releases" / args.candidate_sha),
            "/var/lib/jason/independent-component-release",
            *["/var/lib/jason/independent-component-release/"+name for name in (
                "stage-e-code-before","stage-e-physical-before","stage-e-step-audit")],
            "/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json",
            "/etc/jason/release-readback-recovery/production-desired-state.json",
            "/home/al/.local/lib/jason/jason_self_heal_watchdog.py",
            "/home/al/.local/lib/jason/release_manager_host_runner.py",
            *replacement_unit_targets(files)],
    }
    with locks():
        protected()
        _, catalog_hash = isolated_baseline()
        scope["protected_catalog_policy_sha256"] = catalog_hash
        need(tree(TRUST) == args.before_tree_sha256, "ISOLATED_EXACT_BEFORE_TREE_CHANGED")
        current_ci(files, args.candidate_sha)
        cutover_preflight(files, args.candidate_sha)
    if not args.apply:
        print(json.dumps({"status": "isolated_read_only_preflight_passed", "scope": scope}))
        return
    actor = owner(scope)
    with locks():
        protected()
        current_ci(files, args.candidate_sha)
        state = install_isolated_source(files, policy, scope, actor)
    refresh = subprocess.run(
        ["/usr/bin/python3", "-I", "-B", str(TRUST / CONTROLS["ci_refresh_sha256"]),
         "--candidate-sha", args.candidate_sha],
        cwd="/", capture_output=True, check=True, timeout=480,
    )
    need(json.loads(refresh.stdout).get("status") == "fresh_protected_ci_verified",
         "ISOLATED_NATIVE_CI_UNVERIFIED")
    request = signed_cutover_request(policy, actor)
    write(state / "owner-proof.json", canonical(request), 0o400)
    result = run_isolated_native(args.candidate_sha, request, state)
    need(digest(read(WORKER, 0, 0o755)) == WORKER_BEFORE
         and digest(read(CATALOG_POLICY,
                         0, 0o600, 8192)) == catalog_hash,
         "PROTECTED_SHARED_WORKER_OR_CATALOG_CHANGED")
    write(state / "accepted.json", canonical(result), 0o400)
    print("PMV4_E_ISOLATED_CUTOVER=VERIFIED")
    print(json.dumps(result["original_native_receipt"], sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--before-tree-sha256", required=True)
    parser.add_argument("--repair-and-cutover", action="store_true")
    parser.add_argument("--isolated-cutover", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    need(os.geteuid() == 0, "LOCAL_ROOT_REQUIRED")
    need(re.fullmatch("[0-9a-f]{40}", args.candidate_sha)
         and all(re.fullmatch("[0-9a-f]{64}", value) for value in
                 (args.archive_sha256, args.manifest_sha256, args.before_tree_sha256)),
         "EXACT_DIGESTS_REQUIRED")
    files, policy = plan(args.candidate_sha, args.archive_sha256, args.manifest_sha256)
    if args.isolated_cutover:
        complete_isolated(args, files, policy)
        return
    need(not args.apply, "SHARED_WORKER_INSTALL_REQUIRES_ISOLATED_CUTOVER")
    proposed = {
        "action": REPAIR_ACTION if args.repair_and_cutover else ACTION,
        "policy": policy, "archive_sha256": args.archive_sha256,
        "worker_before_sha256": REPAIR_WORKER if args.repair_and_cutover else WORKER_BEFORE,
        "worker_after_sha256": digest(files[WORKER_SOURCE]),
        "trust_before_sha256": args.before_tree_sha256,
        "installer_sha256": digest(Path(__file__).read_bytes()),
    }
    if args.repair_and_cutover:
        need(args.before_tree_sha256 == REPAIR_TREE, "REPAIR_EXACT_TREE_REQUIRED")
        proposed["queue_cutover"] = True
    if args.rollback:
        with locks():
            protected()
            rollback(files, policy, proposed)
        print("PMV4_E_DISPATCHER_ROLLBACK=VERIFIED")
        return
    with locks():
        protected()
        if args.repair_and_cutover:
            repair_baseline()
        else:
            need(not any(os.path.lexists(p) for p in (POLICY, RECORDS)),
                 "INSTALL_TARGET_EXISTS_OR_PARTIAL")
        need(not os.path.lexists(BASE / ("dispatch-install-" + args.candidate_sha)),
             "INSTALL_TARGET_EXISTS_OR_PARTIAL")
        need(tree(TRUST) == args.before_tree_sha256
             and digest(read(WORKER, 0, 0o755)) == proposed["worker_before_sha256"],
             "INSTALL_BASELINE_CHANGED")
        current_ci(files, args.candidate_sha)
        if args.repair_and_cutover:
            worker = load_code(files[WORKER_SOURCE], "stage_e_repaired_worker", WORKER)
            need(worker["_root_owner_identity_is_active"](
                "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
                "person-entra-bee80bdcffb04c50b453c09d4d411f5f"),
                "CANONICAL_OWNER_IDENTITY_NOT_ACTIVE")
            cutover_preflight()
    if not args.apply:
        print(json.dumps({"status": "read_only_preflight_passed", "scope": proposed}, sort_keys=True))
        return
    actor = owner(proposed)
    with locks():
        current_ci(files, args.candidate_sha)
        protected()
        receipt = {
            "scope": proposed, "owner_object_id": actor,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
        install(files, policy, receipt, args.before_tree_sha256)
    print("PMV4_E_DISPATCHER_INSTALL=VERIFIED", flush=True)
    if args.repair_and_cutover:
        result = queue_cutover(policy, actor)
        print("PMV4_E_CUTOVER=QUEUED REQUEST_ID=" + result["request_id"], flush=True)


if __name__ == "__main__":
    try:
        main()
    except (Denied, OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as exc:
        raise SystemExit("DENIED:" + type(exc).__name__ + ":" + str(exc)[:110])
