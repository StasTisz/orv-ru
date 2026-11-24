"""Story-level metadata and glossary entry value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoryMetadata:
    """Descriptive metadata for a story collection."""

    slug: str
    title: str
    original_title: str
    author: str
    language: str
    status: str


@dataclass(frozen=True)
class GlossaryEntry:
    """Single canonical term mapping used during translation."""

    source: str
    target: str
    category: str
    notes: str = ""
    aliases: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
