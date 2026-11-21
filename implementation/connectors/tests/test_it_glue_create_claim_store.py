"""Durable IT Glue create-claim tests: no automatic duplicate POST on retry."""
import os
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest

from connectors.it_glue.create_claim_store import SQLiteItGlueCreationClaimStore

K = "a" * 64
V = "b" * 64


def test_claim_survives_reopen_and_marks_verified(tmp_path):
    path = tmp_path / "claims.sqlite3"
    a = SQLiteItGlueCreationClaimStore(path)
    assert a.claim_once(key=K, payload_sha256=V) is True
    assert a.status(key=K) == "claimed"
    assert SQLiteItGlueCreationClaimStore(path).claim_once(
        key=K, payload_sha256=V) is False
    a.mark_verified(key=K, payload_sha256=V)
    assert SQLiteItGlueCreationClaimStore(path).status(key=K) == "verified"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert SQLiteItGlueCreationClaimStore(path).claim_once(
        key=K, payload_sha256="c" * 64) is False


def test_concurrent_exact_claim_only_one_winner(tmp_path):
    path = tmp_path / "claims.sqlite3"
    def claim(_):
        return SQLiteItGlueCreationClaimStore(path).claim_once(
            key=K, payload_sha256=V)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(claim, range(6)))
    assert results.count(True) == 1
    assert results.count(False) == 5


def test_claim_checks_digest_and_preexisting_file_permissions(tmp_path):
    store = SQLiteItGlueCreationClaimStore(tmp_path / "claims.sqlite3")
    with pytest.raises(ValueError, match="DIGEST"):
        store.claim_once(key="not-a-digest", payload_sha256=V)
    store.path.write_bytes(b"")
    os.chmod(store.path, 0o644)
    with pytest.raises(PermissionError, match="PERMISSIONS"):
        store.claim_once(key=K, payload_sha256=V)


def test_claim_rejects_symlinks(tmp_path):
    actual = tmp_path / "target"
    actual.write_bytes(b"")
    link = tmp_path / "claim.sqlite3"
    link.symlink_to(actual)
    store = SQLiteItGlueCreationClaimStore(link)
    with pytest.raises(PermissionError, match="SYMLINK"):
        store.claim_once(key=K, payload_sha256=V)


def test_claim_cannot_mark_wrong_payload_as_verified(tmp_path):
    store = SQLiteItGlueCreationClaimStore(tmp_path / "claims.sqlite3")
    assert store.claim_once(key=K, payload_sha256=V)
    with pytest.raises(PermissionError, match="VERIFICATION_MISMATCH"):
        store.mark_verified(key=K, payload_sha256="c" * 64)
    assert store.status(key=K) == "claimed"
