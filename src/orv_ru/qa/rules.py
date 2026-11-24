"""Deterministic Level 1 quality rules catching typography, bracket, and omission bugs."""

from __future__ import annotations

import re

from orv_ru.domain.blocks import Block, BlockKind, NoticeBlock, ParagraphBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.validation import Severity, ValidationIssue, ValidationReport

_AMERICAN_QUOTE_DOT_RE = re.compile(r"[^\.\u2026]\.\»")
_ASIAN_ELLIPSIS_RE = re.compile(r"\u2026{2,}|(?<![.?!\u2026])\.\.(?!\.)")
_CYRILLIC_STRAIGHT_QUOTE_RE = re.compile(r'"[^"\n]*[а-яёА-ЯЁ][^"\n]*"')
_INLINE_COLON_DASH_RE = re.compile(r":[ \t]+\u2014[ \t]+")
_MID_SENTENCE_DASH_SPEECH_RE = re.compile(r"[а-яё]\.[ \t]+\u2014[ \t]+[А-ЯЁ]")
_LEADING_HYPHEN_RE = re.compile(r"(?:^|<br\s*/?>\s*)-\s+", re.IGNORECASE)
_SPACED_HYPHEN_RE = re.compile(r"\S\s+-\s+\S")
_MULTI_SPACE_RE = re.compile(r" {2,}")

# Skill/title square brackets, ignoring numeric footnote markers like [1], [2].
_SKILL_BRACKET_RE = re.compile(r"\[(?!\d+\])([^\[\]\n]+)\]")
_CORNER_BRACKET_OPEN = "「"
_CORNER_BRACKET_CLOSE = "」"
_LENTICULAR_OPEN = "【"
_LENTICULAR_CLOSE = "】"
_CHEVRON_OPEN = "«"
_CHEVRON_CLOSE = "»"

_ASTERISK_ITALIC_RE = re.compile(r"\*[^*\n]+\*")
_BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)

_DANGLING_DIALOGUE_TAG_RE = re.compile(
    r"^(?:Пробормотал[аи]?|Проворчал[аи]?|Спросил[аи]?|Произн(?:ёс|есл[аи])|"
    r"Крикнул[аи]?|Прошептал[аи]?|Ответил[аи]?|Добавил[аи]?|Воскликнул[аи]?|"
    r"Подумал[аи]?|Вздохнул[аи]?)\s+[А-ЯЁ][а-яё-]+"
)

_CALQUE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "NON_STANDARD_MECHT",
        re.compile(r"(?<![а-яёА-ЯЁ])мечт(?![а-яёА-ЯЁ])", re.IGNORECASE),
        "Ненормативная форма 'мечт' (ожидается 'мечтаний' или переформулировка).",
    ),
    (
        "CALQUE_MOMENT_IN_TIME",
        re.compile(r"\bв\s+(?:этой|этом|этот|данной|данный)\s+(?:точке|момент)\s+времени\b", re.IGNORECASE),
        "Калька 'в этот момент времени' (достаточно 'в этот миг' / 'сейчас').",
    ),
    (
        "CALQUE_TRANSITIVE_EVOLVE",
        re.compile(r"\bэволюционировал[аи]?\s+(?:его|её|их|монстр|существ|питомц)", re.IGNORECASE),
        "Ошибочное переходное употребление 'эволюционировать' (нужно 'помочь эволюционировать').",
    ),
    (
        "REPEATED_ADJACENT_WORD",
        re.compile(r"(?<![а-яё-])([а-яё]{3,})\s+\1(?![а-яё-])", re.IGNORECASE),
        "Случайный повтор одного и того же слова подряд.",
    ),
)

_EN_NEGATION_RE = re.compile(
    r"\b(?:can't|cannot|couldn't|didn't|doesn't|don't|won't|wouldn't|never|nobody|nothing|nowhere)\b",
    re.IGNORECASE,
)
_EN_IDIOMS_EXEMPT_RE = re.compile(
    r"\b(?:couldn't\s+help|couldn't\s+be\s+bothered|couldn't\s+argue)\b",
    re.IGNORECASE,
)
_RU_NEGATION_RE = re.compile(
    r"\b(?:не[а-яё]*|ни[а-яё]*|нет|без|лиш[её]н[а-яё]*|отсутств[а-яё]*|вряд\s+ли|едва\s+ли)\b",
    re.IGNORECASE,
)

# 4+ consecutive lowercase English words usually indicate an untranslated English phrase.
_LATIN_RUN_RE = re.compile(r"\b[a-z]{3,}(?:\s+[a-z]{2,}){3,}\b")

_SENTENCE_SPLIT_RE = re.compile(r"(?<!\.\.)[.!?…]+(?:\s+|$)")


def _strip_br(text: str) -> str:
    return _BR_TAG_RE.sub(" ", text)


def _sentence_count(text: str) -> int:
    cleaned = _strip_br(text).strip()
    if not cleaned:
        return 0
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(cleaned) if p.strip()]
    return len(parts)


def _has_balanced_pair(text: str, open_ch: str, close_ch: str) -> bool:
    depth = 0
    for ch in text:
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


class QualityAuditor:
    """Runs fast, zero-LLM deterministic quality & parity checks on translated chapters."""

    def audit_chapter(
        self,
        translated: Chapter,
        source: Chapter | None = None,
    ) -> ValidationReport:
        """Audit `translated` (and optionally compare each block against `source`)."""
        issues: list[ValidationIssue] = []

        src_title = source.title if source is not None else None
        self._check_text_rules(
            dst_text=translated.title,
            src_text=src_title,
            block_index=None,
            is_notice=False,
            is_container=False,
            issues=issues,
        )

        src_blocks = (
            source.blocks
            if source is not None and len(source.blocks) == len(translated.blocks)
            else None
        )

        for idx, block in enumerate(translated.blocks):
            if not block.is_translatable:
                continue

            src_block: Block | None = None
            if src_blocks is not None and src_blocks[idx].kind == block.kind:
                src_block = src_blocks[idx]

            dst_text = block.plain_text()
            src_text = src_block.plain_text() if src_block is not None else None
            is_notice = isinstance(block, NoticeBlock)
            is_container = block.kind in (BlockKind.SYSTEM_WINDOW, BlockKind.GENERIC_BOX)

            self._check_text_rules(
                dst_text=dst_text,
                src_text=src_text,
                block_index=idx,
                is_notice=is_notice,
                is_container=is_container,
                issues=issues,
            )

            if idx > 0 and isinstance(block, ParagraphBlock):
                prev_block = translated.blocks[idx - 1]
                self._check_dangling_dialogue_tag(prev_block, block, idx, issues)

        return ValidationReport(chapter_number=translated.number, issues=tuple(issues))

    def _check_text_rules(
        self,
        *,
        dst_text: str,
        src_text: str | None,
        block_index: int | None,
        is_notice: bool,
        is_container: bool,
        issues: list[ValidationIssue],
    ) -> None:
        self._check_typography(dst_text, src_text, block_index, is_container, issues)
        self._check_brackets_and_quotes(dst_text, src_text, block_index, issues)
        self._check_calques(dst_text, block_index, issues)
        if not is_notice:
            self._check_latin_leaks(dst_text, src_text, block_index, issues)
        if src_text is not None and not is_notice:
            self._check_source_parity(src_text, dst_text, block_index, issues)

    @staticmethod
    def _check_typography(
        dst_text: str,
        src_text: str | None,
        block_index: int | None,
        is_container: bool,
        issues: list[ValidationIssue],
    ) -> None:
        if _AMERICAN_QUOTE_DOT_RE.search(dst_text):
            issues.append(
                ValidationIssue(
                    code="AMERICAN_QUOTE_PERIOD",
                    severity=Severity.WARNING,
                    message="Обнаружена точка перед закрывающей кавычкой ('.»' вместо '».').",
                    block_index=block_index,
                )
            )
        if _ASIAN_ELLIPSIS_RE.search(dst_text):
            issues.append(
                ValidationIssue(
                    code="ASIAN_OR_BROKEN_ELLIPSIS",
                    severity=Severity.WARNING,
                    message="Обнаружено двойное или двухточечное многоточие ('……' или '..').",
                    block_index=block_index,
                )
            )
        if _CYRILLIC_STRAIGHT_QUOTE_RE.search(dst_text):
            issues.append(
                ValidationIssue(
                    code="STRAIGHT_QUOTES_CYRILLIC",
                    severity=Severity.WARNING,
                    message='Прямые машинописные кавычки "..." вокруг кириллицы (нужны «...»).',
                    block_index=block_index,
                )
            )
        is_dialogue_line = dst_text.lstrip().startswith(("—", "–"))
        has_bad_inline_dash = bool(_INLINE_COLON_DASH_RE.search(dst_text)) or (
            not is_dialogue_line and bool(_MID_SENTENCE_DASH_SPEECH_RE.search(dst_text))
        )
        if has_bad_inline_dash:
            issues.append(
                ValidationIssue(
                    code="INLINE_DASH_SPEECH",
                    severity=Severity.WARNING,
                    message="Тире прямой речи внутри абзаца (внутри абзаца рекомендуется «...»).",
                    block_index=block_index,
                )
            )
        if _LEADING_HYPHEN_RE.search(dst_text) or _SPACED_HYPHEN_RE.search(dst_text):
            issues.append(
                ValidationIssue(
                    code="HYPHEN_INSTEAD_OF_DASH",
                    severity=Severity.WARNING,
                    message="Обычный дефис '-' использован вместо длинного тире '—'.",
                    block_index=block_index,
                )
            )
        if (
            not is_container
            and _MULTI_SPACE_RE.search(_strip_br(dst_text))
            and (src_text is None or not _MULTI_SPACE_RE.search(_strip_br(src_text)))
        ):
            issues.append(
                ValidationIssue(
                    code="EXTRA_WHITESPACE",
                    severity=Severity.WARNING,
                    message="Лишние двойные пробелы в тексте (отсутствуют в оригинале).",
                    block_index=block_index,
                )
            )

    @staticmethod
    def _check_brackets_and_quotes(
        dst_text: str,
        src_text: str | None,
        block_index: int | None,
        issues: list[ValidationIssue],
    ) -> None:
        clean_dst = _strip_br(dst_text)
        clean_src = _strip_br(src_text) if src_text is not None else None
        unbalanced = [
            name
            for name, o, c in (
                ("«»", _CHEVRON_OPEN, _CHEVRON_CLOSE),
                ("「」", _CORNER_BRACKET_OPEN, _CORNER_BRACKET_CLOSE),
                ("【】", _LENTICULAR_OPEN, _LENTICULAR_CLOSE),
                ("[]", "[", "]"),
            )
            if not _has_balanced_pair(clean_dst, o, c)
            and (clean_src is None or _has_balanced_pair(clean_src, o, c))
        ]
        if unbalanced:
            issues.append(
                ValidationIssue(
                    code="UNBALANCED_BRACKETS",
                    severity=Severity.WARNING,
                    message=f"Несбалансированные скобки/кавычки: {', '.join(unbalanced)}.",
                    block_index=block_index,
                )
            )

        if src_text is None:
            return

        src_skills = _SKILL_BRACKET_RE.findall(src_text)
        dst_skills = _SKILL_BRACKET_RE.findall(dst_text)
        if len(src_skills) != len(dst_skills):
            issues.append(
                ValidationIssue(
                    code="INLINE_SKILL_BRACKET_MISMATCH",
                    severity=Severity.WARNING,
                    message=(
                        f"Не совпадает число квадратных скобок `[...]`: "
                        f"в оригинале {len(src_skills)}, в переводе {len(dst_skills)}."
                    ),
                    block_index=block_index,
                )
            )

        for name, token in (("「", "「"), ("【", "【")):
            src_cnt = src_text.count(token)
            dst_cnt = dst_text.count(token)
            if src_cnt != dst_cnt:
                issues.append(
                    ValidationIssue(
                        code="INLINE_CORNER_BRACKET_MISMATCH",
                        severity=Severity.WARNING,
                        message=(
                            f"Не совпадает число скобок `{name}...`: "
                            f"в оригинале {src_cnt}, в переводе {dst_cnt}."
                        ),
                        block_index=block_index,
                    )
                )

        src_italics = len(_ASTERISK_ITALIC_RE.findall(src_text))
        dst_italics = len(_ASTERISK_ITALIC_RE.findall(dst_text))
        if src_italics > 0 and dst_italics == 0:
            issues.append(
                ValidationIssue(
                    code="DROPPED_ITALIC_EMPHASIS",
                    severity=Severity.WARNING,
                    message=f"Утеряно выделение курсивом `*...*` (в оригинале: {src_italics}).",
                    block_index=block_index,
                )
            )

    @staticmethod
    def _check_calques(
        dst_text: str,
        block_index: int | None,
        issues: list[ValidationIssue],
    ) -> None:
        clean = _strip_br(dst_text)
        for code, pattern, msg in _CALQUE_PATTERNS:
            if pattern.search(clean):
                issues.append(
                    ValidationIssue(
                        code=code,
                        severity=Severity.WARNING,
                        message=msg,
                        block_index=block_index,
                    )
                )

    @staticmethod
    def _check_latin_leaks(
        dst_text: str,
        src_text: str | None,
        block_index: int | None,
        issues: list[ValidationIssue],
    ) -> None:
        clean = _strip_br(dst_text)
        match = _LATIN_RUN_RE.search(clean)
        if not match:
            return
        # Ignore if source and target share the exact English snippet (e.g. intentional song lyric/app id).
        snippet = match.group(0)
        if src_text is not None and snippet in src_text and len(snippet) < 28:
            return
        issues.append(
            ValidationIssue(
                code="UNTRANSLATED_LATIN_LEAK",
                severity=Severity.WARNING,
                message=f"Подозрение на непереведённый английский фрагмент: '{snippet}'.",
                block_index=block_index,
            )
        )

    @staticmethod
    def _check_source_parity(
        src_text: str,
        dst_text: str,
        block_index: int | None,
        issues: list[ValidationIssue],
    ) -> None:
        src_clean = _strip_br(src_text).strip()
        dst_clean = _strip_br(dst_text).strip()
        if not src_clean or not dst_clean:
            return

        src_len = len(src_clean)
        dst_len = len(dst_clean)
        if src_len >= 45:
            ratio = dst_len / src_len
            if ratio < 0.50:
                issues.append(
                    ValidationIssue(
                        code="LENGTH_RATIO_TOO_SHORT",
                        severity=Severity.WARNING,
                        message=(
                            f"Перевод подозрительно короче оригинала (ratio={ratio:.2f}, "
                            f"{dst_len}/{src_len} симв.) — возможен пропуск фразы."
                        ),
                        block_index=block_index,
                    )
                )
            elif ratio > 2.30:
                issues.append(
                    ValidationIssue(
                        code="LENGTH_RATIO_TOO_LONG",
                        severity=Severity.WARNING,
                        message=(
                            f"Перевод подозрительно длиннее оригинала (ratio={ratio:.2f}, "
                            f"{dst_len}/{src_len} симв.) — возможна лишняя вставка."
                        ),
                        block_index=block_index,
                    )
                )

        src_sents = _sentence_count(src_clean)
        dst_sents = _sentence_count(dst_clean)
        if src_sents >= 3 and dst_sents == 1 and dst_len < src_len * 0.85:
            issues.append(
                ValidationIssue(
                    code="SENTENCE_DROP_SUSPECTED",
                    severity=Severity.WARNING,
                    message=(
                        f"В оригинале {src_sents} предл., в переводе {dst_sents} — "
                        "проверьте, не выпало ли предложение."
                    ),
                    block_index=block_index,
                )
            )

        if (
            src_len <= 180
            and "?" not in src_clean
            and _EN_NEGATION_RE.search(src_clean)
            and not _EN_IDIOMS_EXEMPT_RE.search(src_clean)
            and not _RU_NEGATION_RE.search(dst_clean)
        ):
            issues.append(
                ValidationIssue(
                    code="NEGATION_POLARITY_MISMATCH",
                    severity=Severity.WARNING,
                    message="В оригинале есть явное отрицание, но в переводе не найдено отрицательных маркеров.",
                    block_index=block_index,
                )
            )

    @staticmethod
    def _check_dangling_dialogue_tag(
        prev_block: Block,
        curr_block: ParagraphBlock,
        block_index: int,
        issues: list[ValidationIssue],
    ) -> None:
        if not prev_block.is_translatable:
            return
        prev_text = prev_block.plain_text().lstrip()
        if not prev_text.startswith(("—", "«", "「")):
            return
        if _DANGLING_DIALOGUE_TAG_RE.match(curr_block.text.lstrip()):
            issues.append(
                ValidationIssue(
                    code="DANGLING_DIALOGUE_TAG",
                    severity=Severity.WARNING,
                    message="Абзац после реплики начинается с оторванного глагола речи (возможная калька с EN).",
                    block_index=block_index,
                )
            )
