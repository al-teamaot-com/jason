"""Existing native controller supports typed hooks without changing Compose semantics."""
from pathlib import Path
from tools import independent_component_release as native
import pytest


def test_original_compose_observation_and_previous_bundle_unchanged():
    controller = object.__new__(native.ComponentReleaseController)
    assert controller._resource_name({"compose_project": "test-compose"}) == "test-compose"
    base = Path("/tmp/native-test-only")
    assert controller._previous_bundle(base, native.ZERO) is None
    assert controller._previous_bundle(base, "a"*40) == base/("a"*40)


def test_default_recovery_manifest_remains_compose_strict():
    controller = object.__new__(native.ComponentReleaseController)
    with pytest.raises(native.ComponentReleaseDenied):
        controller._validate_recovery_manifest({
            "release_mode": "owner-signed-native-systemd-stage-e",
        })


def test_unmodified_controller_has_no_stage_e_manifest_acceptance():
    controller = object.__new__(native.ComponentReleaseController)
    with pytest.raises((KeyError, native.ComponentReleaseDenied)):
        controller._resource_name({"release_mode": "owner-signed-native-systemd-stage-e"})


def test_default_pointer_denies_missing_prior_for_nonzero_rollback(tmp_path):
    controller = object.__new__(native.ComponentReleaseController)
    controller.production = False
    with pytest.raises(native.ComponentReleaseDenied, match="COMPONENT_RECOVERY_PRIOR_INVALID"):
        controller._restore_recovery_pointer(
            tmp_path, component="demo-component", candidate="b"*40,
            rollback="a"*40, active_sha="b"*40, prior=None,
        )


def test_recovery_pointer_is_not_created_for_noop(tmp_path):
    controller = object.__new__(native.ComponentReleaseController)
    controller.production = False
    controller._restore_recovery_pointer(
        tmp_path, component="demo-component", candidate="b"*40,
        rollback="a"*40, active_sha=None, prior=None,
    )
    assert list(tmp_path.iterdir()) == []


def test_original_signed_controller_hooks_are_overrideable_without_replacement():
    class Typed(native.ComponentReleaseController):
        def _resource_name(self, manifest):
            assert manifest["release_mode"] == "owner-signed-native-systemd-stage-e"
            return "jason-pmv4-e-six-unit-controlplane"

        def _previous_bundle(self, releases, rollback):
            return None

    obj = object.__new__(Typed)
    assert obj._resource_name({"release_mode": "owner-signed-native-systemd-stage-e"}) == "jason-pmv4-e-six-unit-controlplane"
    assert obj._previous_bundle(Path("/tmp/test"), "a"*40) is None
    assert isinstance(obj, native.ComponentReleaseController)
