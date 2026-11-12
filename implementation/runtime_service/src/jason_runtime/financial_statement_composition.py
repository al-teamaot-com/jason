"""Compose the owner-approved daily AOT financial statement organizer."""
from __future__ import annotations

from pathlib import Path

from .financial_statement_maintenance import FinancialStatementMaintenance, SQLiteFinancialStatementState
from .microsoft_sharepoint_write import build_microsoft_sharepoint_runtime


def build_financial_statement_maintenance(*, enabled: bool, boundary_db: Path,
                                          openbao_url: str, role_id_path: Path,
                                          secret_id_path: Path, transport,
                                          state_db: Path, tenant_id: str,
                                          drive_id: str, root_path: str,
                                          timezone_name: str = "America/New_York",
                                          run_hour: int = 5, audit=None):
    if not enabled:
        return None
    if audit is None or not callable(getattr(audit, "append", None)):
        raise ValueError("financial statement canonical audit sink required")
    runtime = build_microsoft_sharepoint_runtime(
        boundary_db=boundary_db, openbao_url=openbao_url,
        role_id_path=role_id_path, secret_id_path=secret_id_path,
        transport=transport,
    )
    return FinancialStatementMaintenance(
        client=runtime.files,
        state=SQLiteFinancialStatementState(state_db),
        tenant_id=tenant_id,
        drive_id=drive_id,
        root_path=root_path,
        timezone_name=timezone_name,
        run_hour=run_hour,
        audit=audit,
    )
