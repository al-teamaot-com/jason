"""Regression questions for the generic evidence interpreter.

The cases deliberately describe expected support behavior and known-dangerous
substitutions without mapping any human question to a provider field.  They are
portable across providers and fixtures because correctness is evaluated from the
reasoner's verified path choices, not from a question-to-field lookup table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SupportExpectation = Literal["supported", "supported_or_unavailable"]


@dataclass(frozen=True, slots=True)
class EvidenceRegressionCase:
    name: str
    question: str
    expectation: SupportExpectation
    forbidden_path_terms: tuple[str, ...] = ()


WORKSTATION_EVIDENCE_REGRESSIONS = (
    EvidenceRegressionCase(
        name="lan_ip",
        question="What is the LAN IP address of this workstation?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="wan_ip",
        question="What is the WAN or public IP address of this workstation?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="logged_in_user",
        question="Who was the last logged-in user on this workstation?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="windows_version",
        question="What Windows version and release is this workstation running?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="ram",
        question="How much RAM does this workstation have?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="processor",
        question="What processor does this workstation have?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="motherboard",
        question="What motherboard does this workstation have?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="video_card",
        question="What video card or display adapter does this workstation have?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="printers",
        question="What printers are present on this workstation?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="zerotier",
        question="Is ZeroTier installed on this workstation?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="chrome_version",
        question="What version of Google Chrome is installed on this workstation?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="network_adapters",
        question="What network adapters does this workstation have?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="free_disk",
        question="How much free disk space does this workstation have?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="open_alerts",
        question="What open alerts does this workstation have?",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="disk_errors",
        question="Does the evidence show any disk errors for this workstation?",
        expectation="supported_or_unavailable",
    ),
    EvidenceRegressionCase(
        name="broad_workstation_summary",
        question="Tell me everything the evidence establishes about this workstation.",
        expectation="supported",
    ),
    EvidenceRegressionCase(
        name="last_reboot",
        question="Can you tell me when AOT-50107 was last rebooted?",
        expectation="supported_or_unavailable",
        forbidden_path_terms=("lastloggedinuser",),
    ),
    EvidenceRegressionCase(
        name="last_full_virus_scan",
        question="When is the last time that machine ran a full virus scan?",
        expectation="supported_or_unavailable",
    ),
    EvidenceRegressionCase(
        name="bitlocker_recovery_key",
        question="Can you give me the BitLocker unlock code for AOT-50107?",
        expectation="supported_or_unavailable",
        forbidden_path_terms=(
            "resource_selector",
            "selector",
            "hostname_fragment",
        ),
    ),
    EvidenceRegressionCase(
        name="bitlocker_status",
        question="What is the BitLocker status of AOT-50107?",
        expectation="supported_or_unavailable",
    ),
)
