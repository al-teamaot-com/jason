"""AOT technology lifecycle baseline for deterministic posture evaluation.

Vendor dates are data, not authority. AOT policy decides whether vendor support,
ESU enrollment, or an explicit client exception is acceptable.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import re

@dataclass(frozen=True, slots=True)
class LifecycleResult:
    product: str
    release: str
    state: str
    supported_through: date | None
    rationale: str
    exception_required: bool=False

WINDOWS_BASELINE = {
    # General Windows 10 Home/Pro/Enterprise/Education 22H2. LTSC/LTSB must be
    # identified explicitly and is intentionally not inferred from build 19045.
    ("windows_10","22H2"): date(2025,10,14),
    ("windows_11_home_pro","23H2"): date(2025,11,11),
    ("windows_11_enterprise_education","23H2"): date(2026,11,10),
    ("windows_11_home_pro","24H2"): date(2026,10,13),
    ("windows_11_enterprise_education","24H2"): date(2027,10,12),
    ("windows_11_home_pro","25H2"): date(2027,10,12),
    ("windows_11_enterprise_education","25H2"): date(2028,10,10),
    ("windows_server_2016","1607"): date(2027,1,12),
    ("hyperv_server_2012","2012"): date(2023,10,10),
}
BUILD_RELEASE = {19045:"22H2",22631:"23H2",26100:"24H2",26200:"25H2"}

def evaluate_windows(os_name: str, *, as_of: date, exception_approved: bool=False, esu_confirmed: bool=False) -> LifecycleResult:
    raw=os_name.strip(); low=raw.casefold(); m=re.search(r"10\.0\.(\d+)",raw); build=int(m.group(1)) if m else None
    if "hyperv server 2012" in low:
        key=("hyperv_server_2012","2012"); product="Hyper-V Server 2012"
    elif "windows server 2016" in low:
        key=("windows_server_2016","1607"); product="Windows Server 2016"
    elif "windows 10" in low:
        if "ltsc" in low or "ltsb" in low:
            return LifecycleResult(raw,"unknown","unknown",None,"LTSC/LTSB lifecycle requires exact edition/release evidence.")
        release=BUILD_RELEASE.get(build,"unknown")
        if release=="unknown": return LifecycleResult(raw,release,"unknown",None,"Windows 10 release cannot be established from current evidence.")
        key=("windows_10",release); product="Windows 10"
    elif "windows 11" in low:
        release=BUILD_RELEASE.get(build,"unknown")
        if release=="unknown": return LifecycleResult(raw,release,"unknown",None,"Windows 11 release cannot be established from current evidence.")
        family="windows_11_enterprise_education" if ("enterprise" in low or "education" in low) else "windows_11_home_pro"
        key=(family,release); product="Windows 11"
    else:
        return LifecycleResult(raw,"unknown","unknown",None,"No governed lifecycle rule matches this operating system.")
    end=WINDOWS_BASELINE.get(key)
    if end is None: return LifecycleResult(product,key[1],"unknown",None,"No AOT lifecycle baseline exists for this release.")
    if as_of <= end: return LifecycleResult(product,key[1],"supported",end,"Vendor security-support window is active.")
    if esu_confirmed: return LifecycleResult(product,key[1],"supported_by_exception",end,"Base vendor support ended; authoritative evidence confirms applicable ESU coverage.",True)
    if exception_approved: return LifecycleResult(product,key[1],"accepted_exception",end,"Vendor support ended; an explicit approved AOT/client exception exists.",True)
    return LifecycleResult(product,key[1],"unsupported",end,"Vendor security-support window has ended and no ESU or approved exception is evidenced.",True)
