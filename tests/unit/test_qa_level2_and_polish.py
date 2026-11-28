import json
from pathlib import Path
from typing import Any

from orv_ru.domain.blocks import ParagraphBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import GlossaryEntry, StoryMetadata
from orv_ru.parsing import OrvMarkupParser, OrvMarkupSerializer, StructuralValidator
from orv_ru.qa import MorphologyAuditor, SuspectsPolisher
from orv_ru.storage import FileSystemChapterRepository
from orv_ru.translation import (
    ChapterTranslationPipeline,
    Glossary,
    GlossaryChecker,
    PromptBuilder,
)


def test_morphology_auditor_catches_names_tautology_agreement_and_register() -> None:
    auditor = MorphologyAuditor()
    assert auditor.is_available()

    ch = Chapter(
        number=3,
        title="Глава 3",
        blocks=(
            ParagraphBlock("У Ю Миа не было выбора."),
            ParagraphBlock("Обманув надежды, путь преградила преграда прямо перед ним."),
            ParagraphBlock("Новая менеджер улыбнулась."),
            ParagraphBlock("— Пожалуйста, расскажите мне всё о вашем плане."),
            ParagraphBlock("— Хорошо, слушай меня внимательно, ты ведь всё понял?"),
        ),
    )

    rep = auditor.audit_chapter(ch)
    by_block = {(i.block_index, i.code) for i in rep.issues}
    assert (0, "UNINFLECTED_DECLINABLE_NAME") in by_block
    assert (1, "SAME_ROOT_TAUTOLOGY") in by_block
    assert (2, "GENDER_AGREEMENT_MISMATCH") in by_block
    assert (4, "DIALOGUE_REGISTER_SHIFT") in by_block


def test_hardened_pipeline_retries_flash_leaks_and_autofixes_typography() -> None:
    class _FlakyFlashLLM:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, system_prompt: str, user_prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                # Attempt 1: Flash model drops [...] brackets and leaves English prose
                return json.dumps(
                    {
                        "title": "Пролог",
                        "items": [
                            {
                                "block_index": 0,
                                "lines": ["Он применил Ауру Меча and left english words right here."],
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            # Attempt 2: Fixed content, minor `.»` typography fixed automatically by pipeline
            return json.dumps(
                {
                    "title": "Пролог",
                    "items": [
                        {
                            "block_index": 0,
                            "lines": ['Он применил [Ауру Меча] и сказал "Привет."'],
                        }
                    ],
                },
                ensure_ascii=False,
            )

    src = Chapter(
        number=1,
        title="Prologue",
        blocks=(ParagraphBlock("He used [Sword Aura] and greeted them."),),
    )
    story = StoryMetadata(
        slug="cont",
        title="ORV",
        original_title="ORV",
        author="Sing Shong",
        language="ru",
        status="Онгоинг",
    )
    llm = _FlakyFlashLLM()
    pipeline = ChapterTranslationPipeline(
        llm_client=llm,
        validator=StructuralValidator(),
        glossary_checker=GlossaryChecker(),
        prompt_builder=PromptBuilder(story),
        max_retries=2,
    )
    res = pipeline.translate(src, glossary=())
    assert llm.calls == 2
    assert res.attempts == 2
    assert res.chapter.blocks[0].plain_text() == "Он применил [Ауру Меча] и сказал «Привет»."


def test_suspects_polisher_updates_valid_blocks_and_rejects_broken_tags(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    tr_dir = tmp_path / "tr"
    src_dir.mkdir()
    tr_dir.mkdir()

    (src_dir / "1.txt").write_text(
        "<title>Ch 1\nLine one.\nLine two<br>continues.\n",
        encoding="utf-8",
    )
    (tr_dir / "1.txt").write_text(
        "<title>Гл 1\nКривая калька.\nВторая строка<br>дальше.\n",
        encoding="utf-8",
    )

    parser = OrvMarkupParser()
    serializer = OrvMarkupSerializer()
    src_repo = FileSystemChapterRepository(src_dir, parser, serializer)
    tr_repo = FileSystemChapterRepository(tr_dir, parser, serializer)

    class _MockPolisherLLM:
        def generate(self, system_prompt: str, user_prompt: str) -> str:
            payload: dict[str, Any] = {
                "fixes": [
                    {"chapter_number": 1, "block_index": 0, "lines": ["Живая русская строка."]},
                    # Block 1 drops <br>, so polisher MUST reject it while keeping block 0
                    {"chapter_number": 1, "block_index": 1, "lines": ["Сломанный перенос."]},
                ]
            }
            return json.dumps(payload, ensure_ascii=False)

    polisher = SuspectsPolisher(
        llm_client=_MockPolisherLLM(),
        validator=StructuralValidator(),
        glossary_checker=GlossaryChecker(),
    )
    suspects_data = {
        "schema_version": 1,
        "story_slug": "cont",
        "suspect_count": 2,
        "suspects": [
            {
                "chapter_number": 1,
                "block_index": 0,
                "kind": "paragraph",
                "source_text": "Line one.",
                "translated_text": "Кривая калька.",
                "prev_context": "",
                "next_context": "",
                "issues": [{"code": "STYLE"}],
            },
            {
                "chapter_number": 1,
                "block_index": 1,
                "kind": "paragraph",
                "source_text": "Line two<br>continues.",
                "translated_text": "Вторая строка<br>дальше.",
                "prev_context": "",
                "next_context": "",
                "issues": [{"code": "STYLE"}],
            },
        ],
    }

    res = polisher.polish_payload(
        suspects_data=suspects_data,
        source_repo=src_repo,
        translated_repo=tr_repo,
        glossary=Glossary(
            entries=(GlossaryEntry(source="Line", target="Строка", category="terms"),)
        ),
    )
    assert res.blocks_updated == 1
    assert res.blocks_rejected == 1
    assert res.chapters_saved == (1,)
    saved = tr_repo.load(1)
    assert saved.blocks[0].plain_text() == "Живая русская строка."
    assert saved.blocks[1].plain_text() == "Вторая строка<br>дальше."
