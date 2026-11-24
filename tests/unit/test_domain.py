import pytest

from orv_ru.domain.blocks import (
    BlankLineBlock,
    ConstellationBlock,
    CoverBlock,
    DividerBlock,
    ImageBlock,
    NoticeBlock,
    OuterGodBlock,
    ParagraphBlock,
    QuoteBlock,
    SystemMessageBlock,
    SystemWindowBlock,
    count_br_tags,
)
from orv_ru.domain.chapter import Chapter


def test_chapter_requires_positive_number() -> None:
    with pytest.raises(ValueError):
        Chapter(number=0, title="Bad", blocks=())


def test_chapter_word_count_and_reading_time_unicode() -> None:
    chapter = Chapter(
        number=553,
        title="553 Пролог",
        blocks=(
            CoverBlock(filename="cover.jpg", alt=""),
            ParagraphBlock("Привет мир — 1,864 раза!<br>Ещё два слова."),
            SystemMessageBlock("[Навык активирован!]"),
            NoticeBlock("Примечание переводчика не должно учитываться в словах."),
            ImageBlock(filename="art.png", alt="Иллюстрация"),
            DividerBlock(),
            BlankLineBlock(),
        ),
    )

    # Paragraph: Привет, мир, 1864, раза, Ещё, два, слова (7)
    # System: Навык, активирован (2)
    assert chapter.word_count == 9
    assert chapter.reading_time_minutes(words_per_minute=250) == 1
    assert chapter.reading_time_minutes(words_per_minute=4) == 3
    assert chapter.cover == CoverBlock(filename="cover.jpg", alt="")


def test_translatable_blocks_and_immutability() -> None:
    blocks = (
        CoverBlock(filename="cover.jpg", alt=""),
        ParagraphBlock("Hello"),
        DividerBlock(),
        SystemWindowBlock(lines=("[Status]", "Name: Lee Hakhyun")),
        BlankLineBlock(),
        QuoteBlock("「Quote」"),
        ConstellationBlock("[Watch]"),
        OuterGodBlock("【Void】"),
    )
    ch = Chapter(number=554, title="554 Test", blocks=blocks)

    translatable = ch.translatable_blocks()
    assert [idx for idx, _ in translatable] == [1, 3, 5, 6, 7]

    translated = ch.with_translated_content(
        title="554 Тест",
        blocks=blocks,
    )
    assert translated.number == 554
    assert translated.title == "554 Тест"
    assert ch.title == "554 Test"


def test_structural_signatures_and_br_counts() -> None:
    assert count_br_tags("Line1<br>Line2<BR/>Line3") == 2
    assert QuoteBlock("A<br>B").structural_signature() != QuoteBlock("AB").structural_signature()
    assert CoverBlock("a.jpg", "en").structural_signature() == CoverBlock("a.jpg", "ru").structural_signature()
    assert CoverBlock("a.jpg", "en").structural_signature() != CoverBlock("b.jpg", "en").structural_signature()
    assert SystemWindowBlock.is_header_line("[Header]")
    assert SystemWindowBlock.is_header_line("<!>[Scenario]")
    assert not SystemWindowBlock.is_header_line("Time Limit: 24h")


def test_word_count_memoization_preserves_equality_and_hash() -> None:
    ch_a = Chapter(number=553, title="553", blocks=(ParagraphBlock("One two three"),))
    ch_b = Chapter(number=553, title="553", blocks=(ParagraphBlock("One two three"),))

    assert ch_a.word_count == 3
    assert ch_a.word_count == 3
    assert ch_a == ch_b
    assert hash(ch_a) == hash(ch_b)
