from __future__ import annotations

import json
from pathlib import Path

from jason_cap_001.validation import validate_document


def test_request_fixtures_match_contract() -> None:
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures" / "requests"
    fixtures = sorted(fixture_dir.glob("*.json"))
    assert fixtures, "At least one request fixture is required."

    for fixture in fixtures:
        with fixture.open("r", encoding="utf-8") as handle:
            validate_document("investigation_request", json.load(handle))
