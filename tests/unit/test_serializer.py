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
from orv_ru.domain.chapter import Chapter
from orv_ru.parsing.parser import OrvMarkupParser
from orv_ru.parsing.serializer import OrvMarkupSerializer


def test_serializer_canonical_round_trip() -> None:
    chapter = Chapter(
        number=795,
        title="795 Глава",
        blocks=(
            CoverBlock("Cover Part 7 - 795.jpg", ""),
            ParagraphBlock("Обычный текст."),
            BlankLineBlock(),
            SystemMessageBlock("[Системное сообщение]"),
            ConstellationBlock("[Голос созвездия]"),
            OuterGodBlock("【Внешний Бог】"),
            QuoteBlock("「Цитата」<br>— Автор"),
            NoticeBlock("Примечание"),
            ListBlock("<li>Пункт</li>"),
            SystemWindowBlock(("[Окно]", "Строка 1")),
            GenericBoxBlock(("Рамка",)),
            ImageBlock("art.png", "Арт"),
            DividerBlock(),
        ),
    )

    serializer = OrvMarkupSerializer()
    parser = OrvMarkupParser()

    text = serializer.serialize(chapter)
    reparsed = parser.parse(795, text)
    assert reparsed == chapter
    assert serializer.serialize(reparsed) == text
