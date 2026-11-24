"""Validation value objects for structural and translation integrity checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """Severity level of a structural validation finding."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    """Single structural or content-integrity issue found in a chapter."""

    code: str
    severity: Severity
    message: str
    block_index: int | None = None


@dataclass(frozen=True)
class ValidationReport:
    """Aggregated validation result for a chapter or source/target pair."""

    chapter_number: int
    issues: tuple[ValidationIssue, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == Severity.WARNING)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def is_valid(self) -> bool:
        return not self.has_errors
