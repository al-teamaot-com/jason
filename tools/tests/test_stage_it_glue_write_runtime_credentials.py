"""Source-only, no-secret IT Glue write AppRole staging contract tests."""
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.stage_it_glue_write_runtime_credentials import (
    _SPECS, _STAGED, build_parser, run,
)


def test_exact_separate_write_staging_paths():
    assert len(_SPECS) == 2
    assert {v.provider for v in _SPECS} == {"it_glue_write"}
    assert {v.credential_name for v in _SPECS} == {"role_id", "secret_id"}
    assert all("write-approle" in str(v.source) for v in _SPECS)
    assert all(v.destination.parent == _STAGED for v in _SPECS)
    assert not any("read-approle" in str(v.source) for v in _SPECS)


def test_default_check_only_is_preflight_without_staging():
    opts = build_parser().parse_args(["--check-only"])
    with (
        patch("tools.stage_it_glue_write_runtime_credentials.preflight_provider_read_runtime_credentials",
              return_value={"status": "credential_staging_preflight_pass"}) as preflight,
        patch("tools.stage_it_glue_write_runtime_credentials.stage_provider_read_runtime_credentials") as stage,
    ):
        data = run(opts)
    assert data["stage_performed"] is False
    assert data["credential_values_disclosed"] is False
    assert preflight.call_args.kwargs["specs"] == _SPECS
    stage.assert_not_called()


def test_staging_requires_explicit_stage_and_bound_source():
    opts = build_parser().parse_args(["--stage"])
    with patch(
        "tools.stage_it_glue_write_runtime_credentials.stage_provider_read_runtime_credentials",
        return_value={"status": "credential_staging_pass"},
    ) as staged:
        data = run(opts)
    assert data["stage_performed"] is True
    assert staged.call_args.kwargs["replace_existing"] is False
    assert staged.call_args.kwargs["runtime_uid"] == 1000
    assert staged.call_args.kwargs["runtime_gid"] == 1000
    assert staged.call_args.kwargs["specs"] == _SPECS


def test_replace_cannot_happen_via_check_only():
    opts = Namespace(check_only=True, stage=False, replace_existing=True)
    with pytest.raises(PermissionError):
        run(opts)


def test_read_only_source_never_used_as_write_fallback():
    for spec in _SPECS:
        assert "itglue-write" in str(spec.source)
        assert "it-glue-write" in str(spec.destination)
        assert "itglue-read" not in str(spec.source)
