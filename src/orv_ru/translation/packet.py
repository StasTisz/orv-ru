"""Protected Payload extraction and reassembly keeping markup tags untouchable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orv_ru.domain.blocks import (
    Block,
    BlockKind,
    MultiLineContainerBlock,
    SingleLineTextBlock,
    count_br_tags,
)
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import GlossaryEntry
from orv_ru.translation.exceptions import TranslationError
from orv_ru.translation.glossary import Glossary


@dataclass(frozen=True)
class TranslatableItem:
    """Single translatable block extracted with structural guards."""

    block_index: int
    kind: BlockKind
    lines: tuple[str, ...]
    expected_br_counts: tuple[int, ...]

    def char_count(self) -> int:
        return sum(len(line) for line in self.lines)


@dataclass(frozen=True)
class TranslationPacket:
    """Self-contained export packet for external or automated chapter translation."""

    chapter_number: int
    title: str
    items: tuple[TranslatableItem, ...]
    matched_glossary: tuple[GlossaryEntry, ...]
    rules: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "chapter_number": self.chapter_number,
            "title": self.title,
            "instructions": (
                "Переведите `title` и `lines` каждого элемента в `items` на русский язык. "
                "Не меняйте `block_index`, не добавляйте и не удаляйте строки в `lines`, "
                "сохраняйте точное количество тегов <br> внутри каждой строки."
            ),
            "expected_output_format": {
                "chapter_number": self.chapter_number,
                "title": "<переведённый заголовок>",
                "items": [{"block_index": 0, "lines": ["<переведённая строка>"]}],
            },
            "rules": dict(self.rules),
            "glossary": [
                {
                    "source": e.source,
                    "target": e.target,
                    "category": e.category,
                    "notes": e.notes,
                    "aliases": list(e.aliases),
                    "forbidden": list(e.forbidden),
                }
                for e in self.matched_glossary
            ],
            "items": [
                {
                    "block_index": item.block_index,
                    "kind": str(item.kind),
                    "lines": list(item.lines),
                    "expected_br_counts": list(item.expected_br_counts),
                }
                for item in self.items
            ],
        }


@dataclass(frozen=True)
class TranslatedItem:
    """Translated lines mapped back to a specific `block_index`."""

    block_index: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class TranslatedPayload:
    """Validated JSON response payload returned by an LLM or translation agent."""

    chapter_number: int
    title: str
    items: tuple[TranslatedItem, ...]

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        fallback_chapter_number: int | None = None,
    ) -> TranslatedPayload:
        if not isinstance(data, dict):
            raise TranslationError("Translated payload must be a JSON object.")

        raw_num = data.get("chapter_number", fallback_chapter_number)
        if not isinstance(raw_num, int) or isinstance(raw_num, bool) or raw_num <= 0:
            raise TranslationError(f"Invalid or missing chapter_number: {raw_num!r}")

        raw_title = data.get("title")
        if not isinstance(raw_title, str):
            raise TranslationError("Translated payload must include string field 'title'.")

        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            raise TranslationError("Translated payload must include list field 'items'.")

        parsed_items: list[TranslatedItem] = []
        for idx, entry in enumerate(raw_items):
            if not isinstance(entry, dict):
                raise TranslationError(f"Item {idx} in payload must be an object.")
            b_idx = entry.get("block_index")
            lines = entry.get("lines")
            if not isinstance(b_idx, int) or isinstance(b_idx, bool) or b_idx < 0:
                raise TranslationError(f"Item {idx} has invalid block_index: {b_idx!r}")
            if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
                raise TranslationError(
                    f"Item {idx} (block_index={b_idx}) must have string list 'lines'."
                )
            parsed_items.append(TranslatedItem(block_index=b_idx, lines=tuple(lines)))

        return cls(chapter_number=raw_num, title=raw_title, items=tuple(parsed_items))


def extract_packet(chapter: Chapter, glossary: Glossary | None = None) -> TranslationPacket:
    """Extract only translatable blocks from `chapter`, leaving tags/media protected."""
    items: list[TranslatableItem] = []
    for idx, block in chapter.translatable_blocks():
        lines = block.lines if isinstance(block, MultiLineContainerBlock) else (block.plain_text(),)
        br_counts = tuple(count_br_tags(line) for line in lines)
        items.append(
            TranslatableItem(
                block_index=idx,
                kind=block.kind,
                lines=lines,
                expected_br_counts=br_counts,
            )
        )

    active_glossary = glossary or Glossary()
    matched = active_glossary.match_relevant(chapter)
    return TranslationPacket(
        chapter_number=chapter.number,
        title=chapter.title,
        items=tuple(items),
        matched_glossary=matched,
        rules=dict(active_glossary.rules),
    )


def apply_payload(source: Chapter, payload: TranslatedPayload) -> Chapter:
    """Reassemble a translated `Chapter` by applying `payload` onto `source` blocks."""
    by_index: dict[int, tuple[str, ...]] = {}
    for item in payload.items:
        if item.block_index in by_index:
            raise TranslationError(f"Duplicate block_index {item.block_index} in payload.")
        by_index[item.block_index] = item.lines

    translatable_indices = {idx for idx, _ in source.translatable_blocks()}
    unexpected = set(by_index) - translatable_indices
    if unexpected:
        raise TranslationError(
            f"Payload references non-translatable or unknown block_index(es): {sorted(unexpected)}"
        )

    new_blocks: list[Block] = []
    for idx, block in enumerate(source.blocks):
        if not block.is_translatable:
            new_blocks.append(block)
            continue

        if idx not in by_index:
            raise TranslationError(f"Missing translated content for block_index {idx}.")
        lines = by_index[idx]

        if isinstance(block, MultiLineContainerBlock):
            new_blocks.append(block.with_lines(lines))
        elif isinstance(block, SingleLineTextBlock):
            if len(lines) != 1:
                raise TranslationError(
                    f"Single-line block {idx} ({block.kind}) requires exactly 1 line, got {len(lines)}."
                )
            new_blocks.append(block.with_text(lines[0]))
        else:
            raise TranslationError(f"Unsupported translatable block type: {type(block).__name__}")

    return source.with_translated_content(title=payload.title, blocks=tuple(new_blocks))


def estimate_packet_tokens(packet: TranslationPacket) -> dict[str, int]:
    """Estimate character and token budget for translating a chapter packet into Russian."""
    source_chars = len(packet.title) + sum(item.char_count() for item in packet.items)
    glossary_chars = sum(
        len(e.source) + len(e.target) + len(e.notes) for e in packet.matched_glossary
    ) + sum(len(k) + len(v) for k, v in packet.rules.items())

    text_tokens = max(1, round(source_chars / 3.8))
    glossary_tokens = round(glossary_chars / 3.5)
    input_tokens = text_tokens + glossary_tokens + 350
    output_tokens_ru = round(text_tokens * 1.9)
    return {
        "source_chars": source_chars,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens_ru": output_tokens_ru,
        "estimated_total_tokens": input_tokens + output_tokens_ru,
    }
