"""Deterministic, lossless Russian typography auto-fixer (zero LLM tokens)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from orv_ru.domain.blocks import Block, MultiLineContainerBlock, SingleLineTextBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.qa.models import AutoFixChange

_AMERICAN_QUOTE_DOT_RE = re.compile(r"([^\.\u2026])\.\»")
_ASIAN_DOUBLE_ELLIPSIS_RE = re.compile(r"\u2026{2,}|(?<!\.)\.\.\.(?:\s*\.\.\.)+")
_TWO_DOT_ELLIPSIS_RE = re.compile(r"(?<![.?!\u2026])\.\.(?!\.)")
_CYRILLIC_STRAIGHT_QUOTES_RE = re.compile(r'"([^"\n]*[а-яёА-ЯЁ][^"\n]*)"')
_LEADING_HYPHEN_RE = re.compile(r"(^|<br\s*/?>\s*)-\s+", re.IGNORECASE)
_SPACED_HYPHEN_RE = re.compile(r"(\S)\s+-\s+(\S)")
_MULTI_SPACE_RE = re.compile(r" {2,}")
_BR_SPLIT_RE = re.compile(r"(<br\s*/?>)", re.IGNORECASE)


def _has_intentional_spacing(source_text: str) -> bool:
    """Detect deliberate stylistic multi-spacing (e.g. eerie Outer God staccato)."""
    return bool(_MULTI_SPACE_RE.search(source_text))


def _fix_segment(text: str, *, allow_multi_spaces: bool) -> tuple[str, tuple[str, ...]]:
    """Apply safe deterministic typography normalizations to a single non-tag text chunk."""
    applied: list[str] = []
    cur = text

    updated = _CYRILLIC_STRAIGHT_QUOTES_RE.sub(r"«\1»", cur)
    if updated != cur:
        applied.append("STRAIGHT_QUOTES_TO_CHEVRONS")
        cur = updated

    updated = _AMERICAN_QUOTE_DOT_RE.sub(r"\1».", cur)
    if updated != cur:
        applied.append("AMERICAN_QUOTE_PERIOD")
        cur = updated

    updated = _ASIAN_DOUBLE_ELLIPSIS_RE.sub("…", cur)
    updated = _TWO_DOT_ELLIPSIS_RE.sub("…", updated)
    if updated != cur:
        applied.append("NORMALIZE_ELLIPSIS")
        cur = updated

    updated = _LEADING_HYPHEN_RE.sub(r"\1— ", cur)
    updated = _SPACED_HYPHEN_RE.sub(r"\1 — \2", updated)
    if updated != cur:
        applied.append("HYPHEN_TO_EM_DASH")
        cur = updated

    if not allow_multi_spaces:
        collapsed = _MULTI_SPACE_RE.sub(" ", cur)
        if collapsed != cur:
            applied.append("NORMALIZE_WHITESPACE")
            cur = collapsed

    return cur, tuple(applied)


def fix_line_typography(line: str, *, source_line: str = "") -> tuple[str, tuple[str, ...]]:
    """Normalize typography inside a line while keeping `<br>` tags untouched."""
    allow_multi = _has_intentional_spacing(source_line)
    parts = _BR_SPLIT_RE.split(line)
    rules: list[str] = []
    out: list[str] = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            out.append(part)
            continue
        fixed_part, part_rules = _fix_segment(part, allow_multi_spaces=allow_multi)
        out.append(fixed_part)
        for r in part_rules:
            if r not in rules:
                rules.append(r)

    joined = "".join(out)
    if not allow_multi and source_line and source_line == source_line.strip():
        stripped = joined.strip()
        if stripped != joined:
            joined = stripped
            if "NORMALIZE_WHITESPACE" not in rules:
                rules.append("NORMALIZE_WHITESPACE")

    return joined, tuple(rules)


@dataclass(frozen=True)
class AutoFixResult:
    """Result returned by `TypographyAutoFixer.fix_chapter`."""

    chapter: Chapter
    changes: tuple[AutoFixChange, ...]


class TypographyAutoFixer:
    """Applies safe, deterministic typography cleanups without altering block signatures."""

    def fix_chapter(self, translated: Chapter, source: Chapter | None = None) -> AutoFixResult:
        """Return a cleaned `Chapter` copy plus the exact list of applied changes."""
        changes: list[AutoFixChange] = []

        src_title = source.title if source is not None else ""
        fixed_title, title_rules = fix_line_typography(translated.title, source_line=src_title)
        if fixed_title != translated.title:
            changes.append(
                AutoFixChange(
                    block_index=None,
                    rule=",".join(title_rules),
                    before=translated.title,
                    after=fixed_title,
                )
            )

        src_blocks = source.blocks if source is not None and len(source.blocks) == len(translated.blocks) else None
        new_blocks: list[Block] = []

        for idx, block in enumerate(translated.blocks):
            if not block.is_translatable:
                new_blocks.append(block)
                continue

            src_block = src_blocks[idx] if src_blocks is not None and src_blocks[idx].kind == block.kind else None

            if isinstance(block, SingleLineTextBlock):
                src_line = src_block.plain_text() if isinstance(src_block, SingleLineTextBlock) else ""
                fixed_line, rules = fix_line_typography(block.text, source_line=src_line)
                if fixed_line != block.text:
                    changes.append(
                        AutoFixChange(
                            block_index=idx,
                            rule=",".join(rules),
                            before=block.text,
                            after=fixed_line,
                        )
                    )
                    new_blocks.append(block.with_text(fixed_line))
                else:
                    new_blocks.append(block)
                continue

            if isinstance(block, MultiLineContainerBlock):
                src_lines = (
                    src_block.lines
                    if isinstance(src_block, MultiLineContainerBlock) and len(src_block.lines) == len(block.lines)
                    else ("",) * len(block.lines)
                )
                fixed_lines: list[str] = []
                line_rules: list[str] = []
                changed_any = False
                for line, src_line in zip(block.lines, src_lines, strict=True):
                    fixed_line, rules = fix_line_typography(line, source_line=src_line)
                    fixed_lines.append(fixed_line)
                    if fixed_line != line:
                        changed_any = True
                        for r in rules:
                            if r not in line_rules:
                                line_rules.append(r)

                if changed_any:
                    changes.append(
                        AutoFixChange(
                            block_index=idx,
                            rule=",".join(line_rules),
                            before=block.plain_text(),
                            after="\n".join(fixed_lines),
                        )
                    )
                    new_blocks.append(block.with_lines(tuple(fixed_lines)))
                else:
                    new_blocks.append(block)
                continue

            new_blocks.append(block)

        if not changes:
            return AutoFixResult(chapter=translated, changes=())

        cleaned_chapter = translated.with_translated_content(
            title=fixed_title,
            blocks=tuple(new_blocks),
        )
        return AutoFixResult(chapter=cleaned_chapter, changes=tuple(changes))
