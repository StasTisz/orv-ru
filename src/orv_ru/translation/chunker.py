"""Chapter chunker splitting large chapters into context-preserving batches."""

from __future__ import annotations

from dataclasses import dataclass

from orv_ru.translation.packet import TranslatableItem, TranslatedItem, TranslationPacket


@dataclass(frozen=True)
class TranslationChunk:
    """Single bounded batch of translatable items sent to an LLM."""

    chunk_index: int
    total_chunks: int
    include_title: bool
    title: str | None
    items: tuple[TranslatableItem, ...]


class ChapterChunker:
    """Splits a `TranslationPacket` into bounded chunks without breaking multi-line blocks."""

    def __init__(
        self,
        *,
        max_chars: int = 3500,
        max_items: int = 40,
        context_lines: int = 3,
    ) -> None:
        if max_chars <= 0 or max_items <= 0 or context_lines < 0:
            raise ValueError("Chunker limits must be positive (context_lines >= 0).")
        self._max_chars = max_chars
        self._max_items = max_items
        self._context_lines = context_lines

    def split(self, packet: TranslationPacket) -> list[TranslationChunk]:
        """Split `packet` into ordered `TranslationChunk` batches."""
        if not packet.items:
            return [
                TranslationChunk(
                    chunk_index=0,
                    total_chunks=1,
                    include_title=True,
                    title=packet.title,
                    items=(),
                )
            ]

        groups: list[list[TranslatableItem]] = []
        current_group: list[TranslatableItem] = []
        current_chars = 0

        for item in packet.items:
            item_chars = item.char_count()
            would_exceed_chars = current_group and (current_chars + item_chars > self._max_chars)
            would_exceed_items = len(current_group) >= self._max_items
            if would_exceed_chars or would_exceed_items:
                groups.append(current_group)
                current_group = []
                current_chars = 0

            current_group.append(item)
            current_chars += item_chars

        if current_group:
            groups.append(current_group)

        total = len(groups)
        return [
            TranslationChunk(
                chunk_index=idx,
                total_chunks=total,
                include_title=(idx == 0),
                title=packet.title if idx == 0 else None,
                items=tuple(group),
            )
            for idx, group in enumerate(groups)
        ]

    def extract_context(self, translated_items: list[TranslatedItem]) -> tuple[str, ...]:
        """Return up to `context_lines` recent non-empty lines for sliding context."""
        if self._context_lines == 0:
            return ()
        lines: list[str] = []
        for item in translated_items:
            for line in item.lines:
                cleaned = line.strip()
                if cleaned:
                    lines.append(cleaned)
        return tuple(lines[-self._context_lines :])
