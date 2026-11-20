from hashlib import sha256
import io
import json
import os
from pathlib import PurePosixPath
import tarfile

import pytest

from tools import pmv4_e_dispatch_install as install


@pytest.fixture
def files():
    return {name: name.encode() for name in
            [install.WORKER_SOURCE, *install.CONTROLS.values()]}


def archive(files, invalid=None):
    output = io.BytesIO()
    prefix = PurePosixPath(install.PREFIX)
    directories = {prefix}
    for name in files:
        directories.update(parent for parent in (prefix / name).parents
                           if parent.as_posix().startswith(install.PREFIX))
    with tarfile.open(fileobj=output, mode="w") as tar:
        for name in sorted(directories):
            item = tarfile.TarInfo(str(name))
            item.type = tarfile.DIRTYPE
            item.mode = 0o555
            tar.addfile(item)
        for name, raw in files.items():
            item = tarfile.TarInfo(str(prefix / name))
            item.mode = 0o444
            item.size = len(raw)
            tar.addfile(item, io.BytesIO(raw))
        if invalid:
            tar.addfile(invalid)
    return output.getvalue()


def test_archive_is_exact(files):
    assert install.decode_archive(
        archive(files), {name: sha256(data).hexdigest() for name, data in files.items()}
    ) == files


@pytest.mark.parametrize("bad", ["../escape", "tools/link", "tools/extra"])
def test_archive_rejects_traversal_links_and_unreviewed_content(files, bad):
    item = tarfile.TarInfo(install.PREFIX + "/" + bad)
    item.type = tarfile.SYMTYPE if bad.endswith("link") else tarfile.REGTYPE
    item.linkname = "/etc/example"
    item.mode = 0o444
    with pytest.raises(install.Denied, match="ARCHIVE_"):
        install.decode_archive(
            archive(files, item), {name: sha256(data).hexdigest() for name, data in files.items()}
        )


@pytest.fixture
def isolated(tmp_path, monkeypatch, files):
    if os.geteuid() != 0:
        pytest.skip("sealed-directory swaps require the disposable UID0 runner")
    base = tmp_path / "bootstrap"
    base.mkdir()
    trust = base / "trusted"
    install.stage_tree(trust, {"tools/old.py": b"old"})
    worker = tmp_path / "worker.py"
    worker.write_bytes(b"old worker")
    worker.chmod(0o755)
    policy = tmp_path / "policy.json"
    records = tmp_path / "authority" / "records"
    monkeypatch.setattr(install, "BASE", base)
    monkeypatch.setattr(install, "TRUST", trust)
    monkeypatch.setattr(install, "WORKER", worker)
    monkeypatch.setattr(install, "WORKER_BEFORE", install.digest(worker.read_bytes()))
    monkeypatch.setattr(install, "POLICY", policy)
    monkeypatch.setattr(install, "RECORDS", records)
    monkeypatch.setattr(install, "protected", lambda: None)
    previous = install.tree(trust)
    data = {"candidate_sha": "7" * 40}
    receipt = {"scope": {"trust_before_sha256": previous}, "owner_object_id": "fixture-owner"}
    return files, data, receipt, previous, base


def test_install_and_reversible_readback(isolated):
    files, policy, receipt, previous, base = isolated
    install.install(files, policy, receipt, previous)
    assert install.WORKER.read_bytes() == files[install.WORKER_SOURCE]
    assert json.loads(install.POLICY.read_bytes()) == policy
    assert install.tree(install.TRUST) != previous
    assert install.RECORDS.is_dir()
    install.rollback(files, policy, receipt["scope"])
    assert install.WORKER.read_bytes() == b"old worker"
    assert install.tree(install.TRUST) == previous
    assert not install.RECORDS.parent.exists()
    assert not install.POLICY.exists()
    assert len(list(base.glob("*/rolled-back.json"))) == 1


def test_failed_postcheck_restores_before_images(isolated, monkeypatch):
    files, policy, receipt, previous, base = isolated

    def gate():
        if install.POLICY.exists():
            raise install.Denied("SIMULATED_POSTCHECK_DENIAL")

    monkeypatch.setattr(install, "protected", gate)
    with pytest.raises(install.Denied, match="POSTCHECK"):
        install.install(files, policy, receipt, previous)
    assert install.tree(install.TRUST) == previous
    assert install.WORKER.read_bytes() == b"old worker"
    assert not install.POLICY.exists()
    assert len(list(base.glob("*/rolled-back.json"))) == 1


def test_rollback_denies_a_dispatched_approval(isolated):
    files, policy, receipt, previous, _ = isolated
    install.install(files, policy, receipt, previous)
    (install.RECORDS / "existing.json").write_text("{}")
    with pytest.raises(install.Denied, match="APPROVAL_ALREADY_DISPATCHED"):
        install.rollback(files, policy, receipt["scope"])
    assert install.WORKER.read_bytes() == files[install.WORKER_SOURCE]
    assert install.POLICY.exists()
