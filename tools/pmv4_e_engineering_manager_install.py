"""Exact, root-isolated native manager relocation; no standing new authority.

Must be launched from an externally hash-pinned protected-main checkout. The
existing native CI attestor, exact Owner verifier, production locks and root
transition worker remain authoritative. All production targets are fixed.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import ExitStack
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
BASELINE = "f79360ab053b4ab479d7053d99f75645a258f82c"
ROOT = Path("/usr/local/lib/jason/pmv4-e-engineering-manager")
LIB = Path("/home/al/.local/lib/jason")
USER_UNITS = Path("/home/al/.config/systemd/user")
SYSTEM_UNITS = Path("/etc/systemd/system")
STATE = Path("/var/lib/jason-owner-release/engineering-manager-install")
MANAGER = Path("/var/lib/jason/openclaw/release-manager")
POLICY = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
ENV = Path("/var/lib/jason/production-health.env")
PROFILE = Path("/opt/jason/current/config/autotask-entity-read-profile.json")
RECEIPT = Path("/etc/jason-owner-release/pmv4-e/engineering-manager-system-authorized.json")
STAGE_E = RECEIPT.with_name("replacement-retirement-accepted.json")
PAUSE = MANAGER.parent / "support-repair/pmv3-engineering-owner-pause.json"
PARALLEL = Path("/var/lib/jason-owner-release/parallel-development-install/fe4a941073dc55542554bfae2a78ac61a4a65c0e")
DROPIN = USER_UNITS / "jason-self-heal-watchdog.service.d/99-pmv4-e-accepted-source.conf"
EXPORTER = "jason-production-health-exporter.service"
TIMERS = ("jason-pmv4-engineering.timer", "jason-self-heal-watchdog.timer")
SERVICES = tuple(x.replace(".timer", ".service") for x in TIMERS)
UNITS = TIMERS + SERVICES
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ACTION = "RELOCATE-EXACT-PMV4-ENGINEERING-AND-WATCHDOG-MANAGERS"
NATIVE = {
    "tools/pmv4_e_dispatch_install.py": "6d276b67538e1bf988a751dc9ef10ac6996cc6955ff6bc3e562a506da13282f7",
    "tools/parallel_development_install.py": "e38e1c4f227d9d785c5610f6dece06b16064d98e7bc1ddd9f74cbb299ed198c8",
}
OLD = {
    USER_UNITS / SERVICES[0]: (0, 0o644, "e865a61a40b7dedb566b09759fab004325636f40e8179c028dc95a672bc59630"),
    USER_UNITS / TIMERS[0]: (0, 0o644, "8103e5cc8bdfa0ec9e3d87f763534cb7266a93ff32e3f674f2fd786b0d5385f2"),
    USER_UNITS / SERVICES[1]: (1000, 0o600, "fc49a66be3692c650f03a537cbd1d5265bee1d9e6593c91aab880fe1daf4ebb1"),
    USER_UNITS / TIMERS[1]: (1000, 0o600, "d1739344579c0cdcf9634b463818e79718c1742dd636b5a8b466926e16a11242"),
    DROPIN: (1000, 0o644, "ed1a2029bd4821f68acec8f1ed21a08583010dfecd28d79402f9ca8fb8c8c321"),
    LIB / "release_manager_host_runner.py": (1000, 0o755, "6c05cab43e04c69e482cc7073190899352174f73a627bc443609cc8d37bbf31c"),
    LIB / "jason_self_heal_watchdog.py": (1000, 0o700, "786aa5e64dde025c2c254a75a1295eef1d8491370516f0a19c6c8551db52be65"),
    POLICY: (0, 0o600, "9480380c2847b65d428927bd80e0cc101ae80f2a6b6ea8359b5e0a02e4ace47d"),
    ENV: (0, 0o644, "ff9b609ff0581a0f95a4742c15b6946e9bbad8c7ab3c9b8fc061fee923626a92"),
    PAUSE: (1000, 0o600, "4a5de8286bf9d77842ca94dafe6f1d38c1a835e8f12bc0dfda46b7a3cf867747"),
}
PARALLEL_FILES = {
    "owner_approved_development_worker.py": (0o700, "856eee72496931ca58d24997ba5c2ff172c81b74186b277b24efe238a414de27"),
    "dependency_conflict_service.py": (0o600, "517c6fd03033b13c1bfc2b3c261257fd9f5dcc3a281b1095872e7a19c920a8fa"),
    "development-concurrency-scopes.json": (0o600, "5d01893673c054b0f1636fffef8ad58c684e9352ef4b9136dcc2f33476e32423"),
    "isolated_service_common.py": (0o600, "b13b333e8463b2e32011872f4c82f0698ae7db001aaee8b28c089cd4dd110992"),
}
CLIENT = "pmv4_e_engineering_manager_client.py"
STAGE_SHA = "a74d159851ca82cd1d94e996ee9469cc7ad923046d36f642c341a8a90fd20141"
PARALLEL_RESULT_SHA = "e0fab889ba182db3092cfe55296dce66d27264834cfcaf1dd638f2b9d85f16be"
SOURCE_FILES = {
    "tools/pmv4_e_engineering_manager_install.py",
    "tools/pmv4_e_engineering_manager_guard.py",
    "tools/pmv4_e_engineering_manager_client.py",
    "tools/pmv4_e_engineering_manager_relocation.py",
    "tools/pmv4_e_engineering_manager_transaction.py",
    "tools/release_manager_host_runner.py",
    "tools/jason_self_heal_watchdog.py",
    "tools/tests/test_jason_self_heal_watchdog.py",
    "tests/test_pmv4_e_engineering_manager_relocation.py",
    "tests/test_pmv4_e_engineering_manager_guard.py",
    "tests/test_pmv4_e_engineering_manager_transaction.py",
    "tests/test_pmv4_e_engineering_manager_install.py",
    ".github/workflows/pmv4-e-providerfree-scheduler-parity.yml",
    "docs/operations/PMv4-Engineering-Manager-Sandbox-Recovery-20261125.md",
    *("infrastructure/pmv4-e-engineering-manager/systemd/" + n for n in UNITS),
}


def need(ok, why):
    if not ok:
        raise PermissionError("ENGINEERING_MANAGER_INSTALL_" + why)


def digest(raw):
    return sha256(raw).hexdigest()


def canon(row):
    return json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def load(raw, path):
    ns = {"__name__": "reviewed_engineering_manager_" + path.stem, "__file__": str(path)}
    exec(compile(raw, str(path), "exec"), ns)
    return ns


def image(raw, uid, mode):
    return (raw, uid, uid, mode)


def describe(value):
    return None if value is None else {"sha256": digest(value[0]), "uid": value[1],
                                       "gid": value[2], "mode": oct(value[3]), "bytes": len(value[0])}


def encode(values):
    return {str(k): None if v is None else [base64.b64encode(v[0]).decode(), *v[1:]]
            for k, v in values.items()}


def decode(values, allowed):
    need(set(values) == {str(x) for x in allowed}, "RECOVERY_TARGET_SET")
    return {Path(k): None if v is None else (base64.b64decode(v[0], validate=True), *v[1:])
            for k, v in values.items()}


def parent_fd(path):
    parent = path.parent
    need(parent.resolve(strict=True) == parent, "PARENT_ALIAS")
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    m = os.fstat(fd)
    try:
        need(m.st_uid == m.st_gid and m.st_uid in (0, 1000) and not m.st_mode & 0o022,
             "PARENT_CUSTODY")
        live = parent.lstat()
        need((live.st_dev, live.st_ino) == (m.st_dev, m.st_ino), "PARENT_CHANGED")
    except BaseException:
        os.close(fd)
        raise
    return fd


def snapshot_at(fd, name):
    try:
        f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None
    with os.fdopen(f, "rb") as s:
        m = os.fstat(s.fileno())
        need(stat.S_ISREG(m.st_mode) and m.st_nlink == 1 and m.st_uid == m.st_gid
             and m.st_uid in (0, 1000) and not m.st_mode & 0o022 and 0 < m.st_size <= 2000000,
             "FILE_CUSTODY:" + name)
        raw = s.read(2000001)
    need(len(raw) == m.st_size, "FILE_CHANGED")
    return (raw, m.st_uid, m.st_gid, stat.S_IMODE(m.st_mode))


def snapshot(path):
    if not path.parent.exists():
        need(not os.path.lexists(path.parent), "PARENT_ALIAS")
        return None
    fd = parent_fd(path)
    try:
        return snapshot_at(fd, path.name)
    finally:
        os.close(fd)


def replace_exact(path, before, after, rename_noreplace):
    fd = parent_fd(path)
    name = path.name
    temp = None
    try:
        need(snapshot_at(fd, name) == before, "BEFORE_IMAGE_CHANGED:" + name)
        if after is None:
            need(before is not None, "REMOVE_ABSENT")
            os.unlink(name, dir_fd=fd)
        else:
            temp = ".engineering-manager-" + name + "-" + digest(after[0])[:24] + ".tmp"
            out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            try:
                with os.fdopen(out, "wb") as f:
                    f.write(after[0]); f.flush()
                    os.fchown(f.fileno(), after[1], after[2])
                    os.fchmod(f.fileno(), after[3]); os.fsync(f.fileno())
                need(snapshot_at(fd, name) == before, "TARGET_CHANGED_DURING_STAGE")
                if before is None:
                    rename_noreplace(fd, temp, name)
                else:
                    os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
            finally:
                try: os.unlink(temp, dir_fd=fd)
                except FileNotFoundError: pass
        os.fsync(fd)
        need(snapshot_at(fd, name) == after, "AFTER_IMAGE_CHANGED:" + name)
    finally:
        os.close(fd)


def cleanup_staged(path, values):
    if not path.parent.is_dir():
        return
    fd = parent_fd(path)
    try:
        for value in values:
            if value is None:
                continue
            name = ".engineering-manager-" + path.name + "-" + digest(value[0])[:24] + ".tmp"
            try:
                temp = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            except FileNotFoundError:
                continue
            with os.fdopen(temp, "rb") as f:
                m = os.fstat(f.fileno())
                raw = f.read(len(value[0]) + 1)
                complete = (m.st_uid,m.st_gid,stat.S_IMODE(m.st_mode)) == value[1:] and raw == value[0]
                partial = m.st_uid == m.st_gid == 0 and stat.S_IMODE(m.st_mode) == 0o600 and value[0].startswith(raw)
                need(stat.S_ISREG(m.st_mode) and m.st_nlink == 1 and (complete or partial),
                     "FOREIGN_STAGED_TEMP")
                current = os.stat(name, dir_fd=fd, follow_symlinks=False)
                need((m.st_dev,m.st_ino)==(current.st_dev,current.st_ino),"TEMP_CHANGED")
            os.unlink(name,dir_fd=fd)
            os.fsync(fd)
    finally:
        os.close(fd)


def target_set(candidate):
    need(re.fullmatch("[0-9a-f]{40}",candidate) is not None,"INVALID_CANDIDATE")
    artifacts = [*PARALLEL_FILES,"release_manager_host_runner.py","jason_self_heal_watchdog.py",CLIENT]
    return (set(OLD) | {SYSTEM_UNITS/n for n in UNITS} | {LIB/CLIENT, RECEIPT, ROOT/"manager_guard.py"}
            | {ROOT/"releases"/candidate/"tools"/n for n in artifacts})



def native():
    need(os.geteuid() == 0 and sys.flags.isolated == 1, "ROOT_ISOLATED_REQUIRED")
    out = []
    for name, pin in NATIVE.items():
        path = REPO / name
        v = snapshot(path)
        need(v is not None and v[1] == 1000 and digest(v[0]) == pin, "NATIVE_HELPER_CHANGED")
        out.append(load(v[0], path))
    return out


def source_review(candidate, p, *, recovery=False):
    git = lambda *args: p["git"](REPO, *args)
    need(re.fullmatch("[0-9a-f]{40}", candidate) is not None and
         git("rev-parse", "HEAD").decode().strip() == candidate and
         not git("status", "--porcelain", "--untracked-files=all").strip() and
         git("remote", "get-url", "origin").decode().strip() == "https://github.com/al-teamaot-com/jason.git" and
         git("rev-parse", "--is-shallow-repository").decode().strip() == "false",
         "PROTECTED_CHECKOUT_NOT_EXACT")
    changed = set(git("diff", "--name-only", BASELINE, candidate).decode().splitlines())
    need(changed == SOURCE_FILES, "UNREVIEWED_SOURCE_CHANGE")
    if not recovery:
        helper_path = p["NATIVE"] / "pmv4_e_ci_refresh.py"
        helper = p["native_code"](helper_path, str(helper_path), 0, 0o444)
        attestor = helper["load_pinned_attestor"](helper["SOURCE"], production=True)
        helper["paginate_required_checks"](attestor)
        ci = attestor["verify_ci"](candidate)
        need(ci["candidate_sha"] == candidate and ci["required_ci_passed"] is True and
             ci["protected_main_ancestor"] is True and ci["protected_main"] == candidate and
             p["command"]([*p["USER"], "/usr/bin/git", "ls-remote",
                           "https://github.com/al-teamaot-com/jason.git", "refs/heads/main"]).decode().split()
             == [candidate, "refs/heads/main"], "CURRENT_MAIN_CI_NOT_EXACT")
    files = {}
    for name in sorted(SOURCE_FILES):
        raw = git("show", candidate + ":" + name)
        need(raw == p["read"](REPO / name, 1000, source=True), "SOURCE_BYTES_CHANGED")
        files[name] = raw
    need(files["tools/pmv4_e_engineering_manager_install.py"] == Path(__file__).read_bytes(),
         "EXECUTED_INSTALLER_CHANGED")
    return files


class NativeAdapter:
    def __init__(self, candidate, n, p, code):
        self.candidate = candidate
        self.n, self.p, self.code = n, p, code
        self.g = load(code["tools/pmv4_e_engineering_manager_guard.py"],
                      REPO / "tools/pmv4_e_engineering_manager_guard.py")
        self.m = load(code["tools/pmv4_e_engineering_manager_relocation.py"],
                      REPO / "tools/pmv4_e_engineering_manager_relocation.py")
        self.t = load(code["tools/pmv4_e_engineering_manager_transaction.py"],
                      REPO / "tools/pmv4_e_engineering_manager_transaction.py")
        self.release = ROOT / "releases" / candidate / "tools"
        self.directory = STATE / candidate
        self.lock = None
        self.actor = None
        self.plan = None
        self.before = self.after = None
        self.receipt_bytes = None

    def command(self, args, timeout=90):
        return self.p["command"](list(args), timeout=timeout)

    def systemctl(self, args, user=False, timeout=90):
        return self.command([*(self.p["USER"] if user else ()), "/usr/bin/systemctl",
                             *(["--user"] if user else []), *args], timeout)

    def properties(self, name, user):
        keys = ("LoadState", "ActiveState", "MainPID", "UnitFileState", "FragmentPath", "DropInPaths")
        data = self.systemctl(["show", name, *["-p" + k for k in keys]], user)
        return dict(x.split("=", 1) for x in data.decode().splitlines() if "=" in x)

    def inspect(self):
        p = self.p
        need(not os.path.lexists(ROOT) and not os.path.lexists(RECEIPT)
             and not os.path.lexists(self.directory), "SUCCESSOR_ALREADY_PRESENT")
        self.n["directory"](STATE.parent, 0o700)
        need(digest(p["read"](STAGE_E, 0, 0o444)) == STAGE_SHA, "STAGE_E_CHANGED")
        need(digest(p["read"](PARALLEL / "result.json", 0, 0o600)) == PARALLEL_RESULT_SHA,
             "PARALLEL_RECEIPT_CHANGED")
        need(digest(p["read"](PARALLEL / "approval.json", 0, 0o600)) ==
             "07b2b023a3fd2b4373a9b098c471f0d57184dc28ce3dbcba6cabf509a5fb2dd1",
             "PARALLEL_APPROVAL_CHANGED")
        before = {}
        for target, (uid, mode, pin) in OLD.items():
            v = snapshot(target)
            need(v is not None and v[1:] == (uid, uid, mode) and digest(v[0]) == pin,
                 "PINNED_BEFORE_CHANGED:" + target.name)
            before[target] = v
        for name in UNITS:
            old = self.properties(name, True); new = self.properties(name, False)
            need(old.get("LoadState") == "loaded" and old.get("FragmentPath") == str(USER_UNITS / name),
                 "OLD_UNIT_CHANGED")
            need(new.get("LoadState") == "not-found" and new.get("ActiveState") == "inactive",
                 "SYSTEM_COUNTERPART_ALREADY_EXISTS")
            if name in TIMERS:
                need(old.get("ActiveState") == "active" and old.get("UnitFileState") == "enabled",
                     "OLD_TIMER_NOT_ENABLED")
            else:
                need(old.get("ActiveState") == "inactive" and old.get("MainPID") == "0",
                     "OLD_SERVICE_NOT_QUIESCENT")
            want = str(DROPIN) if name == SERVICES[1] else ""
            need(old.get("DropInPaths", "") == want, "OLD_DROPIN_CHANGED")
        protected = p["protected_health"](expected_guard_sha=p["GUARD_AFTER_SHA"])
        control = json.loads(p["read"](MANAGER / "production-control-state.json", 0, 0o600))
        profile_raw = p["read"](PROFILE, 0)
        new_env = self.t["monitoring_environment"](before[ENV][0], profile_raw,
                                                    control["last_known_good"]["manifest"])
        new_policy = self.m["desired_state_delta"](json.loads(before[POLICY][0]))
        after = {k: None if k.parent == USER_UNITS or k == DROPIN else v for k, v in before.items()}
        after[POLICY] = image(json.dumps(new_policy, sort_keys=True, indent=2).encode()+b"\n", 0, 0o600)
        after[ENV] = image(new_env, 0, 0o644)
        source_units = self.m["units"](REPO)
        unit_hashes = {}
        for name in UNITS:
            rel = "infrastructure/pmv4-e-engineering-manager/systemd/" + name
            raw = self.code[rel]
            need(raw == source_units[rel], "GENERATED_UNIT_MISMATCH")
            after[SYSTEM_UNITS / name] = image(raw, 0, 0o644)
            unit_hashes[name] = digest(raw)
        artifacts = {}
        for name, mode in (("release_manager_host_runner.py", 0o755),
                           ("jason_self_heal_watchdog.py", 0o700), (CLIENT, 0o600)):
            raw = self.code["tools/" + name]
            after[LIB / name] = image(raw, 1000, mode)
            after[self.release / name] = image(raw, 0, 0o444)
            artifacts[name] = digest(raw)
        for name, (mode, pin) in PARALLEL_FILES.items():
            raw = p["read"](LIB / name, 1000, mode)
            need(digest(raw) == pin, "PARALLEL_ARTIFACT_CHANGED")
            after[self.release / name] = image(raw, 0, 0o444)
            artifacts[name] = pin
        after[ROOT / "manager_guard.py"] = image(self.code["tools/pmv4_e_engineering_manager_guard.py"], 0, 0o444)
        for path in after:
            if path not in before:
                need(snapshot(path) is None, "NEW_TARGET_EXISTS:" + path.name)
                before[path] = None
        before[RECEIPT] = None
        # The receipt is constructed only after native Owner verification.
        plan = {"action": ACTION, "policy": {"candidate_sha": self.candidate, "rollback_sha": LKG},
                "old_user_timers": list(TIMERS), "new_system_timers": list(TIMERS), "services": list(SERVICES),
                "production_authority": False, "provider_writes": False, "runtime_or_mcp_restart_allowed": False,
                "freeze_or_hold_change": False, "monitoring_restart": EXPORTER,
                "pause_preserved_during_cutover": True, "rollback_authorized": True,
                "queue_cutover": False, "resume_after_cutover": True,
                "resume_target": str(PAUSE), "resume_before_sha256": OLD[PAUSE][2],
                "resume_only_after_native_cutover_verification": True,
                "readonly_systemd_acceptance_probe":"jason-engineering-manager-readonly-acceptance",
                "restore_pause_on_failed_scheduled_acceptance": True,
                "installation_targets": [str(x) for x in sorted(before)],
                "before": {str(k): describe(v) for k,v in before.items()},
                "after": {str(k): describe(v) for k,v in after.items()},
                "root_receipt_recipe": {"stage_e_sha256": STAGE_SHA,
                    "parallel_result_sha256": PARALLEL_RESULT_SHA, "unit_sha256": unit_hashes,
                    "artifact_sha256": artifacts, "effective_policy_sha256": digest(after[POLICY][0]),
                    "guard_sha256": digest(after[ROOT / "manager_guard.py"][0])},
                "protected_health": protected,
                "source_hashes": {k:digest(v) for k,v in self.code.items()},
                "rollback": "restore exact reviewed file images and original user timers; preserve pause, freeze, hold and runtime; native revalidation only"}
        return plan, before, after

    def verify_owner_and_before(self, plan, sha):
        need(self.actor is not None and self.plan == plan and self.t["verify_plan"](plan) == sha,
             "OWNER_SCOPE_UNVERIFIED")
        self.lock = self.n["locks"](); self.lock.__enter__()
        try:
            need(source_review(self.candidate, self.p) == self.code, "APPROVED_SOURCE_CHANGED")
            again, self.before, self.after = self.inspect()
            need(again == plan, "APPROVED_SCOPE_CHANGED")
        except BaseException:
            self.release_lock()
            raise
        return True

    def release_lock(self):
        if self.lock is not None:
            self.lock.__exit__(None, None, None); self.lock = None

    def persist_before_images(self, plan):
        if not STATE.exists():
            STATE.mkdir(mode=0o700); self.n["sync_dir"](STATE.parent)
        self.n["directory"](STATE, 0o700)
        self.directory.mkdir(mode=0o700)
        self.n["sync_dir"](STATE)
        record = {"scope": plan, "scope_sha256": self.t["verify_plan"](plan),
                  "owner_oid": self.actor, "approved_at": stamp(),
                  "before_images": encode(self.before), "after_images": encode(self.after)}
        raw = canon(record)
        self.n["write"](self.directory/"approval.json", raw, 0o400)
        receipt = {"schema_version":"1.0","action":ACTION,"status":"accepted",
                   "candidate_sha":self.candidate,"rollback_sha":LKG,
                   "scope_sha256":record["scope_sha256"],"approval_sha256":digest(raw),
                   **plan["root_receipt_recipe"],"accepted_at":stamp()}
        self.g["validate_receipt"](receipt)
        self.receipt_bytes = canon(receipt)
        self.after[RECEIPT] = image(self.receipt_bytes, 0, 0o444)
        self.n["write"](self.directory/"receipt-image.json", self.receipt_bytes, 0o400)

    def stop_old_timers(self, names):
        need(tuple(names) == TIMERS, "OLD_TIMER_SCOPE")
        self.systemctl(["disable", "--now", *names], True)

    def verify_old_services_quiescent(self, names):
        need(tuple(names) == SERVICES, "OLD_SERVICE_SCOPE")
        for _ in range(30):
            if all(self.properties(n, True).get("ActiveState") == "inactive" and
                   self.properties(n, True).get("MainPID") == "0" for n in names):
                return
            time.sleep(1)
        need(False, "OLD_SERVICE_DID_NOT_QUIESCE")

    def publish_files_without_receipt(self, plan):
        for d in (ROOT, ROOT/"releases", self.release.parent, self.release):
            d.mkdir(mode=0o755); self.n["sync_dir"](d.parent)
        for path in self.after:
            if path != RECEIPT and self.before[path] != self.after[path]:
                replace_exact(path, self.before[path], self.after[path], self.p["rename_noreplace"])

    def reload_managers(self):
        self.systemctl(["daemon-reload"], True)
        self.systemctl(["daemon-reload"])

    def verify_old_units_retired(self, names):
        need(set(names) == set(UNITS), "RETIRED_SCOPE")
        for name in names:
            props = self.properties(name, True)
            need(props.get("LoadState") == "not-found" and props.get("ActiveState") == "inactive"
                 and not props.get("FragmentPath") and not props.get("DropInPaths"), "OLD_UNIT_NOT_RETIRED")

    def enable_new_system_timers(self, names):
        need(tuple(names) == TIMERS, "SYSTEM_TIMER_SCOPE")
        self.systemctl(["enable", "--now", *names])

    def verify_new_timers(self, names):
        for name in names:
            row = self.properties(name, False)
            need(row.get("ActiveState") == "active" and row.get("UnitFileState") == "enabled",
                 "SYSTEM_TIMER_NOT_ENABLED")

    def restart_exact_monitoring_exporter(self):
        self.systemctl(["restart", EXPORTER])

    def verify_approved_monitoring_expectations(self):
        probe = ("import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:9467/metrics',timeout=8); "
                 "s=r.read(2000000).decode(); a=s.splitlines(); "
                 "assert all('jason_mcp_contract{check=\"'+k+'\"} 1' in a or "
                 "'jason_mcp_contract{check=\"'+k+'\"} 1.0' in a for k in ('image','provider_profile','source_revision')); "
                 "print('MCP_EXPECTATIONS_VERIFIED')")
        for _ in range(20):
            try:
                raw = self.command([*self.p["USER"], "/usr/bin/python3", "-I", "-B", "-c", probe], 12)
                if raw.strip() == b"MCP_EXPECTATIONS_VERIFIED":
                    return
            except (OSError, PermissionError, subprocess.SubprocessError):
                pass
            time.sleep(2)
        need(False, "MONITORING_CONTRACT_NOT_VERIFIED")

    def publish_exact_native_receipt(self, plan, sha):
        need(self.after[RECEIPT][0] == self.receipt_bytes and
             json.loads(self.receipt_bytes)["scope_sha256"] == sha, "RECEIPT_SCOPE_CHANGED")
        replace_exact(RECEIPT, None, self.after[RECEIPT], self.p["rename_noreplace"])

    def verify_successor_topology_and_source(self, *, resumed=False):
        raw = self.command([*self.p["USER"], "/usr/bin/python3", "-I", "-B",
                            str(ROOT/"manager_guard.py"), "--status"], 130)
        proof = json.loads(raw)
        need(proof.get("status") == "verified_system_manager" and proof.get("candidate_sha") == self.candidate
             and proof.get("production_authority") is False, "SUCCESSOR_GUARD_DENIED")
        for path, value in self.after.items():
            expected = None if resumed and path == PAUSE else value
            need(snapshot(path) == expected, "INSTALLED_FILE_READBACK_CHANGED")
        code = ("import json,sys;sys.path[:0]=['/home/al/.local/lib/jason','/opt/jason/current/tools'];"
                "import jason_self_heal_watchdog as w;f,e=w.production_convergence_failures();"
                "print(json.dumps({'failures':f,'mode':e.get('pmv4_e_controlplane_mode')}))")
        row = json.loads(self.command([*self.p["USER"], "/usr/bin/python3", "-I", "-B", "-c", code], 180))
        need(row == {"failures": [], "mode": "replacement"}, "WATCHDOG_CONVERGENCE_NOT_VERIFIED")

    def verify_preserved_pause_and_controls(self):
        need(snapshot(PAUSE) == self.before[PAUSE], "PAUSE_CHANGED")
        need(self.p["control_bytes"]() == self.plan["protected_health"]["controls"], "PROTECTED_CONTROL_CHANGED")

    def native_revalidation(self):
        self.systemctl(["start", "jason-production-drift-watchdog.service"])
        code = ("import json,sys;from pathlib import Path;sys.path[:0]=['/home/al/.local/lib/jason','/opt/jason/current/tools'];"
                "import release_manager_host_runner as r;"
                "r.request_root_control_transition(Path(sys.argv[1]),action='revalidate',revision=sys.argv[2]);"
                "print('NATIVE_REVALIDATION_REQUEST_ACCEPTED')")
        self.command([*self.p["USER"], "/usr/bin/python3", "-I", "-B", "-c", code, str(MANAGER), LKG], 145)
        for _ in range(30):
            row = json.loads(self.p["read"](MANAGER/"protected-readback/production-control-state.json",1000,0o600))
            drift = json.loads(self.p["read"](MANAGER/"protected-readback/production-drift.json",1000,0o600))
            if (row.get("circuit_breaker",{}).get("state") == "closed" and
                row.get("circuit_breaker",{}).get("revalidated_revision") == LKG and
                drift.get("status") == "pass" and drift.get("problems") == []):
                return
            time.sleep(1)
        need(False, "NATIVE_REVALIDATION_READBACK_FAILED")

    def verify_native_drift_and_lkg(self):
        # Independent read-only evaluation under the same native lock, then
        # release it before requesting the existing root transition.
        guard = Path("/opt/jason/current/tools/production_drift_guard.py")
        need(digest(self.p["read"](guard,0)) == self.p["PINNED"][str(guard)], "NATIVE_DRIFT_CODE_CHANGED")
        row = json.loads(self.command(["/usr/bin/python3", str(guard), "--config", str(POLICY)], 75))
        need(row.get("status") == "pass" and row.get("problems") == [], "NATIVE_DRIFT_DENIED")
        self.release_lock()
        self.native_revalidation()
        self.verify_preserved_pause_and_controls()
        self.verify_successor_topology_and_source()
        # Independently preserve exact container identities/images/start times.
        data = json.loads(self.command(["/usr/bin/docker", "inspect", "--type", "container", *self.p["PEERS"]]))
        peers = {r["Name"].lstrip("/"): {"id": r["Id"], "image": r["Image"],
                 "started_at": r["State"]["StartedAt"]} for r in data}
        need(peers == self.plan["protected_health"]["protected_peers"] and
             all(r["State"]["Running"] is True and (r["State"].get("Health") or {}).get("Status") in ("healthy",None)
                 for r in data), "PROTECTED_PEERS_CHANGED")

    def record_cutover_verified(self):
        self.n["write"](self.directory/"result.json",
                        canon({"status":"cutover_verified_paused","scope_sha256":self.t["verify_plan"](self.plan),
                               "at":stamp(),"live_scheduler_unpaused":False,"production_authority":False}),0o400)

    def restore_before_images_and_topology(self, plan):
        if self.lock is None:
            self.lock = self.n["locks"](); self.lock.__enter__()
        # Only an authenticated native transaction may call rollback. Refuse
        # all foreign file images before any restorative write.
        need(self.before is not None and self.after is not None, "ROLLBACK_IMAGES_MISSING")
        for path, old in self.before.items():
            new = self.after.get(path)
            need(snapshot(path) in (old,new), "FOREIGN_ROLLBACK_IMAGE:" + path.name)
        for path, old in self.before.items():
            cleanup_staged(path,(old,self.after.get(path)))
        # Remove admission first so no new system worker can launch.
        if snapshot(RECEIPT) is not None:
            replace_exact(RECEIPT,self.after[RECEIPT],None,self.p["rename_noreplace"])
        for name in TIMERS:
            if self.properties(name,False).get("LoadState") == "loaded":
                self.systemctl(["disable","--now",name])
        for _ in range(30):
            if all(self.properties(n,False).get("ActiveState") in ("inactive","failed")
                   and self.properties(n,False).get("MainPID","0") in ("","0") for n in SERVICES):
                break
            time.sleep(1)
        else:
            need(False,"ROLLBACK_WORKER_NOT_QUIESCENT")
        for path in reversed(list(self.after)):
            if path == RECEIPT: continue
            current = snapshot(path)
            if current != self.before[path]:
                replace_exact(path,current,self.before[path],self.p["rename_noreplace"])
        for d in (self.release,self.release.parent,ROOT/"releases",ROOT):
            if d.exists(): d.rmdir(); self.n["sync_dir"](d.parent)
        self.reload_managers()
        self.systemctl(["enable","--now",*TIMERS],True)
        # Reset only the failed relocated service latches, never the breaker.
        for name in SERVICES:
            if self.properties(name,False).get("ActiveState") == "failed":
                self.systemctl(["reset-failed",name])
        self.restart_exact_monitoring_exporter()
        self.release_lock()
        self.native_revalidation()

    def verify_rollback_and_preserved_controls(self):
        need(all(snapshot(p)==v for p,v in self.before.items()),"ROLLBACK_BYTES_CHANGED")
        self.verify_preserved_pause_and_controls()
        need(all(self.properties(n,True).get("ActiveState")=="active" for n in TIMERS),
             "ROLLBACK_TIMER_NOT_ACTIVE")

    def record_rollback(self):
        self.n["write"](self.directory/"rollback.json",
                        canon({"status":"original_topology_restored","scope_sha256":self.t["verify_plan"](self.plan),
                               "at":stamp(),"production_authority":False}),0o400)


    def load_record(self):
        self.n["directory"](STATE,0o700); self.n["directory"](self.directory,0o700)
        raw = self.n["read"](self.directory/"approval.json",0,0o400,8_000_000)
        record = json.loads(raw)
        plan = record["scope"]
        sha = self.t["verify_plan"](plan)
        need(sha == record["scope_sha256"] and plan["policy"]["candidate_sha"] == self.candidate
             and re.fullmatch("[0-9a-f-]{36}",str(record.get("owner_oid",""))) is not None
             and plan.get("rollback_authorized") is True
             and plan["source_hashes"] == {k:digest(v) for k,v in self.code.items()}
             and set(plan["installation_targets"]) == {str(p) for p in target_set(self.candidate)},
             "RECOVERY_APPROVAL_IDENTITY")
        self.plan = plan
        self.actor = record["owner_oid"]
        self.before = decode(record["before_images"],target_set(self.candidate))
        self.after = decode(record["after_images"],target_set(self.candidate)-{RECEIPT})
        need({str(k):describe(v) for k,v in self.before.items()} == plan["before"]
             and {str(k):describe(v) for k,v in self.after.items()} == plan["after"],
             "RECOVERY_FILE_IMAGES_CHANGED")
        receipt = self.directory/"receipt-image.json"
        if receipt.exists():
            self.receipt_bytes = self.n["read"](receipt,0,0o400)
            row = self.g["validate_receipt"](json.loads(self.receipt_bytes))
            need(row["approval_sha256"] == digest(raw) and row["scope_sha256"] == sha
                 and row["candidate_sha"] == self.candidate
                 and all(row[k]==v for k,v in plan["root_receipt_recipe"].items()),
                 "RECOVERY_RECEIPT_IDENTITY")
            self.after[RECEIPT] = image(self.receipt_bytes,0,0o444)
        else:
            self.after[RECEIPT] = None
        return sha

    def recover(self):
        self.load_record()
        need(not os.path.lexists(self.directory/"result.json")
             and not os.path.lexists(self.directory/"rollback.json"),"RECOVERY_ALREADY_TERMINAL")
        if self.receipt_bytes is None:
            # The receipt image is persisted before any production mutation.
            need(all(snapshot(p)==v for p,v in self.before.items()),"MUTATION_BEFORE_DURABLE_RECEIPT")
            self.record_rollback()
            return
        try:
            self.restore_before_images_and_topology(self.plan)
            self.verify_rollback_and_preserved_controls()
            self.record_rollback()
        finally:
            self.release_lock()

    def resume_verified_cutover(self):
        # The same native exact Owner approval explicitly includes resume after
        # successful cutover. This is not a fresh or standing approval.
        sha = self.load_record()
        need(self.plan.get("resume_after_cutover") is True
             and self.plan.get("resume_target") == str(PAUSE)
             and self.plan.get("resume_before_sha256") == OLD[PAUSE][2]
             and self.plan.get("resume_only_after_native_cutover_verification") is True
             and not os.path.lexists(self.directory/"rollback.json"),"RESUME_SCOPE_NOT_AUTHORIZED")
        result = json.loads(self.n["read"](self.directory/"result.json",0,0o400))
        need(result.get("status")=="cutover_verified_paused" and result.get("scope_sha256")==sha,
             "CUTOVER_NOT_VERIFIED")
        with self.n["locks"]():
            need(not os.path.lexists(self.directory/"activation.json"),"RESUME_ALREADY_RECORDED")
            self.verify_successor_topology_and_source()
            self.verify_preserved_pause_and_controls()
            row = json.loads(self.p["read"](MANAGER/"production-control-state.json",0,0o600))
            need(row.get("circuit_breaker",{}).get("state")=="closed"
                 and row.get("circuit_breaker",{}).get("revalidated_revision")==LKG,
                 "NATIVE_BREAKER_NOT_REVALIDATED")
            drift = json.loads(self.p["read"](MANAGER/"production-drift.json",0,0o600))
            age = (datetime.now(timezone.utc)-datetime.fromisoformat(drift["observed_at"])).total_seconds()
            need(drift.get("status")=="pass" and drift.get("problems")==[] and 0<=age<=120,
                 "NATIVE_DRIFT_NOT_FRESH")
            need(self.properties(SERVICES[0],False).get("ActiveState")=="inactive",
                 "ENGINEERING_NOT_QUIESCENT")
            # Read-only production health verification; no watchdog recovery or
            # provider mutation is invoked by this probe.
            probe=("import json,sys;sys.path[:0]=['/home/al/.local/lib/jason','/opt/jason/current/tools'];"
                   "import owner_approved_development_worker as w;from pathlib import Path;"
                   "print(json.dumps(w.verified_development_health(Path('/var/lib/jason/openclaw/support-repair'))))")
            # Test the actual system-manager mount namespace, not the shell
            # namespace that hid the first scheduled failure.
            probe=("import os,sys,json;from pathlib import Path;"
                   "assert os.getuid()==os.getgid()==1000;"
                   "assert Path('/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json').stat().st_uid==0;"
                   "assert 'NoNewPrivs:\t1' in Path('/proc/self/status').read_text();"
                   "p=Path('/home/al/.local/lib/jason/engineering-worker-source');"
                   "assert bool(os.statvfs(p).f_flag&os.ST_RDONLY) and os.access(p/'.git',os.W_OK);"
                   +probe)
            health=json.loads(self.command(["/usr/bin/systemd-run","--quiet","--wait","--pipe","--collect",
                "--unit=jason-engineering-manager-readonly-acceptance",
                "-p","User=al","-p","Group=al","-p","NoNewPrivileges=yes","-p","PrivateTmp=yes",
                "-p","ProtectSystem=strict","-p","ProtectHome=read-only",
                "-p","Environment=HOME=/home/al",
                "-p","Environment=XDG_RUNTIME_DIR=/run/user/1000",
                "-p","Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
                "-p","ReadWritePaths=/home/al/.local/lib/jason/engineering-worker-source/.git",
                "/usr/bin/python3","-I","-B","-c",probe],150))
            need(health.get("verified") is True and health.get("production_authority") is False,
                 "SYSTEM_MANAGER_DEVELOPMENT_HEALTH_NOT_VERIFIED")
            # Persist the exact rollback image before unlink; if any write
            # after removal fails, restore the pause immediately.
            attempt=self.directory/"activation-attempt.json"
            need(not os.path.lexists(attempt),"ACTIVATION_ATTEMPT_REQUIRES_RECOVERY")
            self.n["write"](attempt,canon({"scope_sha256":sha,"pause_sha256":OLD[PAUSE][2],
                                           "at":stamp(),"rollback_authorized":True}),0o400)
            try:
                replace_exact(PAUSE,self.before[PAUSE],None,self.p["rename_noreplace"])
                self.n["write"](self.directory/"activation.json",
                    canon({"status":"resumed_pending_scheduled_acceptance","scope_sha256":sha,
                           "at":stamp(),"production_authority":False}),0o400)
            except BaseException:
                if snapshot(PAUSE) is None:
                    replace_exact(PAUSE,None,self.before[PAUSE],self.p["rename_noreplace"])
                raise


    def verify_activation(self):
        sha=self.load_record()
        act=json.loads(self.n["read"](self.directory/"activation.json",0,0o400))
        need(act.get("scope_sha256")==sha and act.get("status")=="resumed_pending_scheduled_acceptance",
             "ACTIVATION_RECEIPT_INVALID")
        start=datetime.fromisoformat(act["at"])
        need(snapshot(PAUSE) is None,"ACTIVATION_PAUSED")
        self.verify_successor_topology_and_source(resumed=True)
        state_dir=PAUSE.parent
        states={}
        for name in ("pmv3-engineering-controller-state.json","engineering-pipeline-state.json",
                     "development-state.json"):
            states[name]=json.loads(self.p["read"](state_dir/name,1000,0o600))
        controller=states["pmv3-engineering-controller-state.json"]
        pipeline=states["engineering-pipeline-state.json"]
        development=states["development-state.json"]
        admission=development.get("dependency_admission") or {}
        health=admission.get("production_health_evidence") or {}
        def fresh(value):
            try:
                return datetime.fromisoformat(value.replace("Z","+00:00"))>=start
            except (AttributeError,ValueError,TypeError):
                return False
        timer=self.systemctl(["show",TIMERS[0],"-pLastTriggerUSec"]).decode().strip().partition("=")[2]
        try:
            timer_at=datetime.fromtimestamp(int(self.command(["/usr/bin/date","-d",timer,"+%s"]).decode()),timezone.utc)
        except (OSError,ValueError,PermissionError,subprocess.SubprocessError):
            timer_at=datetime.fromtimestamp(0,timezone.utc)
        service=self.systemctl(["show",SERVICES[0],"-pActiveState","-pResult","-pExecMainStatus",
                                "-pConditionResult","-pMainPID"]).decode()
        svc=dict(x.split("=",1) for x in service.splitlines() if "=" in x)
        drift=json.loads(self.p["read"](MANAGER/"production-drift.json",0,0o600))
        control=json.loads(self.p["read"](MANAGER/"production-control-state.json",0,0o600))
        fresh_admission=(fresh(admission.get("observed_at")) and health.get("verified") is True
                         and admission.get("production_authority") is False)
        holds=admission.get("active_editor_holds") or {}
        records=development.get("items") or {}
        editor={"identified","diagnosing","implementing","ci_repair_needed","ci_repairing"}
        conflicts=admission.get("existing_conflicts") or []
        def held(c):
            a,b=c["a"],c["b"]
            if records.get(a,{}).get("phase") not in editor and records.get(b,{}).get("phase") not in editor:
                return True
            return any(x.get("with")==b for x in holds.get(a,[])) or any(x.get("with")==a for x in holds.get(b,[]))
        peer_rows=json.loads(self.command(["/usr/bin/docker","inspect","--type","container",*self.p["PEERS"]]))
        peers={r["Name"].lstrip("/"):{"id":r["Id"],"image":r["Image"],"started_at":r["State"]["StartedAt"]}
               for r in peer_rows}
        controls=self.plan["protected_health"]["controls"]
        for path in (self.n["FREEZE"],self.n["HOLD"]):
            uid,mode,pin=self.p["CONTROLS"][path]
            need(digest(self.p["read"](path,uid,mode))==pin==controls[str(path)],"CONTROL_CHANGED")
        evidence={
            "normal_timer_invocation":timer_at>=start and fresh(controller.get("started_at"))
                 and svc.get("ConditionResult")=="yes",
            "native_manager_guard":"pass",
            "worker_identity":"al",
            "pipeline_completed":fresh(pipeline.get("finished_at")) and fresh(controller.get("finished_at"))
                 and svc.get("ActiveState")=="inactive" and svc.get("Result")=="success"
                 and svc.get("ExecMainStatus")=="0" and not pipeline.get("failed_control_stages")
                 and pipeline.get("stages",{}).get("development",{}).get("status")=="succeeded",
            "dependency_admission_verified":fresh_admission,
            "conflicting_work_blocked":all(held(c) for c in conflicts),
            "observed_conflict_count":len(conflicts),
            "protected_peers_unchanged":peers==self.plan["protected_health"]["protected_peers"],
            "native_drift":drift.get("status") if drift.get("problems")==[]
                and 0 <= (datetime.now(timezone.utc)-datetime.fromisoformat(drift["observed_at"])).total_seconds() <= 120 else "fail",
            "breaker":control.get("circuit_breaker",{}).get("state")
                if control.get("circuit_breaker",{}).get("revalidated_revision")==LKG else "unverified",
            "production_authority":False,
            "controller_status":controller.get("status"),
            "pipeline_status":pipeline.get("status"),
            "max_active_engineering":development.get("max_active_engineering"),
        }
        # The final acceptance receipt requires actual normal-cycle evidence;
        # it is not manufactured from source tests or service installation.
        if not all(evidence.get(k) is True for k in ("normal_timer_invocation","pipeline_completed",
                "dependency_admission_verified","conflicting_work_blocked","protected_peers_unchanged")) or \
                evidence["native_drift"]!="pass" or evidence["breaker"]!="closed":
            print(json.dumps({"status":"scheduled_acceptance_pending_or_failed","evidence":evidence},sort_keys=True))
            return False
        with self.n["locks"]():
            need(snapshot(PAUSE) is None,"ACTIVATION_PAUSED_DURING_ACCEPTANCE")
            if not os.path.lexists(self.directory/"scheduled-acceptance.json"):
                self.n["write"](self.directory/"scheduled-acceptance.json",canon({
                    "status":"scheduled_engineering_acceptance_verified","scope_sha256":sha,
                    "at":stamp(),"evidence":evidence}),0o400)
        print(json.dumps({"status":"scheduled_engineering_acceptance_verified","evidence":evidence},sort_keys=True))
        return True

    def restore_failed_activation_pause(self):
        sha=self.load_record()
        need(self.plan.get("restore_pause_on_failed_scheduled_acceptance") is True
             and not os.path.lexists(self.directory/"scheduled-acceptance.json"),"ACTIVATION_ROLLBACK_NOT_AUTHORIZED")
        attempt=json.loads(self.n["read"](self.directory/"activation-attempt.json",0,0o400))
        need(attempt.get("scope_sha256")==sha and attempt.get("pause_sha256")==OLD[PAUSE][2]
             and attempt.get("rollback_authorized") is True,"ACTIVATION_ROLLBACK_RECEIPT_INVALID")
        with self.n["locks"]():
            props=self.properties(SERVICES[0],False)
            control=json.loads(self.p["read"](MANAGER/"production-control-state.json",0,0o600))
            # Interrupted resume or an actual failed service/native breaker is
            # the only automatic authority to restore the already approved pause.
            interrupted=not os.path.lexists(self.directory/"activation.json")
            need(interrupted or props.get("ActiveState")=="failed"
                 or control.get("circuit_breaker",{}).get("state")=="open","NO_FAILED_ACTIVATION_EVIDENCE")
            need(snapshot(PAUSE) in (None,self.before[PAUSE]),"PAUSE_FOREIGN_IMAGE")
            if snapshot(PAUSE) is None:
                replace_exact(PAUSE,None,self.before[PAUSE],self.p["rename_noreplace"])
            if not os.path.lexists(self.directory/"activation-rollback.json"):
                self.n["write"](self.directory/"activation-rollback.json",canon({
                    "status":"original_pause_restored","scope_sha256":sha,"at":stamp(),
                    "reason":"interrupted_or_failed_live_acceptance","production_authority":False}),0o400)
            if props.get("ActiveState")=="failed" and props.get("MainPID","0") in ("","0"):
                self.systemctl(["reset-failed",SERVICES[0]])
        self.native_revalidation()
        self.verify_preserved_pause_and_controls()
        print("ENGINEERING_ACTIVATION_PAUSE_ROLLBACK_VERIFIED")




def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--candidate", required=True)
    choice=cli.add_mutually_exclusive_group()
    choice.add_argument("--apply", action="store_true")
    choice.add_argument("--recover",action="store_true")
    choice.add_argument("--resume",action="store_true")
    choice.add_argument("--verify-activation",action="store_true")
    choice.add_argument("--restore-failed-activation",action="store_true")
    cli.add_argument("--scope-sha")
    a = cli.parse_args()
    n,p = native()
    code = source_review(a.candidate,p,recovery=a.recover or a.resume or a.verify_activation or a.restore_failed_activation)
    adapter = NativeAdapter(a.candidate,n,p,code)
    if a.verify_activation:
        if not adapter.verify_activation():
            raise SystemExit(2)
        return
    if a.restore_failed_activation:
        adapter.restore_failed_activation_pause()
        return
    if a.recover:
        adapter.recover()
        print("ENGINEERING_MANAGER_EXACT_ROLLBACK_VERIFIED")
        return
    if a.resume:
        adapter.resume_verified_cutover()
        print("ENGINEERING_MANAGER_RESUMED_PENDING_SCHEDULED_ACCEPTANCE")
        return
    with n["locks"]():
        plan,_,_ = adapter.inspect()
    sha = adapter.t["verify_plan"](plan)
    if not a.apply:
        print(json.dumps({"status":"exact_native_manager_migration_preflight_passed","scope_sha256":sha,
                          "scope":plan},sort_keys=True))
        return
    need(a.scope_sha == sha,"EXACT_REVIEWED_SCOPE_REQUIRED")
    adapter.plan = plan
    adapter.actor = n["owner"](plan)
    try:
        adapter.t["migrate"](adapter,plan,sha)
    finally:
        adapter.release_lock()
    print("ENGINEERING_MANAGER_CUTOVER_VERIFIED_PAUSED",flush=True)
    adapter.resume_verified_cutover()
    print("ENGINEERING_MANAGER_RESUMED_PENDING_SCHEDULED_ACCEPTANCE")


if __name__ == "__main__":
    try: main()
    except Exception as exc: raise SystemExit("DENIED:"+type(exc).__name__+":"+str(exc)[:500])
