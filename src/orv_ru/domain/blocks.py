"""Polymorphic block hierarchy representing elements inside a chapter."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import StrEnum

_BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def count_br_tags(text: str) -> int:
    """Return the number of inline `<br>` line-break tags in a text string."""
    return len(_BR_TAG_RE.findall(text))


class BlockKind(StrEnum):
    """Canonical block types supported by the reader and markup engine."""

    PARAGRAPH = "paragraph"
    SYSTEM_MESSAGE = "system_message"
    CONSTELLATION = "constellation"
    OUTER_GOD = "outer_god"
    QUOTE = "quote"
    NOTICE = "notice"
    SYSTEM_WINDOW = "system_window"
    GENERIC_BOX = "generic_box"
    COVER = "cover"
    IMAGE = "image"
    DIVIDER = "divider"
    BLANK_LINE = "blank_line"
    LIST = "list"


class Block(ABC):
    """Abstract base class for every structural block inside a chapter."""

    @property
    @abstractmethod
    def kind(self) -> BlockKind:
        """Semantic type of this block."""

    @property
    @abstractmethod
    def is_translatable(self) -> bool:
        """Whether this block carries natural-language text for translation."""

    @property
    @abstractmethod
    def counts_toward_word_count(self) -> bool:
        """Whether words in this block contribute to chapter word count."""

    @abstractmethod
    def plain_text(self) -> str:
        """Return plain text content for metrics and search indexing."""

    @abstractmethod
    def structural_signature(self) -> tuple[object, ...]:
        """Return immutable structural invariant key used to validate translations."""


@dataclass(frozen=True)
class SingleLineTextBlock(Block, ABC):
    """Shared base for single-line text-bearing blocks."""

    text: str
    _counts_words: bool = True

    @property
    def is_translatable(self) -> bool:
        return True

    @property
    def counts_toward_word_count(self) -> bool:
        return self._counts_words

    def plain_text(self) -> str:
        return self.text

    def with_text(self, text: str) -> SingleLineTextBlock:
        """Return an immutable copy of the same concrete block subclass with updated text."""
        return replace(self, text=text)

    def structural_signature(self) -> tuple[object, ...]:
        return (self.kind, count_br_tags(self.text))


@dataclass(frozen=True)
class ParagraphBlock(SingleLineTextBlock):
    """Standard narration or dialogue line."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.PARAGRAPH


@dataclass(frozen=True)
class SystemMessageBlock(SingleLineTextBlock):
    """Game/scenario system notification (`<!>`)."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.SYSTEM_MESSAGE


@dataclass(frozen=True)
class ConstellationBlock(SingleLineTextBlock):
    """Constellation true-voice speech (`<@>`)."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.CONSTELLATION


@dataclass(frozen=True)
class OuterGodBlock(SingleLineTextBlock):
    """Outer God speech (`<#>`)."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.OUTER_GOD


@dataclass(frozen=True)
class QuoteBlock(SingleLineTextBlock):
    """Quoted passage or internal monologue (`<&>`)."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.QUOTE


@dataclass(frozen=True)
class NoticeBlock(SingleLineTextBlock):
    """Translator or editorial note (`<?>`)."""

    _counts_words: bool = False

    @property
    def kind(self) -> BlockKind:
        return BlockKind.NOTICE


@dataclass(frozen=True)
class ListBlock(SingleLineTextBlock):
    """Unordered list block (`<list>`)."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.LIST


@dataclass(frozen=True)
class MultiLineContainerBlock(Block, ABC):
    """Shared base for multi-line delimited blocks (`+` or `++`)."""

    lines: tuple[str, ...]

    @property
    def is_translatable(self) -> bool:
        return True

    @property
    def counts_toward_word_count(self) -> bool:
        return True

    def plain_text(self) -> str:
        return "\n".join(self.lines)

    def with_lines(self, lines: tuple[str, ...]) -> MultiLineContainerBlock:
        """Return an immutable copy of the same container subclass with updated lines."""
        return replace(self, lines=lines)

    def structural_signature(self) -> tuple[object, ...]:
        br_counts = tuple(count_br_tags(line) for line in self.lines)
        return (self.kind, len(self.lines), br_counts)


@dataclass(frozen=True)
class SystemWindowBlock(MultiLineContainerBlock):
    """Multi-line system window delimited by `+`."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.SYSTEM_WINDOW

    @staticmethod
    def is_header_line(line: str) -> bool:
        """Return True if a window line represents a bracketed header."""
        return line.startswith("[") or line.startswith("<!>[")


@dataclass(frozen=True)
class GenericBoxBlock(MultiLineContainerBlock):
    """Multi-line generic bordered box delimited by `++`."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.GENERIC_BOX


@dataclass(frozen=True)
class AssetBlock(Block, ABC):
    """Shared base for non-prose media reference blocks."""

    filename: str
    alt: str

    @property
    def is_translatable(self) -> bool:
        return False

    @property
    def counts_toward_word_count(self) -> bool:
        return False

    def plain_text(self) -> str:
        return ""

    def structural_signature(self) -> tuple[object, ...]:
        return (self.kind, self.filename)


@dataclass(frozen=True)
class CoverBlock(AssetBlock):
    """Chapter cover image (`<cover>[filename][alt]`)."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.COVER


@dataclass(frozen=True)
class ImageBlock(AssetBlock):
    """Inline chapter illustration (`<img>[filename][alt]`)."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.IMAGE


@dataclass(frozen=True)
class DividerBlock(Block):
    """Horizontal section break (`***`)."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.DIVIDER

    @property
    def is_translatable(self) -> bool:
        return False

    @property
    def counts_toward_word_count(self) -> bool:
        return False

    def plain_text(self) -> str:
        return ""

    def structural_signature(self) -> tuple[object, ...]:
        return (self.kind,)


@dataclass(frozen=True)
class BlankLineBlock(Block):
    """Explicit empty line separating paragraphs."""

    @property
    def kind(self) -> BlockKind:
        return BlockKind.BLANK_LINE

    @property
    def is_translatable(self) -> bool:
        return False

    @property
    def counts_toward_word_count(self) -> bool:
        return False

    def plain_text(self) -> str:
        return ""

    def structural_signature(self) -> tuple[object, ...]:
        return (self.kind,)
