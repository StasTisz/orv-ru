"""Canonical serializer converting `Chapter` domain objects back to `.txt` markup."""

from __future__ import annotations

from collections.abc import Callable

from orv_ru.domain.blocks import (
    Block,
    BlockKind,
    CoverBlock,
    GenericBoxBlock,
    ImageBlock,
    SingleLineTextBlock,
    SystemWindowBlock,
)
from orv_ru.domain.chapter import Chapter

_SINGLE_LINE_PREFIXES: dict[BlockKind, str] = {
    BlockKind.PARAGRAPH: "",
    BlockKind.SYSTEM_MESSAGE: "<!>",
    BlockKind.CONSTELLATION: "<@>",
    BlockKind.OUTER_GOD: "<#>",
    BlockKind.QUOTE: "<&>",
    BlockKind.NOTICE: "<?>",
    BlockKind.LIST: "<list>",
}


def _serialize_single_line(block: Block) -> list[str]:
    assert isinstance(block, SingleLineTextBlock)
    prefix = _SINGLE_LINE_PREFIXES[block.kind]
    return [f"{prefix}{block.text}"]


def _serialize_window(block: Block) -> list[str]:
    assert isinstance(block, SystemWindowBlock)
    return ["+", *block.lines, "+"]


def _serialize_box(block: Block) -> list[str]:
    assert isinstance(block, GenericBoxBlock)
    return ["++", *block.lines, "++"]


def _serialize_cover(block: Block) -> list[str]:
    assert isinstance(block, CoverBlock)
    return [f"<cover>[{block.filename}][{block.alt}]"]


def _serialize_image(block: Block) -> list[str]:
    assert isinstance(block, ImageBlock)
    return [f"<img>[{block.filename}][{block.alt}]"]


_SERIALIZERS: dict[BlockKind, Callable[[Block], list[str]]] = {
    BlockKind.PARAGRAPH: _serialize_single_line,
    BlockKind.SYSTEM_MESSAGE: _serialize_single_line,
    BlockKind.CONSTELLATION: _serialize_single_line,
    BlockKind.OUTER_GOD: _serialize_single_line,
    BlockKind.QUOTE: _serialize_single_line,
    BlockKind.NOTICE: _serialize_single_line,
    BlockKind.LIST: _serialize_single_line,
    BlockKind.SYSTEM_WINDOW: _serialize_window,
    BlockKind.GENERIC_BOX: _serialize_box,
    BlockKind.COVER: _serialize_cover,
    BlockKind.IMAGE: _serialize_image,
    BlockKind.DIVIDER: lambda _b: ["***"],
    BlockKind.BLANK_LINE: lambda _b: [""],
}


class OrvMarkupSerializer:
    """Stateless serializer implementing `ChapterSerializer` for ORV `.txt` format."""

    def serialize(self, chapter: Chapter) -> str:
        """Serialize a `Chapter` into canonical UTF-8 `.txt` markup."""
        lines: list[str] = [f"<title>{chapter.title}"]
        for block in chapter.blocks:
            handler = _SERIALIZERS.get(block.kind)
            if handler is None:
                raise ValueError(f"Unsupported block kind for serialization: {block.kind}")
            lines.extend(handler(block))
        return "\n".join(lines) + "\n"
