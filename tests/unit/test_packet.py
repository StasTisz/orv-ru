import pytest

from orv_ru.domain.blocks import (
    BlankLineBlock,
    CoverBlock,
    DividerBlock,
    GenericBoxBlock,
    ImageBlock,
    ParagraphBlock,
    QuoteBlock,
    SystemWindowBlock,
)
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import GlossaryEntry
from orv_ru.translation import (
    Glossary,
    TranslatedPayload,
    TranslationError,
    apply_payload,
    estimate_packet_tokens,
    extract_packet,
)


def test_extract_packet_excludes_media_and_apply_payload_preserves_structure() -> None:
    src = Chapter(
        number=795,
        title="795 Chapter",
        blocks=(
            CoverBlock("cover.jpg", ""),
            ParagraphBlock("First paragraph."),
            BlankLineBlock(),
            QuoteBlock("「Quote」<br>— Author"),
            SystemWindowBlock(("[Title]", "Line 1")),
            GenericBoxBlock(("Box",)),
            ImageBlock("art.png", "Art"),
            DividerBlock(),
        ),
    )
    glossary = Glossary(
        entries=(GlossaryEntry(source="Author", target="Автор", category="terms"),)
    )

    packet = extract_packet(src, glossary)
    assert [item.block_index for item in packet.items] == [1, 3, 4, 5]
    assert packet.items[1].expected_br_counts == (1,)
    assert len(packet.matched_glossary) == 1

    packet_dict = packet.to_dict()
    assert packet_dict["schema_version"] == 1
    assert len(packet_dict["items"]) == 4

    est = estimate_packet_tokens(packet)
    assert est["source_chars"] > 0
    assert est["estimated_total_tokens"] > est["estimated_input_tokens"]

    payload = TranslatedPayload.from_dict(
        {
            "chapter_number": 795,
            "title": "795 Глава",
            "items": [
                {"block_index": 1, "lines": ["Первый абзац."]},
                {"block_index": 3, "lines": ["「Цитата」<br>— Автор"]},
                {"block_index": 4, "lines": ["[Заголовок]", "Строка 1"]},
                {"block_index": 5, "lines": ["Рамка"]},
            ],
        }
    )
    dst = apply_payload(src, payload)
    assert dst.title == "795 Глава"
    assert dst.blocks[0] == src.blocks[0]
    assert dst.blocks[2] == BlankLineBlock()
    assert dst.blocks[6] == src.blocks[6]
    assert dst.blocks[7] == DividerBlock()
    assert isinstance(dst.blocks[3], QuoteBlock)
    assert dst.blocks[3].text == "「Цитата」<br>— Автор"


def test_apply_payload_rejects_missing_or_non_translatable_indices() -> None:
    src = Chapter(
        number=553,
        title="553",
        blocks=(CoverBlock("c.jpg", ""), ParagraphBlock("Hello")),
    )
    bad_non_translatable = TranslatedPayload.from_dict(
        {
            "chapter_number": 553,
            "title": "553",
            "items": [
                {"block_index": 0, "lines": ["hijack"]},
                {"block_index": 1, "lines": ["Привет"]},
            ],
        }
    )
    with pytest.raises(TranslationError, match="non-translatable"):
        apply_payload(src, bad_non_translatable)

    missing_item = TranslatedPayload.from_dict(
        {"chapter_number": 553, "title": "553", "items": []}
    )
    with pytest.raises(TranslationError, match="Missing translated content"):
        apply_payload(src, missing_item)
