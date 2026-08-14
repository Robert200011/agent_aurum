"""Deterministic final checks for model-proposed memory content."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.memory.contracts import MemoryProposal

_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|密码|api[ _-]?key|secret|token|jwt|验证码|私钥|private[ _-]?key)"
)
_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_IDENTITY_PATTERN = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_REALTIME_FINANCE_PATTERN = re.compile(
    r"(当前|实时|刚刚|今天).{0,12}(余额|流水|持仓市值|股价|行情|预算执行)|"
    r"(余额|流水|持仓市值|股价|行情|预算执行).{0,12}(当前|实时|刚刚|今天)"
)
_QUOTE_LINE_PATTERN = re.compile(r"(?m)^\s*(?:>|“|\"|```)")


@dataclass(frozen=True, slots=True)
class ProposalValidation:
    proposal: MemoryProposal
    accepted: bool
    result: str


def contains_prohibited_memory_input(current_user_message: str) -> bool:
    """Block high-risk secrets before any third-party memory-decision call."""
    return bool(
        _SECRET_PATTERN.search(current_user_message)
        or _CARD_PATTERN.search(current_user_message)
        or _IDENTITY_PATTERN.search(current_user_message)
    )


def validate_memory_proposal(
    proposal: MemoryProposal,
    *,
    current_user_message: str,
) -> ProposalValidation:
    evidence_start = current_user_message.find(proposal.evidence)
    if evidence_start < 0:
        return ProposalValidation(proposal, False, "evidence_not_found")
    line_start = current_user_message.rfind("\n", 0, evidence_start) + 1
    line_end = current_user_message.find("\n", evidence_start)
    if line_end < 0:
        line_end = len(current_user_message)
    evidence_line = current_user_message[line_start:line_end]
    if _QUOTE_LINE_PATTERN.search(evidence_line):
        return ProposalValidation(proposal, False, "quoted_evidence")
    combined = f"{proposal.title}\n{proposal.content}\n{proposal.evidence}"
    if _SECRET_PATTERN.search(combined) or _CARD_PATTERN.search(combined):
        return ProposalValidation(proposal, False, "sensitive_content")
    if _IDENTITY_PATTERN.search(combined):
        return ProposalValidation(proposal, False, "sensitive_content")
    if _REALTIME_FINANCE_PATTERN.search(combined):
        return ProposalValidation(proposal, False, "realtime_finance_fact")
    return ProposalValidation(proposal, True, "accepted")
