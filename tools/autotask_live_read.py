#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_SOURCE = REPOSITORY_ROOT / "implementation" / "cap-001" / "src"

if str(CAPABILITY_SOURCE) not in sys.path:
    sys.path.insert(0, str(CAPABILITY_SOURCE))

from jason_cap_001.autotask_live_read_command import main


if __name__ == "__main__":
    raise SystemExit(main())
