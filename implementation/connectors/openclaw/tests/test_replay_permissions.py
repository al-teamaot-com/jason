from __future__ import annotations

import os
from pathlib import Path

from jason_openclaw.runtime import SQLiteReplayStore


def test_replay_database_is_owner_only(tmp_path: Path):
    path = tmp_path / "replay.sqlite3"
    store = SQLiteReplayStore(path)
    assert store.claim("req-1") is True
    mode = os.stat(path).st_mode & 0o777
    assert mode == 0o600
