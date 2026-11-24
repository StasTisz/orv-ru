import re

import pytest

from orv_ru.domain.blocks import (
    BlankLineBlock,
    ConstellationBlock,
    CoverBlock,
    DividerBlock,
    GenericBoxBlock,
    ImageBlock,
    ListBlock,
    NoticeBlock,
    OuterGodBlock,
    ParagraphBlock,
    QuoteBlock,
    SystemMessageBlock,
    SystemWindowBlock,
)
from orv_ru.parsing.exceptions import MarkupParseError
from orv_ru.parsing.parser import OrvMarkupParser


def test_parse_all_supported_tags_and_nebula_names() -> None:
    raw = "\n".join(
        [
            "<title>553 Prologue",
            "<cover>[Cover 553.jpg][Cover Alt]",
            "<img>[art.png][Illustration]",
            "<!>[System active]",
            "<@>[Constellation speaks]",
            "<#>【Outer God whispers】",
            " <&>「Quote with leading space」<br>—Author",
            "<?>Translator note",
            "<list><li>Item</li>",
            "+",
            "[Window Title]",
            "Body line",
            "+",
            "++",
            "Box line 1",
            "Box line 2",
            "++",
            "",
            "***",
            "<Olympus> and <Star Stream> are paragraphs, not tags.",
            "Plain prose.",
        ]
    )

    ch = OrvMarkupParser().parse(553, raw, source_name="553.txt")

    assert ch.number == 553
    assert ch.title == "553 Prologue"
    assert ch.blocks == (
        CoverBlock("Cover 553.jpg", "Cover Alt"),
        ImageBlock("art.png", "Illustration"),
        SystemMessageBlock("[System active]"),
        ConstellationBlock("[Constellation speaks]"),
        OuterGodBlock("【Outer God whispers】"),
        QuoteBlock("「Quote with leading space」<br>—Author"),
        NoticeBlock("Translator note"),
        ListBlock("<li>Item</li>"),
        SystemWindowBlock(("[Window Title]", "Body line")),
        GenericBoxBlock(("Box line 1", "Box line 2")),
        BlankLineBlock(),
        DividerBlock(),
        ParagraphBlock("<Olympus> and <Star Stream> are paragraphs, not tags."),
        ParagraphBlock("Plain prose."),
    )


@pytest.mark.parametrize(
    ("raw", "expected_fragment"),
    [
        ("", "empty"),
        ("No title here\nLine 2", "<title>"),
        ("<title>Ch 1\n+\nUnclosed", "Unclosed '+'"),
        ("<title>Ch 1\n++\nUnclosed", "Unclosed '++'"),
        ("<title>Ch 1\n<cover>[only_one_bracket]", "Malformed <cover>"),
        ("<title>Ch 1\n<img>broken", "Malformed <img>"),
    ],
)
def test_parse_errors(raw: str, expected_fragment: str) -> None:
    with pytest.raises(MarkupParseError, match=re.escape(expected_fragment)):
        OrvMarkupParser().parse(1, raw, source_name="bad.txt")
