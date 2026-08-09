from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import patch

from tools.provider_secret_kv_write import metadata_path, current_version


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def read(self) -> bytes:
        return self._body


def test_metadata_path_converts_kv_v2_data_path() -> None:
    assert metadata_path(
        "secret/data/connectors/datto-rmm/production/read-only"
    ) == "secret/metadata/connectors/datto-rmm/production/read-only"


def test_current_version_returns_zero_when_secret_does_not_exist() -> None:
    exc = urllib.error.HTTPError(
        url="http://openbao.test/v1/secret/metadata/x",
        code=404,
        msg="not found",
        hdrs=None,
        fp=BytesIO(b'{"errors":[]}'),
    )
    with patch("urllib.request.urlopen", side_effect=exc):
        assert current_version(
            "http://openbao.test:8200",
            "secret/data/connectors/datto-rmm/production/read-only",
            "token",
        ) == 0


def test_current_version_reads_existing_secret_metadata() -> None:
    with patch(
        "urllib.request.urlopen",
        return_value=FakeResponse({"data": {"current_version": 3}}),
    ):
        assert current_version(
            "http://openbao.test:8200",
            "secret/data/connectors/datto-rmm/production/read-only",
            "token",
        ) == 3
