"""Read-only ticket gap classification must never imply execution approval."""
from pathlib import Path
import ast

SOURCE = Path(__file__).parents[1] / "src/jason_runtime/autonomy_worker_runtime.py"

def test_gaps_are_distinguished_without_playbook_scope_registration():
    source = SOURCE.read_text()
    ast.parse(source)
    assert '"site_outage_correlation_candidate"' in source
    assert '"edr_threat_requires_security_triage"' in source
    assert '"filesystem_corruption_diagnostics_candidate"' in source
    assert '"windows_licensing_diagnostics_candidate"' in source
    assert '"m365_onedrive_diagnostics_candidate"' in source
    assert 'self._unsupported_capability_reason(item.context)' in source
    assert source.index('scope = self._match_scope(item.context)') < source.index('self._unsupported_capability_reason(item.context)')
    assert '"no_applicable_promoted_playbook"' in source
