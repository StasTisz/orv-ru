import json

import pytest

from orv_ru.domain.blocks import CoverBlock, ParagraphBlock, QuoteBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import GlossaryEntry, StoryMetadata
from orv_ru.parsing.validator import StructuralValidator
from orv_ru.translation import (
    ChapterChunker,
    ChapterTranslationPipeline,
    GlossaryChecker,
    PromptBuilder,
    TranslationValidationError,
    extract_json_object,
)


class ScriptedLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("ScriptedLLMClient ran out of scripted responses.")
        return self._responses.pop(0)


def _story() -> StoryMetadata:
    return StoryMetadata(
        slug="cont",
        title="Побочная история",
        original_title="ORV Sequel",
        author="Sing Shong",
        language="ru",
        status="Онгоинг",
    )


def test_extract_json_object_handles_fences() -> None:
    data = extract_json_object('```json\n{"a": 1}\n```')
    assert data == {"a": 1}


def test_pipeline_multi_chunk_self_healing_retry_and_sliding_context() -> None:
    src = Chapter(
        number=553,
        title="553 Prologue",
        blocks=(
            CoverBlock("cover.jpg", ""),
            ParagraphBlock("Kim Dokja smiled."),
            QuoteBlock("「Quote」<br>— Author"),
        ),
    )
    glossary = (
        GlossaryEntry(
            source="Kim Dokja",
            target="Ким Докча",
            category="characters",
        ),
    )

    # Chunk 0 response (wrapped in ```json fence)
    chunk0_ok = '```json\n' + json.dumps(
        {
            "title": "553 Пролог",
            "items": [{"block_index": 1, "lines": ["Ким Докча улыбнулся."]}],
        },
        ensure_ascii=False,
    ) + "\n```"

    # Chunk 1 attempt 1: drops <br> -> triggers automatic retry with diagnostics
    chunk1_bad = json.dumps(
        {"items": [{"block_index": 2, "lines": ["「Цитата」 — Автор"]}]},
        ensure_ascii=False,
    )
    # Chunk 1 attempt 2: fixes <br>
    chunk1_ok = json.dumps(
        {"items": [{"block_index": 2, "lines": ["「Цитата」<br>— Автор"]}]},
        ensure_ascii=False,
    )

    client = ScriptedLLMClient([chunk0_ok, chunk1_bad, chunk1_ok])
    pipeline = ChapterTranslationPipeline(
        llm_client=client,
        validator=StructuralValidator(),
        glossary_checker=GlossaryChecker(),
        prompt_builder=PromptBuilder(_story()),
        chunker=ChapterChunker(max_chars=25, max_items=1, context_lines=2),
        max_retries=2,
    )

    res = pipeline.translate(src, glossary)
    assert res.chunks_processed == 2
    assert res.attempts == 3
    assert res.validation.is_valid
    assert res.glossary_report.is_valid
    assert res.chapter.title == "553 Пролог"
    assert res.chapter.blocks[0] == CoverBlock("cover.jpg", "")
    # Verify sliding context from chunk 0 was injected into chunk 1 prompt
    assert "Ким Докча улыбнулся." in client.calls[1][1]
    # Verify retry prompt contained the <br> diagnostic
    assert "<br>" in client.calls[2][1]


def test_pipeline_raises_validation_error_after_exhausting_retries() -> None:
    src = Chapter(number=553, title="553", blocks=(ParagraphBlock("Hello"),))
    bad_resp = json.dumps({"title": "553", "items": []})
    client = ScriptedLLMClient([bad_resp, bad_resp])
    pipeline = ChapterTranslationPipeline(
        llm_client=client,
        validator=StructuralValidator(),
        glossary_checker=GlossaryChecker(),
        prompt_builder=PromptBuilder(_story()),
        max_retries=1,
    )

    with pytest.raises(TranslationValidationError):
        pipeline.translate(src, ())
