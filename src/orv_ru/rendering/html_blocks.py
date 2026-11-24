"""Polymorphic block-to-HTML5 renderer matching 1:1 visual structure."""

from __future__ import annotations

import re
import urllib.parse as urlparse
from collections.abc import Callable

from orv_ru.domain.blocks import (
    Block,
    BlockKind,
    ConstellationBlock,
    CoverBlock,
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
from orv_ru.rendering.escaping import clean_container_line, escape_inline_html, format_ru_words

_QUOTE_OPEN_RE = re.compile(r"\s*「\s*")
_QUOTE_CLOSE_RE = re.compile(r"\s*」\s*")


def _normalize_quotes(text: str) -> str:
    text = _QUOTE_OPEN_RE.sub("「 ", text)
    return _QUOTE_CLOSE_RE.sub(" 」", text)


class HtmlBlockRenderer:
    """Table-driven HTML5 renderer implementing `BlockRenderer`."""

    def __init__(self, image_base_url: str = "../../../assets/images") -> None:
        self._image_base_url = image_base_url.rstrip("/")
        self._dispatch: dict[BlockKind, Callable[[Block], str]] = {
            BlockKind.PARAGRAPH: self._render_paragraph,
            BlockKind.SYSTEM_MESSAGE: self._render_system,
            BlockKind.CONSTELLATION: self._render_constellation,
            BlockKind.OUTER_GOD: self._render_outergod,
            BlockKind.QUOTE: self._render_quote,
            BlockKind.NOTICE: self._render_notice,
            BlockKind.LIST: self._render_list,
            BlockKind.SYSTEM_WINDOW: self._render_window,
            BlockKind.GENERIC_BOX: self._render_box,
            BlockKind.COVER: lambda _b: "",
            BlockKind.IMAGE: self._render_image,
            BlockKind.DIVIDER: lambda _b: "<hr>",
            BlockKind.BLANK_LINE: lambda _b: "<br>",
        }

    def render(self, block: Block) -> str:
        """Render a single `Block` to HTML5."""
        handler = self._dispatch.get(block.kind)
        if handler is None:
            raise ValueError(f"Unsupported block kind: {block.kind}")
        return handler(block)

    def render_cover(self, cover: CoverBlock | None) -> str:
        """Render the chapter cover block for placement above the article."""
        if cover is None or not cover.filename:
            return ""
        src = f"{self._image_base_url}/{urlparse.quote(cover.filename)}"
        alt = escape_inline_html(cover.alt or "Обложка главы")
        return f'<div class="orv_cover"><img src="{src}" alt="{alt}"></div>'

    def render_chapter_body(
        self,
        chapter: Chapter,
        *,
        words_per_minute: int = 250,
    ) -> tuple[str, str]:
        """Return `(cover_html, article_inner_html)` for a full chapter page."""
        cover_html = self.render_cover(chapter.cover)
        parts: list[str] = []
        for block in chapter.blocks:
            rendered = self.render(block)
            if rendered:
                parts.append(rendered)

        while parts and parts[-1] in ("<br>", "<hr>"):
            parts.pop()
        parts.extend(["<br>", "<hr>"])

        title_escaped = escape_inline_html(chapter.title)
        words_label = format_ru_words(chapter.word_count)
        read_mins = chapter.reading_time_minutes(words_per_minute=words_per_minute)
        header_html = (
            '<div class="orv_title">'
            f"<h1>{title_escaped}</h1>"
            f'<div class="orv_wordcount">{words_label} · ~{read_mins} мин чтения</div>'
            "</div>"
        )
        return cover_html, "\n".join([header_html, *parts])

    @staticmethod
    def _render_paragraph(block: Block) -> str:
        assert isinstance(block, ParagraphBlock)
        return f'<p class="orv_line">{escape_inline_html(block.text)}</p>'

    @staticmethod
    def _render_system(block: Block) -> str:
        assert isinstance(block, SystemMessageBlock)
        return f'<div class="orv_system"><p>{escape_inline_html(block.text)}</p></div>'

    @staticmethod
    def _render_constellation(block: Block) -> str:
        assert isinstance(block, ConstellationBlock)
        return f'<div class="orv_constellation"><p>{escape_inline_html(block.text)}</p></div>'

    @staticmethod
    def _render_outergod(block: Block) -> str:
        assert isinstance(block, OuterGodBlock)
        return f'<div class="orv_outergod"><p>{escape_inline_html(block.text)}</p></div>'

    @staticmethod
    def _render_quote(block: Block) -> str:
        assert isinstance(block, QuoteBlock)
        normalized = _normalize_quotes(block.text)
        return f'<div class="orv_quote"><p>{escape_inline_html(normalized)}</p></div>'

    @staticmethod
    def _render_notice(block: Block) -> str:
        assert isinstance(block, NoticeBlock)
        return f'<div class="orv_notice"><p>{escape_inline_html(block.text)}</p></div>'

    @staticmethod
    def _render_list(block: Block) -> str:
        assert isinstance(block, ListBlock)
        return f'<ul class="orv_list"><li>{escape_inline_html(block.text)}</li></ul>'

    @staticmethod
    def _render_window(block: Block) -> str:
        assert isinstance(block, SystemWindowBlock)
        out = ['<div class="orv_window">']
        for raw_line in block.lines:
            cleaned = clean_container_line(raw_line)
            if cleaned == "":
                out.append("<br>")
            elif SystemWindowBlock.is_header_line(raw_line):
                out.append(f'<h3 class="orv_window_title">{escape_inline_html(cleaned)}</h3>')
            else:
                out.append(f"<p>{escape_inline_html(cleaned)}</p>")
        out.append("</div>")
        return "\n".join(out)

    @staticmethod
    def _render_box(block: Block) -> str:
        assert isinstance(block, GenericBoxBlock)
        out = ['<div class="orv_box">']
        for raw_line in block.lines:
            cleaned = clean_container_line(raw_line)
            if cleaned == "":
                out.append("<br>")
            else:
                out.append(f"<p>{escape_inline_html(cleaned)}</p>")
        out.append("</div>")
        return "\n".join(out)

    def _render_image(self, block: Block) -> str:
        assert isinstance(block, ImageBlock)
        src = f"{self._image_base_url}/{urlparse.quote(block.filename)}"
        alt = escape_inline_html(block.alt or "Иллюстрация")
        return f'<div class="orv_image"><img src="{src}" alt="{alt}" loading="lazy"></div>'
