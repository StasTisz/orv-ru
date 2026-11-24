"""Translation exceptions for payload, LLM client, and validation failures."""

from __future__ import annotations

from orv_ru.domain.validation import ValidationReport


class TranslationError(RuntimeError):
    """Base error for translation pipeline failures."""


class LLMClientError(TranslationError):
    """Raised when an LLM backend cannot be initialized or returns unusable output."""


class TranslationValidationError(TranslationError):
    """Raised when translated output violates structural or glossary invariants."""

    def __init__(self, message: str, report: ValidationReport) -> None:
        self.report = report
        super().__init__(message)
