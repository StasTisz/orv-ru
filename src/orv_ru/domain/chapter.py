"""Chapter domain aggregate acting as Information Expert over chapter content."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from orv_ru.domain.blocks import Block, CoverBlock

_TAG_STRIP_RE = re.compile(r"<[^>]*>")
_NUMBER_COMMA_RE = re.compile(r"(\d),(?=\d)")
_WORD_RE = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class Chapter:
    """Immutable domain representation of a single novel chapter."""

    number: int
    title: str
    blocks: tuple[Block, ...]
    source_name: str | None = None
    # Non-comparing cache so repeated site/metadata reads stay O(1) without breaking frozen hash/eq.
    _word_count_cache: int | None = field(
        default=None, init=False, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        if self.number <= 0:
            raise ValueError(f"Chapter number must be positive, got {self.number}")

    @property
    def cover(self) -> CoverBlock | None:
        """Return the chapter's cover block if one is present."""
        for block in self.blocks:
            if isinstance(block, CoverBlock):
                return block
        return None

    @property
    def word_count(self) -> int:
        """Count words across prose/dialogue blocks (Unicode-aware for EN and RU)."""
        if self._word_count_cache is not None:
            return self._word_count_cache

        total = 0
        for block in self.blocks:
            if not block.counts_toward_word_count:
                continue
            text = _TAG_STRIP_RE.sub(" ", block.plain_text())
            text = _NUMBER_COMMA_RE.sub(r"\1", text)
            total += len(_WORD_RE.findall(text))

        object.__setattr__(self, "_word_count_cache", total)
        return total

    def reading_time_minutes(self, words_per_minute: int = 250) -> int:
        """Estimate reading time in minutes (minimum 1 minute)."""
        if words_per_minute <= 0:
            raise ValueError(f"words_per_minute must be positive, got {words_per_minute}")
        return max(1, (self.word_count + words_per_minute - 1) // words_per_minute)

    def translatable_blocks(self) -> tuple[tuple[int, Block], ...]:
        """Return `(index, block)` pairs for blocks that require translation."""
        return tuple((idx, b) for idx, b in enumerate(self.blocks) if b.is_translatable)

    def with_translated_content(self, title: str, blocks: tuple[Block, ...]) -> Chapter:
        """Return a new Chapter instance preserving chapter number and source metadata."""
        return Chapter(
            number=self.number,
            title=title,
            blocks=blocks,
            source_name=self.source_name,
        )
