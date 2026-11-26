"""No production JSON registry touched, immutable isolated 19-draft rehearsal."""
from pathlib import Path
import pytest

from tools.legacy_json_isolated_preprod_acceptance import (
    ISOLATED, run,
)


def test_exact_isolated_source_rehearsal_never_activates_or_dispatches():
    result=run()
    assert result["candidate_count"]==19
    assert result["generation"]==19
    assert result["active_json_versions"]==0
    assert result["provider_calls"]==result["provider_writes"]==0
    assert result["production_registry_modified"] is False
    assert result["production_core_modified"] is False
    assert result["live_provider_preproduction_acceptance"] is False
    assert all(row["state"]=="draft" and
               row["live_preprod_accepted"] is False and
               row["governed_action_approved"] is False
               for row in result["versions"])
    assert len({row["fingerprint"] for row in result["versions"]})==19
    assert (ISOLATED/"isolated-preprod-evidence.json").is_file()


def test_other_or_production_output_path_fails_closed_without_write(tmp_path):
    with pytest.raises(ValueError,match="OUTPUT_DIRECTORY_FIXED"):
        run(output_root=tmp_path/"production-json-registry")


def test_repeated_rehearsal_is_idempotent_and_does_not_activate():
    first=run()
    second=run()
    assert first==second
    assert second["generation"]==19
    assert second["active_json_versions"]==0
