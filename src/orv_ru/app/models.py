"""Application-layer DTOs and JSON serialization helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from orv_ru.domain.validation import ValidationReport


def serialize_report(rep: ValidationReport) -> dict[str, Any]:
    """Convert a domain `ValidationReport` into a JSON-serializable dict."""
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
class WorkspaceStatus:
    """High-level progress and health summary for the workspace."""

    story_slug: str
    source_count: int
    translated_count: int
    remaining_count: int
    valid_translated_count: int
    invalid_translated_chapters: tuple[int, ...]
    next_untranslated: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationSummary:
    """Aggregated validation results across one or more chapters."""

    mode: str
    checked_chapters: int
    error_count: int
    warning_count: int
    is_valid: bool
    reports: tuple[ValidationReport, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "checked_chapters": self.checked_chapters,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "is_valid": self.is_valid,
            "reports": [serialize_report(rep) for rep in self.reports],
        }
