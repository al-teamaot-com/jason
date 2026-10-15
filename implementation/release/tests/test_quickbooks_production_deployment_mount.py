from __future__ import annotations

from pathlib import Path


DEPLOY_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "jason-runtime"
    / "production-deploy.sh"
)


def test_quickbooks_production_and_sandbox_use_distinct_approle_mounts() -> None:
    """A production deployment must not replace the live sandbox bind destination."""
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'QBO_MOUNT_BASE="/run/jason-secrets/openbao/quickbooks-production"' in source
    assert 'QBO_MOUNT_BASE="/run/jason-secrets/openbao/quickbooks"' in source
    assert '--add-readonly-bind "$QBO_ROLE_HOST:$QBO_MOUNT_BASE/role_id"' in source
    assert '--add-readonly-bind "$QBO_SECRET_HOST:$QBO_MOUNT_BASE/secret_id"' in source

    assert '--set-env "JASON_QUICKBOOKS_OPENBAO_ROLE_ID_PATH=$QBO_MOUNT_BASE/role_id"' in source
    assert '--set-env "JASON_QUICKBOOKS_OPENBAO_SECRET_ID_PATH=$QBO_MOUNT_BASE/secret_id"' in source

    # A hardcoded common mount destination would conflict with the existing
    # sandbox bind when its host AppRole projection differs from production.
    assert '--add-readonly-bind "$QBO_ROLE_HOST:/run/jason-secrets/openbao/quickbooks/role_id"' not in source
    assert '--add-readonly-bind "$QBO_SECRET_HOST:/run/jason-secrets/openbao/quickbooks/secret_id"' not in source
