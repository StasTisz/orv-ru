from orv_ru.domain.blocks import ParagraphBlock, SystemWindowBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import GlossaryEntry, StoryMetadata
from orv_ru.translation import (
    ChapterChunker,
    Glossary,
    PromptBuilder,
    TranslatedItem,
    extract_packet,
)


def test_chunker_splits_without_breaking_multiline_windows() -> None:
    src = Chapter(
        number=553,
        title="553 Title",
        blocks=(
            ParagraphBlock("A" * 40),
            SystemWindowBlock(("[Win]", "B" * 60, "C" * 60)),
            ParagraphBlock("D" * 40),
        ),
    )
    packet = extract_packet(src)
    chunker = ChapterChunker(max_chars=80, max_items=10, context_lines=2)
    chunks = chunker.split(packet)

    # Item 0 (40) -> chunk 0; Item 1 (125 > 80, atomic) -> chunk 1; Item 2 (40) -> chunk 2
    assert len(chunks) == 3
    assert chunks[0].include_title is True
    assert chunks[0].title == "553 Title"
    assert chunks[1].include_title is False
    assert chunks[1].title is None
    assert len(chunks[1].items[0].lines) == 3

    ctx = chunker.extract_context(
        [
            TranslatedItem(0, ("Первая", "")),
            TranslatedItem(1, ("Вторая", "Третья")),
        ]
    )
    assert ctx == ("Вторая", "Третья")


def test_prompt_builder_includes_glossary_context_and_retry_errors() -> None:
    story = StoryMetadata(
        slug="cont",
        title="Побочная история",
        original_title="ORV Sequel",
        author="Sing Shong",
        language="ru",
        status="Онгоинг",
    )
    glossary = Glossary(
        entries=(
            GlossaryEntry(
                source="Oldest Dream",
                target="Древнейшая Мечта",
                category="constellations",
                forbidden=("Самый древний сон",),
            ),
        ),
        rules={"tone": "Preserve original tone"},
    )
    ch = Chapter(number=553, title="553 Title", blocks=(ParagraphBlock("Oldest Dream"),))
    packet = extract_packet(ch, glossary)
    chunks = ChapterChunker().split(packet)

    pb = PromptBuilder(story)
    sys_prompt = pb.build_system_prompt(glossary, packet.matched_glossary)
    assert "Древнейшая Мечта" in sys_prompt
    assert "ЗАПРЕЩЕНО: Самый древний сон" in sys_prompt

    chunk_prompt = pb.build_chunk_prompt(chunks[0], ("Прошлая строка",))
    assert "Прошлая строка" in chunk_prompt
    assert "553 Title" in chunk_prompt

    retry_prompt = pb.build_retry_prompt(chunk_prompt, ["expected 1 <br> tag(s)"])
    assert "expected 1 <br> tag(s)" in retry_prompt
