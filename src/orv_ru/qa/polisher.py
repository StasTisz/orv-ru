"""Batch suspects polisher allowing a strong LLM to fix ONLY flagged blocks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from orv_ru.domain.blocks import Block, MultiLineContainerBlock, SingleLineTextBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.parsing.validator import StructuralValidator
from orv_ru.ports.repository import ChapterReader, ChapterRepository
from orv_ru.ports.translator import LLMClient
from orv_ru.translation.clients import extract_json_object
from orv_ru.translation.glossary import Glossary
from orv_ru.translation.glossary_checker import GlossaryChecker

_POLISH_SYSTEM_PROMPT = """Ты — литературный редактор русского перевода веб-новеллы «Точка зрения всеведущего читателя» (ORV).
Тебе передаётся компактный список ТОЛЬКО подозрительных блоков с контекстом и замечаниями авто-аудита.
Твоя задача:
1. Исправить проблему в `translated_text` (или вернуть его без изменений, если замечание ложное).
2. Сохранять точное число тегов `<br>` и канонический стиль ORV (`«...»`, `— `, `[Навык]`, `「...」`, `【...】`).
3. Отвечать ТОЛЬКО валидным JSON формата:
{"fixes": [{"chapter_number": 553, "block_index": 10, "lines": ["исправленный текст"]}]}
"""


@dataclass(frozen=True)
class PolishResult:
    """Summary of applying LLM polish fixes across flagged suspect blocks."""

    suspects_reviewed: int
    blocks_updated: int
    blocks_rejected: int
    chapters_saved: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suspects_reviewed": self.suspects_reviewed,
            "blocks_updated": self.blocks_updated,
            "blocks_rejected": self.blocks_rejected,
            "chapters_saved": list(self.chapters_saved),
        }


class SuspectsPolisher:
    """Sends only flagged suspect blocks in small batches to an `LLMClient`."""

    def __init__(
        self,
        llm_client: LLMClient,
        validator: StructuralValidator,
        glossary_checker: GlossaryChecker,
        *,
        batch_size: int = 10,
    ) -> None:
        self._llm = llm_client
        self._validator = validator
        self._glossary_checker = glossary_checker
        self._batch_size = batch_size

    def polish_payload(
        self,
        *,
        suspects_data: dict[str, Any],
        source_repo: ChapterReader,
        translated_repo: ChapterRepository,
        glossary: Glossary,
        dry_run: bool = False,
    ) -> PolishResult:
        """Polish all `suspects` entries in `suspects_data` and persist valid updates."""
        raw_suspects = suspects_data.get("suspects", [])
        if not isinstance(raw_suspects, list) or not raw_suspects:
            return PolishResult(0, 0, 0, ())

        # Skip title suspects (block_index is None) unless needed; polish block-level entries.
        items = [s for s in raw_suspects if isinstance(s, dict) and s.get("block_index") is not None]
        if not items:
            return PolishResult(0, 0, 0, ())

        updates_by_chapter: dict[int, dict[int, tuple[str, ...]]] = {}
        for start in range(0, len(items), self._batch_size):
            batch = items[start : start + self._batch_size]
            user_prompt = json.dumps({"suspects": batch}, ensure_ascii=False, indent=2)
            raw_resp = self._llm.generate(_POLISH_SYSTEM_PROMPT, user_prompt)
            parsed = extract_json_object(raw_resp)
            for fix in parsed.get("fixes", []):
                if not isinstance(fix, dict):
                    continue
                ch_num = fix.get("chapter_number")
                b_idx = fix.get("block_index")
                lines = fix.get("lines")
                if (
                    isinstance(ch_num, int)
                    and isinstance(b_idx, int)
                    and isinstance(lines, list)
                    and all(isinstance(x, str) for x in lines)
                ):
                    updates_by_chapter.setdefault(ch_num, {})[b_idx] = tuple(lines)

        blocks_updated = 0
        blocks_rejected = 0
        chapters_saved: list[int] = []

        for ch_num, block_map in sorted(updates_by_chapter.items()):
            src = source_repo.load(ch_num)
            dst = translated_repo.load(ch_num)
            new_blocks = list(dst.blocks)
            changed_this_chapter = 0

            for b_idx, new_lines in block_map.items():
                if not (0 <= b_idx < len(new_blocks)):
                    blocks_rejected += 1
                    continue
                cur_block = new_blocks[b_idx]
                if not cur_block.is_translatable:
                    blocks_rejected += 1
                    continue

                candidate: Block
                if isinstance(cur_block, SingleLineTextBlock):
                    if len(new_lines) != 1 or not new_lines[0].strip():
                        blocks_rejected += 1
                        continue
                    candidate = cur_block.with_text(new_lines[0])
                elif isinstance(cur_block, MultiLineContainerBlock):
                    if len(new_lines) != len(cur_block.lines):
                        blocks_rejected += 1
                        continue
                    candidate = cur_block.with_lines(new_lines)
                else:
                    blocks_rejected += 1
                    continue

                if candidate.structural_signature() != src.blocks[b_idx].structural_signature():
                    blocks_rejected += 1
                    continue

                if candidate.plain_text() != cur_block.plain_text():
                    new_blocks[b_idx] = candidate
                    changed_this_chapter += 1

            if changed_this_chapter == 0:
                continue

            updated_chapter: Chapter = dst.with_translated_content(
                title=dst.title, blocks=tuple(new_blocks)
            )
            st_rep = self._validator.validate_translation(src, updated_chapter)
            gl_rep = self._glossary_checker.check(src, updated_chapter, glossary)
            if not st_rep.is_valid or gl_rep.has_errors:
                blocks_rejected += changed_this_chapter
                continue

            blocks_updated += changed_this_chapter
            if not dry_run:
                translated_repo.save(updated_chapter)
                chapters_saved.append(ch_num)

        return PolishResult(
            suspects_reviewed=len(items),
            blocks_updated=blocks_updated,
            blocks_rejected=blocks_rejected,
            chapters_saved=tuple(chapters_saved),
        )
