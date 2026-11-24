"""Compact suspects packet builder for Audit-by-Exception workflows."""

from __future__ import annotations

from typing import Any

from orv_ru.domain.blocks import Block
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.validation import ValidationReport
from orv_ru.qa.models import SuspectBlock


def _context_preview(blocks: tuple[Block, ...], idx: int | None) -> tuple[str, str]:
    if idx is None:
        first = blocks[0].plain_text() if blocks and blocks[0].is_translatable else ""
        return "", first
    prev_text = ""
    for i in range(idx - 1, -1, -1):
        if blocks[i].is_translatable:
            prev_text = blocks[i].plain_text()
            break
    next_text = ""
    for i in range(idx + 1, len(blocks)):
        if blocks[i].is_translatable:
            next_text = blocks[i].plain_text()
            break
    return prev_text, next_text


def extract_suspect_blocks(
    *,
    translated: Chapter,
    report: ValidationReport,
    source: Chapter | None = None,
) -> tuple[SuspectBlock, ...]:
    """Group `report` issues by block and return minimal review units with context."""
    if not report.issues:
        return ()

    grouped: dict[int | None, list[dict[str, Any]]] = {}
    for issue in report.issues:
        payload: dict[str, Any] = {
            "code": issue.code,
            "severity": str(issue.severity),
            "message": issue.message,
            "block_index": issue.block_index,
        }
        grouped.setdefault(issue.block_index, []).append(payload)

    src_blocks = (
        source.blocks
        if source is not None and len(source.blocks) == len(translated.blocks)
        else None
    )

    suspects: list[SuspectBlock] = []
    for block_idx, issue_list in grouped.items():
        if block_idx is None:
            kind = "title"
            dst_text = translated.title
            src_text = source.title if source is not None else ""
        else:
            block = translated.blocks[block_idx]
            kind = str(block.kind)
            dst_text = block.plain_text()
            src_text = src_blocks[block_idx].plain_text() if src_blocks is not None else ""

        prev_ctx, next_ctx = _context_preview(translated.blocks, block_idx)
        suspects.append(
            SuspectBlock(
                chapter_number=translated.number,
                block_index=block_idx,
                kind=kind,
                source_text=src_text,
                translated_text=dst_text,
                prev_context=prev_ctx,
                next_context=next_ctx,
                issues=tuple(issue_list),
            )
        )

    return tuple(suspects)


def build_suspects_payload(
    *,
    story_slug: str,
    chapter_pairs: list[tuple[Chapter, Chapter | None, ValidationReport]],
) -> dict[str, Any]:
    """Assemble a token-minimal JSON packet containing only flagged blocks."""
    all_suspects: list[SuspectBlock] = []
    for translated, source, report in chapter_pairs:
        all_suspects.extend(
            extract_suspect_blocks(translated=translated, report=report, source=source)
        )

    return {
        "schema_version": 1,
        "story_slug": story_slug,
        "suspect_count": len(all_suspects),
        "suspects": [s.to_dict() for s in all_suspects],
    }
