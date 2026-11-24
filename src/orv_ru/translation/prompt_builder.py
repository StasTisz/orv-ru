"""Prompt builder formatting literary ORV instructions, glossary, and retry feedback."""

from __future__ import annotations

import json

from orv_ru.domain.story import GlossaryEntry, StoryMetadata
from orv_ru.translation.chunker import TranslationChunk
from orv_ru.translation.glossary import Glossary


class PromptBuilder:
    """Constructs system, chunk, and self-healing retry prompts."""

    def __init__(self, story: StoryMetadata) -> None:
        self._story = story

    def build_system_prompt(
        self,
        glossary: Glossary,
        matched_entries: tuple[GlossaryEntry, ...],
    ) -> str:
        glossary_block = glossary.format_for_prompt(matched_entries)
        sections = [
            f"Ты — профессиональный литературный переводчик веб-новеллы «{self._story.title}» "
            f"(оригинал: {self._story.original_title}, автор: {self._story.author}) на русский язык.",
            "",
            "Технические требования (СТРОГО):",
            "1. Отвечай ТОЛЬКО валидным JSON-объектом без markdown-обёрток и пояснений.",
            "2. Для каждого элемента входного массива `items` верни объект с тем же `block_index` и массивом `lines`.",
            "3. Количество строк в `lines` каждого элемента ДОЛЖНО точно совпадать с исходным.",
            "4. Сохраняй точное число тегов `<br>` в тех строках, где они присутствуют.",
            "5. Не переводи имена файлов, не добавляй и не удаляй элементы `items`.",
            "6. Сохраняй характерный стиль типов блоков (`system_message`, `constellation`, `outer_god`, `quote`, `system_window`).",
        ]
        if glossary_block:
            sections.extend(["", glossary_block])
        return "\n".join(sections)

    def build_chunk_prompt(
        self,
        chunk: TranslationChunk,
        context_lines: tuple[str, ...],
    ) -> str:
        payload: dict[str, object] = {
            "chunk": f"{chunk.chunk_index + 1}/{chunk.total_chunks}",
            "items": [
                {
                    "block_index": item.block_index,
                    "kind": str(item.kind),
                    "lines": list(item.lines),
                }
                for item in chunk.items
            ],
        }
        if chunk.include_title:
            payload["title"] = chunk.title

        parts: list[str] = []
        if context_lines:
            parts.append("Контекст предыдущего фрагмента (для согласованности тона и местоимений, НЕ переводи повторно):")
            parts.extend(f"> {line}" for line in context_lines)
            parts.append("")

        schema_hint = (
            'Верни JSON формата {"title": "...", "items": [{"block_index": 0, "lines": ["..."]}]}'
            if chunk.include_title
            else 'Верни JSON формата {"items": [{"block_index": 0, "lines": ["..."]}]}'
        )
        parts.append(schema_hint)
        parts.append(json.dumps(payload, ensure_ascii=False, indent=2))
        return "\n".join(parts)

    @staticmethod
    def build_retry_prompt(base_prompt: str, error_messages: list[str]) -> str:
        errors_block = "\n".join(f"- {msg}" for msg in error_messages)
        return (
            f"{base_prompt}\n\n"
            "ВНИМАНИЕ: предыдущий ответ не прошёл автоматическую проверку. Исправь следующие ошибки:\n"
            f"{errors_block}\n"
            "Верни исправленный JSON целиком."
        )
