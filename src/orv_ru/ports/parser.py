"""Parser and serializer contracts for chapter text representations."""

from __future__ import annotations

from typing import Protocol

from orv_ru.domain.chapter import Chapter


class ChapterParser(Protocol):
    """Parses raw chapter markup text into a `Chapter` domain object."""

    def parse(
        self,
        chapter_number: int,
        raw_text: str,
        *,
        source_name: str | None = None,
    ) -> Chapter: ...


class ChapterSerializer(Protocol):
    """Serializes a `Chapter` domain object back to canonical text markup."""

    def serialize(self, chapter: Chapter) -> str: ...
