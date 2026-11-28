"""Deterministic Level 1 Russian quality auditor, typography auto-fixer, and suspects builder."""

from orv_ru.qa.autofix import AutoFixResult, TypographyAutoFixer, fix_line_typography
from orv_ru.qa.models import AuditSummary, AutoFixChange, ChapterAuditReport, SuspectBlock
from orv_ru.qa.morphology import MorphologyAuditor
from orv_ru.qa.polisher import PolishResult, SuspectsPolisher
from orv_ru.qa.rules import QualityAuditor
from orv_ru.qa.suspects import build_suspects_payload, extract_suspect_blocks

__all__ = [
    "AuditSummary",
    "AutoFixChange",
    "AutoFixResult",
    "ChapterAuditReport",
    "MorphologyAuditor",
    "PolishResult",
    "QualityAuditor",
    "SuspectBlock",
    "SuspectsPolisher",
    "TypographyAutoFixer",
    "build_suspects_payload",
    "extract_suspect_blocks",
    "fix_line_typography",
]
