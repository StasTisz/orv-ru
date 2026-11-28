"""Resumable chunked chapter translation pipeline with self-healing retries."""

from __future__ import annotations

import re
from typing import Any

from orv_ru.domain.blocks import BlockKind, count_br_tags
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import GlossaryEntry
from orv_ru.domain.validation import Severity, ValidationIssue, ValidationReport
from orv_ru.parsing.validator import StructuralValidator
from orv_ru.ports.translator import LLMClient, TranslationResult
from orv_ru.qa.autofix import TypographyAutoFixer
from orv_ru.translation.chunker import ChapterChunker, TranslationChunk
from orv_ru.translation.clients import extract_json_object
from orv_ru.translation.exceptions import TranslationError, TranslationValidationError
from orv_ru.translation.glossary import Glossary, compile_source_pattern
from orv_ru.translation.glossary_checker import GlossaryChecker, matches_forbidden_term
from orv_ru.translation.packet import (
    TranslatedItem,
    TranslatedPayload,
    apply_payload,
    extract_packet,
)
from orv_ru.translation.prompt_builder import PromptBuilder

_LATIN_LEAK_RE = re.compile(r"\b[a-z]{3,}(?:\s+[a-z]{2,}){3,}\b")
_SKILL_BRACKET_RE = re.compile(r"\[(?!\d+\])([^\[\]\n]+)\]")


class ChapterTranslationPipeline:
    """Orchestrates chunking, prompting, retries, structural QA, and glossary QA."""

    def __init__(
        self,
        llm_client: LLMClient,
        validator: StructuralValidator,
        glossary_checker: GlossaryChecker,
        prompt_builder: PromptBuilder,
        *,
        chunker: ChapterChunker | None = None,
        auto_fixer: TypographyAutoFixer | None = None,
        max_retries: int = 2,
    ) -> None:
        self._llm = llm_client
        self._validator = validator
        self._glossary_checker = glossary_checker
        self._prompt_builder = prompt_builder
        self._chunker = chunker or ChapterChunker()
        self._auto_fixer = auto_fixer or TypographyAutoFixer()
        self._max_retries = max_retries

    def translate(
        self,
        chapter: Chapter,
        glossary: tuple[GlossaryEntry, ...],
        *,
        rules: dict[str, str] | None = None,
    ) -> TranslationResult:
        """Translate `chapter` into Russian, enforcing structural and forbidden-term invariants."""
        glossary_obj = Glossary(entries=glossary, rules=rules or {})
        packet = extract_packet(chapter, glossary_obj)
        chunks = self._chunker.split(packet)
        system_prompt = self._prompt_builder.build_system_prompt(
            glossary_obj, packet.matched_glossary
        )

        translated_title = chapter.title
        collected_items: list[TranslatedItem] = []
        total_attempts = 0
        context_lines: tuple[str, ...] = ()

        for chunk in chunks:
            chunk_title, chunk_items, attempts = self._translate_chunk_with_retries(
                chapter_number=chapter.number,
                chunk=chunk,
                system_prompt=system_prompt,
                context_lines=context_lines,
                matched_glossary=packet.matched_glossary,
            )
            total_attempts += attempts
            if chunk.include_title and chunk_title is not None:
                translated_title = chunk_title
            collected_items.extend(chunk_items)
            context_lines = self._chunker.extract_context(collected_items)

        payload = TranslatedPayload(
            chapter_number=chapter.number,
            title=translated_title,
            items=tuple(collected_items),
        )
        translated_chapter = self._auto_fixer.fix_chapter(
            apply_payload(chapter, payload), chapter
        ).chapter

        structural_report = self._validator.validate_translation(chapter, translated_chapter)
        if not structural_report.is_valid:
            raise TranslationValidationError(
                f"Structural validation failed for chapter {chapter.number}: "
                f"{[i.message for i in structural_report.errors]}",
                structural_report,
            )

        glossary_report = self._glossary_checker.check(chapter, translated_chapter, glossary_obj)
        if glossary_report.has_errors:
            raise TranslationValidationError(
                f"Glossary check failed for chapter {chapter.number}: "
                f"{[i.message for i in glossary_report.errors]}",
                glossary_report,
            )

        return TranslationResult(
            chapter=translated_chapter,
            validation=structural_report,
            glossary_report=glossary_report,
            chunks_processed=len(chunks),
            attempts=total_attempts,
        )

    def _translate_chunk_with_retries(
        self,
        *,
        chapter_number: int,
        chunk: TranslationChunk,
        system_prompt: str,
        context_lines: tuple[str, ...],
        matched_glossary: tuple[GlossaryEntry, ...],
    ) -> tuple[str | None, list[TranslatedItem], int]:
        base_prompt = self._prompt_builder.build_chunk_prompt(chunk, context_lines)
        prompt = base_prompt
        last_errors: list[str] = []

        for attempt in range(1, self._max_retries + 2):
            raw_response = self._llm.generate(system_prompt, prompt)
            try:
                data = extract_json_object(raw_response)
                title, items, errors = self._validate_chunk_dict(
                    data=data,
                    chunk=chunk,
                    matched_glossary=matched_glossary,
                )
            except TranslationError as exc:
                errors = [str(exc)]
                title, items = None, []

            if not errors:
                return title, items, attempt

            last_errors = errors
            prompt = self._prompt_builder.build_retry_prompt(base_prompt, last_errors)

        report = ValidationReport(
            chapter_number=chapter_number,
            issues=tuple(
                ValidationIssue(
                    code="CHUNK_TRANSLATION_FAILED",
                    severity=Severity.ERROR,
                    message=msg,
                )
                for msg in last_errors
            ),
        )
        raise TranslationValidationError(
            f"Chapter {chapter_number} chunk {chunk.chunk_index + 1}/{chunk.total_chunks} "
            f"failed after {self._max_retries + 1} attempts: {last_errors}",
            report,
        )

    @staticmethod
    def _validate_chunk_dict(
        *,
        data: dict[str, Any],
        chunk: TranslationChunk,
        matched_glossary: tuple[GlossaryEntry, ...],
    ) -> tuple[str | None, list[TranslatedItem], list[str]]:
        errors: list[str] = []

        parsed_title: str | None = None
        if chunk.include_title:
            raw_title = data.get("title")
            if not isinstance(raw_title, str) or not raw_title.strip():
                errors.append("Missing or empty required string field 'title'.")
            else:
                parsed_title = raw_title.strip()

        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            errors.append("Missing or non-list field 'items'.")
            return parsed_title, [], errors

        by_index: dict[int, tuple[str, ...]] = {}
        for pos, entry in enumerate(raw_items):
            if not isinstance(entry, dict):
                errors.append(f"items[{pos}] must be a JSON object.")
                continue
            b_idx = entry.get("block_index")
            lines = entry.get("lines")
            if not isinstance(b_idx, int) or isinstance(b_idx, bool):
                errors.append(f"items[{pos}] has non-integer block_index: {b_idx!r}.")
                continue
            if b_idx in by_index:
                errors.append(f"Duplicate block_index {b_idx} in chunk response.")
                continue
            if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
                errors.append(f"block_index {b_idx} must contain a list of strings in 'lines'.")
                continue
            by_index[b_idx] = tuple(lines)

        expected_indices = {item.block_index for item in chunk.items}
        missing = sorted(expected_indices - set(by_index))
        extra = sorted(set(by_index) - expected_indices)
        if missing:
            errors.append(f"Missing block_index(es): {missing}.")
        if extra:
            errors.append(f"Unexpected block_index(es): {extra}.")

        validated_items: list[TranslatedItem] = []
        forbidden_entries = [e for e in matched_glossary if e.forbidden]
        for expected in chunk.items:
            got_lines = by_index.get(expected.block_index)
            if got_lines is None:
                continue
            if len(got_lines) != len(expected.lines):
                errors.append(
                    f"block_index {expected.block_index}: expected {len(expected.lines)} line(s), "
                    f"got {len(got_lines)}."
                )
                continue

            for line_pos, (src_line, dst_line, exp_br) in enumerate(
                zip(expected.lines, got_lines, expected.expected_br_counts, strict=True)
            ):
                if src_line.strip() and not dst_line.strip():
                    errors.append(
                        f"block_index {expected.block_index} line {line_pos} became empty."
                    )
                got_br = count_br_tags(dst_line)
                if got_br != exp_br:
                    errors.append(
                        f"block_index {expected.block_index} line {line_pos}: expected {exp_br} "
                        f"<br> tag(s), got {got_br}."
                    )
                if expected.kind != BlockKind.NOTICE:
                    src_skills = _SKILL_BRACKET_RE.findall(src_line)
                    dst_skills = _SKILL_BRACKET_RE.findall(dst_line)
                    if len(src_skills) != len(dst_skills):
                        errors.append(
                            f"block_index {expected.block_index} line {line_pos}: preserve `[...]` "
                            f"skill/system brackets (expected {len(src_skills)}, got {len(dst_skills)})."
                        )
                    latin_match = _LATIN_LEAK_RE.search(dst_line)
                    if latin_match and not (
                        latin_match.group(0) in src_line and len(latin_match.group(0)) < 28
                    ):
                        errors.append(
                            f"block_index {expected.block_index} line {line_pos}: untranslated "
                            f"English fragment '{latin_match.group(0)}'."
                        )
                    if len(src_line.strip()) >= 60 and len(dst_line.strip()) < len(src_line.strip()) * 0.40:
                        errors.append(
                            f"block_index {expected.block_index} line {line_pos}: translation "
                            "looks truncated compared to source length."
                        )
                for entry in forbidden_entries:
                    if compile_source_pattern(entry.source).search(src_line):
                        for bad in entry.forbidden:
                            if matches_forbidden_term(
                                bad, dst_line, canonical_target=entry.target
                            ):
                                errors.append(
                                    f"block_index {expected.block_index}: forbidden term '{bad}' "
                                    f"used for '{entry.source}' (expected '{entry.target}')."
                                )

            validated_items.append(TranslatedItem(block_index=expected.block_index, lines=got_lines))

        return parsed_title, validated_items, errors
