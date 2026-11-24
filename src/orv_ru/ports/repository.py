"""Segregated repository ports (ISP) for reading and writing chapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from orv_ru.domain.chapter import Chapter


class ChapterReader(Protocol):
    """Read-only access to persisted chapters."""

    def list_chapter_numbers(self) -> list[int]: ...

    def load(self, chapter_number: int) -> Chapter: ...

    def load_all(self) -> list[Chapter]: ...


class ChapterWriter(Protocol):
    """Write-only access for saving chapters."""

    def save(self, chapter: Chapter) -> Path: ...


class ChapterRepository(ChapterReader, ChapterWriter, Protocol):
    """Combined read/write repository contract."""
