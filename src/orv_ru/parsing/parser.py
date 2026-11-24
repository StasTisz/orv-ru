"""Table-driven parser turning raw `.txt` chapter markup into a `Chapter` object."""

from __future__ import annotations

import re
from collections.abc import Callable

from orv_ru.domain.blocks import (
    BlankLineBlock,
    Block,
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
from orv_ru.parsing.exceptions import MarkupParseError

_COVER_RE = re.compile(r"^<cover>\[([^\]]*)\]\[([^\]]*)\]\s*$")
_IMAGE_RE = re.compile(r"^<img>\[([^\]]*)\]\[([^\]]*)\]\s*$")

_SINGLE_LINE_BUILDERS: tuple[tuple[str, Callable[[str], Block]], ...] = (
    ("<!>", SystemMessageBlock),
    ("<@>", ConstellationBlock),
    ("<#>", OuterGodBlock),
    ("<&>", QuoteBlock),
    ("<?>", NoticeBlock),
    ("<list>", ListBlock),
)


class OrvMarkupParser:
    """Stateless parser implementing `ChapterParser` for ORV `.txt` format."""

    def parse(
        self,
        chapter_number: int,
        raw_text: str,
        *,
        source_name: str | None = None,
    ) -> Chapter:
        """Parse raw chapter markup text into an immutable `Chapter`."""
        lines = raw_text.splitlines()
        if not lines:
            raise MarkupParseError(
                "Chapter text is empty; expected <title> on line 1",
                line_number=1,
                source_name=source_name,
            )

        first_line = lines[0].lstrip()
        if not first_line.startswith("<title>"):
            raise MarkupParseError(
                "First line must start with <title>",
                line_number=1,
                source_name=source_name,
            )
        title = first_line[len("<title>") :].strip()

        blocks: list[Block] = []
        idx = 1
        while idx < len(lines):
            line = lines[idx]
            stripped = line.lstrip()
            line_num = idx + 1

            if stripped.strip() == "+":
                inner_lines, next_idx = self._consume_delimited(
                    lines, idx + 1, "+", line_num, source_name
                )
                blocks.append(SystemWindowBlock(lines=tuple(inner_lines)))
                idx = next_idx
                continue

            if stripped.strip() == "++":
                inner_lines, next_idx = self._consume_delimited(
                    lines, idx + 1, "++", line_num, source_name
                )
                blocks.append(GenericBoxBlock(lines=tuple(inner_lines)))
                idx = next_idx
                continue

            blocks.append(self._parse_single_line(line, stripped, line_num, source_name))
            idx += 1

        return Chapter(
            number=chapter_number,
            title=title,
            blocks=tuple(blocks),
            source_name=source_name,
        )

    @staticmethod
    def _consume_delimited(
        lines: list[str],
        start_idx: int,
        delimiter: str,
        open_line_num: int,
        source_name: str | None,
    ) -> tuple[list[str], int]:
        collected: list[str] = []
        idx = start_idx
        while idx < len(lines):
            if lines[idx].strip() == delimiter:
                return collected, idx + 1
            collected.append(lines[idx])
            idx += 1
        raise MarkupParseError(
            f"Unclosed '{delimiter}' block",
            line_number=open_line_num,
            source_name=source_name,
        )

    @staticmethod
    def _parse_single_line(
        raw_line: str,
        stripped: str,
        line_num: int,
        source_name: str | None,
    ) -> Block:
        if raw_line == "":
            return BlankLineBlock()
        if raw_line.strip() == "***":
            return DividerBlock()

        if stripped.startswith("<cover>"):
            match = _COVER_RE.match(stripped)
            if not match:
                raise MarkupParseError(
                    "Malformed <cover> tag; expected <cover>[filename][alt]",
                    line_number=line_num,
                    source_name=source_name,
                )
            return CoverBlock(filename=match.group(1), alt=match.group(2))

        if stripped.startswith("<img>"):
            match = _IMAGE_RE.match(stripped)
            if not match:
                raise MarkupParseError(
                    "Malformed <img> tag; expected <img>[filename][alt]",
                    line_number=line_num,
                    source_name=source_name,
                )
            return ImageBlock(filename=match.group(1), alt=match.group(2))

        for prefix, builder in _SINGLE_LINE_BUILDERS:
            if stripped.startswith(prefix):
                return builder(stripped[len(prefix) :])

        return ParagraphBlock(text=raw_line)
