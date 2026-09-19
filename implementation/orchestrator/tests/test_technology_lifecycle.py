from datetime import date
from orchestrator.technology_lifecycle import evaluate_windows
NOW=date(2026,9,19)
def test_windows_10_22h2_is_unsupported_without_exception():
 r=evaluate_windows('Microsoft Windows 10 Pro 10.0.19045',as_of=NOW); assert r.state=='unsupported'
def test_windows_11_23h2_pro_is_unsupported_but_enterprise_supported():
 assert evaluate_windows('Microsoft Windows 11 Pro 10.0.22631',as_of=NOW).state=='unsupported'
 assert evaluate_windows('Microsoft Windows 11 Enterprise 10.0.22631',as_of=NOW).state=='supported'
def test_windows_11_24h2_and_25h2_are_supported():
 assert evaluate_windows('Microsoft Windows 11 Pro 10.0.26100',as_of=NOW).state=='supported'
 assert evaluate_windows('Microsoft Windows 11 Pro 10.0.26200',as_of=NOW).state=='supported'
def test_server_2016_is_still_supported_and_hyperv_2012_is_not():
 assert evaluate_windows('Microsoft Windows Server 2016 Standard 10.0.14393',as_of=NOW).state=='supported'
 assert evaluate_windows('Microsoft HyperV Server 2012 6.2.9200',as_of=NOW).state=='unsupported'
def test_esu_or_approved_exception_is_explicit_not_inferred():
 assert evaluate_windows('Microsoft Windows 10 Pro 10.0.19045',as_of=NOW,esu_confirmed=True).state=='supported_by_exception'
 assert evaluate_windows('Microsoft Windows 10 Pro 10.0.19045',as_of=NOW,exception_approved=True).state=='accepted_exception'
def test_ltsc_is_not_inferred_from_build():
 assert evaluate_windows('Microsoft Windows 10 Enterprise LTSC 10.0.19045',as_of=NOW).state=='unknown'
