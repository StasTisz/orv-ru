"""Translation contracts and result value objects for Stage 4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import GlossaryEntry
from orv_ru.domain.validation import ValidationReport


@dataclass(frozen=True)
class TranslationResult:
    """Outcome of translating and validating a single chapter."""

    chapter: Chapter
    validation: ValidationReport
    glossary_report: ValidationReport
    chunks_processed: int
    attempts: int


class LLMClient(Protocol):
    """Minimal provider-agnostic interface for text generation."""

    def generate(self, system_prompt: str, user_prompt: str) -> str: ...


class ChapterTranslator(Protocol):
    """Translates a source `Chapter` while preserving structural invariants."""

    def translate(
        self,
        chapter: Chapter,
        glossary: tuple[GlossaryEntry, ...],
        *,
        rules: dict[str, str] | None = None,
    ) -> TranslationResult: ...
