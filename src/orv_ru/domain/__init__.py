"""Pure OOP domain layer (zero I/O or external framework dependencies)."""

from orv_ru.domain.blocks import (
    AssetBlock,
    BlankLineBlock,
    Block,
    BlockKind,
    ConstellationBlock,
    CoverBlock,
    DividerBlock,
    GenericBoxBlock,
    ImageBlock,
    ListBlock,
    MultiLineContainerBlock,
    NoticeBlock,
    OuterGodBlock,
    ParagraphBlock,
    QuoteBlock,
    SingleLineTextBlock,
    SystemMessageBlock,
    SystemWindowBlock,
    count_br_tags,
)
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import GlossaryEntry, StoryMetadata
from orv_ru.domain.validation import Severity, ValidationIssue, ValidationReport

__all__ = [
    "AssetBlock",
    "BlankLineBlock",
    "Block",
    "BlockKind",
    "Chapter",
    "ConstellationBlock",
    "CoverBlock",
    "DividerBlock",
    "GenericBoxBlock",
    "GlossaryEntry",
    "ImageBlock",
    "ListBlock",
    "MultiLineContainerBlock",
    "NoticeBlock",
    "OuterGodBlock",
    "ParagraphBlock",
    "QuoteBlock",
    "Severity",
    "SingleLineTextBlock",
    "StoryMetadata",
    "SystemMessageBlock",
    "SystemWindowBlock",
    "ValidationIssue",
    "ValidationReport",
    "count_br_tags",
]
