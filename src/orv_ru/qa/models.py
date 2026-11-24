"""Value objects and summary DTOs for deterministic Level 1 QA auditing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orv_ru.domain.validation import ValidationReport


def _serialize_qa_report(rep: ValidationReport) -> dict[str, Any]:
    return {
        "chapter_number": rep.chapter_number,
        "is_valid": rep.is_valid,
        "error_count": len(rep.errors),
        "warning_count": len(rep.warnings),
        "issues": [
            {
                "code": issue.code,
                "severity": str(issue.severity),
                "message": issue.message,
                "block_index": issue.block_index,
            }
            for issue in rep.issues
        ],
    }


@dataclass(frozen=True)
class AutoFixChange:
    """Single deterministic typography fix applied to a block or title."""

    block_index: int | None
    rule: str
    before: str
    after: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_index": self.block_index,
            "rule": self.rule,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True)
class SuspectBlock:
    """Compact review unit containing only flagged blocks plus immediate context."""

    chapter_number: int
    block_index: int | None
    kind: str
    source_text: str
    translated_text: str
    prev_context: str
    next_context: str
    issues: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_number": self.chapter_number,
            "block_index": self.block_index,
            "kind": self.kind,
            "source_text": self.source_text,
            "translated_text": self.translated_text,
            "prev_context": self.prev_context,
            "next_context": self.next_context,
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class ChapterAuditReport:
    """Audit result for a single translated chapter, including optional auto-fixes."""

    report: ValidationReport
    fixes_applied: tuple[AutoFixChange, ...] = ()

    @property
    def chapter_number(self) -> int:
        return self.report.chapter_number

    def to_dict(self) -> dict[str, Any]:
        data = _serialize_qa_report(self.report)
        data["fixes_count"] = len(self.fixes_applied)
        data["fixes"] = [f.to_dict() for f in self.fixes_applied]
        return data


@dataclass(frozen=True)
class AuditSummary:
    """Aggregated deterministic QA results across selected chapters."""

    story_slug: str
    checked_chapters: int
    error_count: int
    warning_count: int
    fixes_count: int
    is_valid: bool
    chapters: tuple[ChapterAuditReport, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "story_slug": self.story_slug,
            "checked_chapters": self.checked_chapters,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "fixes_count": self.fixes_count,
            "is_valid": self.is_valid,
            "chapters": [ch.to_dict() for ch in self.chapters],
        }
