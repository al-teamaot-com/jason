#!/usr/bin/env python3
"""Root entrypoint for typed, exact objective operations; no shell interface."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import secrets

TRUSTED = Path("/usr/local/lib/jason/owner-objective/trusted")
ENTRY = TRUSTED / "tools/owner_objective_root_worker.py"
CONFIG = Path("/etc/jason-owner-release/owner-objective.json")
SPOOL = Path("/var/lib/jason/owner-objective-inbox")
PRIVATE = Path("/var/lib/jason-owner-release/objectives")
_ID = re.compile(r"[0-9a-f]{64}\Z")


def root_read(path: Path, mode=0o444, maximum=2000000) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        m, link = os.fstat(stream.fileno()), path.lstat()
        if (not stat.S_ISREG(m.st_mode) or stat.S_ISLNK(link.st_mode)
                or (m.st_dev, m.st_ino) != (link.st_dev, link.st_ino)
                or m.st_uid != 0 or m.st_gid != 0 or m.st_nlink != 1
                or stat.S_IMODE(m.st_mode) != mode or not 0 < m.st_size <= maximum):
            raise PermissionError("OBJECTIVE_ROOT_FILE_IDENTITY")
        raw = stream.read(maximum + 1)
    if len(raw) != m.st_size:
        raise PermissionError("OBJECTIVE_ROOT_FILE_CHANGED")
    return raw


def load_verified(path: Path, name: str, expected: str):
    raw = root_read(path)
    if sha256(raw).hexdigest() != expected:
        raise PermissionError("OBJECTIVE_TRUSTED_CODE_CHANGED")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def active_owner(config, tenant, oid):
    if tenant != config["tenant_id"] or oid != config["owner_oid"]:
        return None
    binding = sqlite3.connect("file:" + config["bindings_db"] + "?mode=ro", uri=True, timeout=2)
    try:
        row = binding.execute(
            "SELECT jason_identity_id,client_id,status FROM microsoft_identity_bindings "
            "WHERE microsoft_tenant_id=? AND microsoft_object_id=?", (tenant, oid)).fetchone()
    finally:
        binding.close()
    expected = config["owner_identity_id"]
    if row != (expected, None, "active"):
        return None
    authority = sqlite3.connect("file:" + config["authority_db"] + "?mode=ro", uri=True, timeout=2)
    try:
        row = authority.execute("SELECT payload FROM identities WHERE identity_id=?", (expected,)).fetchone()
        service = authority.execute("SELECT payload FROM identities WHERE identity_id=?",
                                    (config["requester_identity_id"],)).fetchone()
        required = config["required_grants_sha256"]
        if not isinstance(required, dict) or len(required) != 6:
            return None
        caps = {"release.documentation.publisher.restore", "release.documentation.publisher.verify",
                "interaction.owner.acceptance.record"}
        needed = {(subject, capability) for subject in (expected, config["requester_identity_id"])
                  for capability in caps}
        found = set()
        for grant_id, digest in required.items():
            record = authority.execute("SELECT payload FROM authority_grants WHERE grant_id=?", (grant_id,)).fetchone()
            if record is None:
                return None
            grant = json.loads(record[0])
            raw = json.dumps(grant, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            if (sha256(raw).hexdigest() != digest or grant.get("status") != "active"
                    or grant.get("organization_id") != "aot" or grant.get("client_id") is not None
                    or grant.get("permission") != "execute"
                    or grant.get("effective_from") is not None or grant.get("effective_until") is not None):
                return None
            found.add((grant.get("subject_id"), grant.get("capability")))
        if found != needed:
            return None
    finally:
        authority.close()
    if row is None:
        return None
    identity = json.loads(row[0])
    if service is None:
        return None
    requester = json.loads(service[0])
    if (requester.get("identity_id") != config["requester_identity_id"]
            or requester.get("identity_type") != "service"
            or requester.get("organization_id") != "aot" or requester.get("status") != "active"):
        return None
    if (identity.get("identity_id") != expected or identity.get("organization_id") != "aot"
            or identity.get("identity_type") not in ("human", "person")
            or identity.get("status") != "active"):
        return None
    return expected


def runtime(config):
    from tools.pmv4_teams_objective_admission import canonical, plan_digest
    from tools.pmv4_teams_objective_store import RootObjectiveStore
    from tools.pmv4_objective_documentation import DocumentationObjectiveActions
    from tools import owner_objective_source_verifier
    files = config["files_sha256"]
    for name, expected in files.items():
        if sha256(root_read(TRUSTED / name)).hexdigest() != expected:
            raise PermissionError("OBJECTIVE_INSTALLED_CODE_CLOSURE_CHANGED")
    original_path = TRUSTED / "tools/documentation_publisher_install.py"
    raw = root_read(original_path)
    if sha256(raw).hexdigest() != "31af4fcfa40e6e976c10dc2bef8709f32e542358f89929b232dc18b8295f027a":
        raise PermissionError("OBJECTIVE_REVIEWED_NATIVE_PRIMITIVES_CHANGED")
    original = {"__name__": "objective_existing_native_primitives", "__file__": str(original_path)}
    exec(compile(raw, str(original_path), "exec"), original)
    native, namespace = original["primitives"]()
    native["objective_host_transaction"] = namespace["locks"]
    signed_path = "implementation/connectors/openclaw/src/jason_openclaw/signed_transport.py"
    signed = load_verified(TRUSTED / signed_path, "objective_existing_signed_transport", files[signed_path])
    from cryptography.hazmat.primitives.serialization import load_pem_public_key, Encoding, PublicFormat
    public = {}
    for row in config["gateway_keys"]:
        raw = root_read(Path(row["public_key_path"]))
        fingerprint = sha256(load_pem_public_key(raw).public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo)).hexdigest()
        if fingerprint != row["sha256_fingerprint"] or row["key_id"] in public:
            raise PermissionError("OBJECTIVE_GATEWAY_PUBLIC_KEY_CHANGED")
        public[row["key_id"]] = raw
    if not 1 <= len(public) <= 4:
        raise PermissionError("OBJECTIVE_GATEWAY_KEY_SET_REQUIRED")
    machines = {row["key_id"]: row["machine_identity"] for row in config["gateway_keys"]}
    authenticator = signed.Ed25519TransportAuthenticator(public, machines)
    policy = json.loads(root_read(Path(config["policy_path"])))
    store = RootObjectiveStore()
    native_manifest = json.loads(root_read(Path(config["documentation_manifest"])))
    policy_digest = plan_digest(policy)
    if policy_digest != config["policy_digest"]:
        raise PermissionError("OBJECTIVE_POLICY_CHANGED")
    actions = DocumentationObjectiveActions(
        manifest=native_manifest, native=native,
        verify_source=lambda candidate: owner_objective_source_verifier.verify(config, candidate),
        receipt_directory=PRIVATE / "native-receipts")
    ports = dict(authenticator=authenticator,
        allowed_machine_identities=frozenset(machines.values()),
        policy_digest=policy_digest, allowed_components=frozenset({"documentation-publisher"}),
        current_owner_identity=lambda tenant, oid: active_owner(config, tenant, oid))
    return store, actions, ports, native, canonical


def process(message: dict, config: dict, context) -> dict:
    store, actions, ports, native, canonical = context
    op = message.get("operation")
    if op in ("readback", "status"):
        observation = message.get("observation_id")
        if not isinstance(observation, str) or not re.fullmatch(r"[0-9a-f]{32}", observation):
            raise PermissionError("OBJECTIVE_READBACK_OBSERVATION_ID")
        message = {k: v for k, v in message.items() if k != "observation_id"}
    if message.get("schema_version") != "1.0":
        raise PermissionError("OBJECTIVE_REQUEST_SCHEMA")
    now = datetime.now(timezone.utc)
    approval_id = message.get("approval_id")
    if op == "stage" and set(message) == {"schema_version", "operation", "approval_id", "material"}:
        # Every Root argument must equal the separately prepared native manifest;
        # a valid-looking arbitrary hash or caller projection cannot stage a card.
        def preflight(candidate):
            steps = candidate["material"]["requests"]
            if ([step.get("capability_name") for step in steps] != [
                    "release.documentation.publisher.restore", "release.documentation.publisher.verify"]
                    or candidate["approval_id"] != config["campaign_approval_id"]):
                return False
            for step in steps:
                if step["arguments"] != actions.manifest["step_arguments"]:
                    return False
            return actions.preflight()
        staged = store.stage(approval_id=approval_id, material=message["material"], at=now,
            policy_digest=ports["policy_digest"], allowed_components=ports["allowed_components"],
            allowed_requesters=frozenset({config["requester_identity_id"]}),
            native_preflight=preflight)
        return {k: staged[k] for k in ("approval_id", "plan_fingerprint", "card_instance_challenge")}
    if op == "deliver" and set(message) == {"schema_version", "operation", "approval_id"}:
        from tools.owner_objective_teams_delivery import send
        if (approval_id != config["campaign_approval_id"]
                or active_owner(config, config["tenant_id"], config["owner_oid"]) != config["owner_identity_id"]
                or actions.preflight() is not True):
            raise PermissionError("OBJECTIVE_DELIVERY_LIVE_PREFLIGHT")
        provider_id = store.deliver(approval_id=approval_id, at=now,
            policy_digest=ports["policy_digest"], allowed_components=ports["allowed_components"],
            native_delivery=lambda enrolled: send(enrolled, config, native))
        return {"approval_id": approval_id, "provider_message_id": provider_id}
    if op == "delivery" and set(message) == {"schema_version", "operation", "approval_id", "provider_message_id"}:
        enrolled = store._enrollment(store._plan(approval_id))
        if enrolled["provider_message_id"] != message["provider_message_id"]:
            raise PermissionError("OBJECTIVE_ROOT_DELIVERY_NOT_CONFIRMED")
        return {"approval_id": approval_id, "delivery_recorded": True}
    if op in ("execute", "readback") and set(message) == {
            "schema_version", "operation", "approval_id", "step_index", "signed_envelope"}:
        index = message["step_index"]
        if type(index) is not int or not 0 <= index < 12:
            raise PermissionError("OBJECTIVE_ROOT_STEP_INDEX")
        existing_claim = store._plan(approval_id) / ("claim-" + str(index) + ".json")
        after_restore = index > 0 or existing_claim.exists()
        claim = store.claim(approval_id=approval_id, step_index=index,
            signed_envelope=message["signed_envelope"], at=now, verify_ports=ports,
            native_preflight=lambda enrolled, step: (
                step["arguments"] == actions.manifest["step_arguments"]
                and actions.preflight(after_restore=after_restore)),
            readback_only=op == "readback")
        if op == "execute" and not claim["already_verified"]:
            actions.execute(claim)
        return store.complete_from_native_readback(
            approval_id=approval_id, step_index=index, native_readback=actions.readback)
    if op == "status" and set(message) == {"schema_version", "operation", "approval_id"}:
        return store.status(approval_id=approval_id)
    raise PermissionError("OBJECTIVE_UNREGISTERED_ROOT_OPERATION")


def once():
    if os.geteuid() != 0 or sys.flags.isolated != 1 or Path(__file__).resolve() != ENTRY:
        raise PermissionError("OBJECTIVE_ISOLATED_INSTALLED_ROOT_REQUIRED")
    config = json.loads(root_read(CONFIG, 0o600))
    if config.get("schema_version") != "1.0" or config.get("enabled") is not True:
        raise PermissionError("OBJECTIVE_ROOT_POLICY_NOT_ACTIVE")
    # Imports are allowed only from this separately reviewed Root-owned bundle.
    sys.path.insert(0, str(TRUSTED))
    context = runtime(config)
    drain_one(config, context)


def read_at(directory_fd, name, *, uid, mode, maximum):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, "rb") as stream:
        meta = os.fstat(stream.fileno())
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != uid or meta.st_gid != uid
                or meta.st_nlink != 1 or stat.S_IMODE(meta.st_mode) != mode
                or not 0 < meta.st_size <= maximum):
            raise PermissionError("OBJECTIVE_SPOOL_FILE_IDENTITY")
        raw = stream.read(maximum + 1)
    if len(raw) != meta.st_size:
        raise PermissionError("OBJECTIVE_SPOOL_FILE_CHANGED")
    return raw


def drain_one(config, context, *, spool=SPOOL, private=PRIVATE,
              request_uid=1000, result_uid=0):
    """One bounded packet; production once() supplies fixed paths and identities."""
    import fcntl
    lock = os.open(private / "worker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        meta = os.fstat(lock)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
                or meta.st_uid != result_uid or stat.S_IMODE(meta.st_mode) != 0o600):
            raise PermissionError("OBJECTIVE_WORKER_LOCK_IDENTITY")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        handles = {}
        try:
            for name, uid, mode in (("requests", request_uid, 0o700), ("results", result_uid, 0o755),
                                    ("processed", result_uid, 0o700)):
                fd = os.open(spool / name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                meta = os.fstat(fd)
                if meta.st_uid != uid or meta.st_gid != uid or stat.S_IMODE(meta.st_mode) != mode:
                    os.close(fd)
                    raise PermissionError("OBJECTIVE_ROOT_SPOOL_DIRECTORY_IDENTITY")
                handles[name] = fd
            requests, results, processed = (handles[n] for n in ("requests", "results", "processed"))
            files = sorted(os.listdir(requests))
            if len(files) > 128:
                raise PermissionError("OBJECTIVE_ROOT_QUEUE_OVER_LIMIT")
            for name in files:
                identifier = name.removesuffix(".json")
                if name != identifier + ".json" or not _ID.fullmatch(identifier):
                    raise PermissionError("OBJECTIVE_ROOT_REQUEST_ID")
                raw = read_at(requests, name, uid=request_uid, mode=0o600, maximum=196608)
                if sha256(raw).hexdigest() != identifier:
                    raise PermissionError("OBJECTIVE_ROOT_REQUEST_CHANGED")
                try:
                    prior = json.loads(read_at(results, name, uid=result_uid, mode=0o444, maximum=196608))
                except FileNotFoundError:
                    prior = None
                if prior is not None:
                    if (not isinstance(prior, dict) or prior.get("request_id") != identifier
                            or prior.get("status") not in ("succeeded", "denied")):
                        raise PermissionError("OBJECTIVE_ROOT_PRIOR_RESULT_IDENTITY")
                else:
                    message = None
                    try:
                        message = json.loads(raw)
                        if not isinstance(message, dict):
                            raise PermissionError("OBJECTIVE_REQUEST_OBJECT_REQUIRED")
                        result = process(message, config, context)
                        record = {"request_id": identifier, "status": "succeeded", "result": result}
                    except Exception as exc:
                        raw_reason = str(exc).split(":", 1)[0]
                        reason = (raw_reason if re.fullmatch(r"[A-Z][A-Z0-9_]{2,120}", raw_reason)
                                  else type(exc).__name__)
                        claimed = False
                        if (isinstance(message, dict) and message.get("operation") in ("execute", "readback")
                                and type(message.get("step_index")) is int
                                and 0 <= message["step_index"] < 12):
                            try:
                                plan = context[0]._plan(message.get("approval_id"))
                                claimed = (plan / ("claim-" + str(message["step_index"]) + ".json")).exists()
                            except (PermissionError, OSError):
                                pass
                        record = {"request_id": identifier, "status": "denied", "reason_code": reason,
                                  "execution_state": "indeterminate" if claimed else "not_started"}
                    put_at(results, name, context[4](record), 0o444)
                try:
                    put_at(processed, name, raw, 0o400)
                except FileExistsError:
                    if read_at(processed, name, uid=result_uid, mode=0o400, maximum=196608) != raw:
                        raise PermissionError("OBJECTIVE_ROOT_ARCHIVE_CHANGED")
                os.unlink(name, dir_fd=requests)
                os.fsync(requests)
                print(json.dumps({"request_id": identifier, "status": "processed"}))
                return True
            return False
        finally:
            for fd in handles.values():
                os.close(fd)
    finally:
        os.close(lock)


def put_at(directory_fd, name, raw, mode):
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError("immutable Root result already exists")
    temporary = ".objective-" + secrets.token_hex(16)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 mode, dir_fd=directory_fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        # This Root-owned directory has exactly one writer under worker.lock.
        # Publish completed bytes atomically; readers never see a partial result.
        os.rename(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        try: os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError: pass


if __name__ == "__main__":
    try:
        once()
    except Exception as exc:
        raise SystemExit("DENIED:OBJECTIVE_ROOT:" + type(exc).__name__)
