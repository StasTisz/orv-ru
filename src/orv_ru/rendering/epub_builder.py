"""Clean-room EPUB 3 packager preserving Rich Text styling and footnotes."""

from __future__ import annotations

import datetime as dt
import re
import urllib.parse as urlparse
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from orv_ru.domain.blocks import (
    AssetBlock,
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
from orv_ru.domain.story import StoryMetadata
from orv_ru.ports.renderer import EpubBuildReport
from orv_ru.rendering.assets import AssetResolver
from orv_ru.rendering.escaping import clean_container_line, escape_inline_html

_NOTE_PREFIX_RE = re.compile(r"^\[\d+\]\s*")

_EPUB_CSS = """body {
  font-family: Georgia, "Times New Roman", serif;
  line-height: 1.6;
  margin: 1.2em;
  color: #1f2328;
}
h1, h2 {
  text-align: center;
  line-height: 1.25;
  margin: 0.8em 0 1em 0;
}
p.orv_line {
  margin: 0.65em 0;
  text-indent: 1em;
}
.orv_cover, .orv_image {
  text-align: center;
  margin: 1em 0;
}
.orv_cover img, .orv_image img {
  max-width: 100%;
  height: auto;
}
.orv_system, .orv_window, .orv_box {
  margin: 1em auto;
  padding: 0.7em 1em;
  border: 1px solid #4a7ebb;
  border-left: 4px solid #1f6feb;
  border-radius: 4px;
}
.orv_window_title {
  text-align: center;
  margin: 0 0 0.5em 0;
  font-size: 1.05em;
}
.orv_constellation {
  margin: 0.9em auto;
  padding: 0.5em 0.9em;
  border-left: 3px solid #1b7f37;
  text-align: center;
}
.orv_outergod {
  margin: 0.9em auto;
  padding: 0.5em 0.9em;
  border-left: 3px solid #c92a2a;
  text-align: center;
}
.orv_quote {
  margin: 0.9em 0.8em;
  padding: 0.4em 0.9em;
  border-left: 3px solid #d97706;
  font-style: italic;
}
.orv_noteref {
  font-size: 0.8em;
  vertical-align: super;
  text-decoration: none;
  color: #1f6feb;
}
.orv_endnotes {
  margin-top: 2em;
  border-top: 1px solid #ccc;
  padding-top: 0.8em;
  font-size: 0.9em;
}
hr {
  border: none;
  border-top: 1px solid #aaa;
  margin: 1.4em auto;
  width: 60%;
}
"""

_CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


@dataclass
class _ChapterRenderCtx:
    """Mutable per-chapter state collecting endnotes alongside embedded asset lookup."""

    embedded_images: dict[str, tuple[Path, str]]
    notes: list[str]


_XhtmlBlockRenderer = Callable[[Block, _ChapterRenderCtx], str]


def _xhtml_paragraph(block: Block, _ctx: _ChapterRenderCtx) -> str:
    assert isinstance(block, ParagraphBlock)
    return f'<p class="orv_line">{escape_inline_html(block.text, xhtml=True)}</p>'


def _xhtml_system(block: Block, _ctx: _ChapterRenderCtx) -> str:
    assert isinstance(block, SystemMessageBlock)
    return f'<div class="orv_system"><p>{escape_inline_html(block.text, xhtml=True)}</p></div>'


def _xhtml_constellation(block: Block, _ctx: _ChapterRenderCtx) -> str:
    assert isinstance(block, ConstellationBlock)
    return (
        '<div class="orv_constellation">'
        f"<p>{escape_inline_html(block.text, xhtml=True)}</p></div>"
    )


def _xhtml_outergod(block: Block, _ctx: _ChapterRenderCtx) -> str:
    assert isinstance(block, OuterGodBlock)
    return f'<div class="orv_outergod"><p>{escape_inline_html(block.text, xhtml=True)}</p></div>'


def _xhtml_quote(block: Block, _ctx: _ChapterRenderCtx) -> str:
    assert isinstance(block, QuoteBlock)
    return f'<div class="orv_quote"><p>{escape_inline_html(block.text, xhtml=True)}</p></div>'


def _xhtml_list(block: Block, _ctx: _ChapterRenderCtx) -> str:
    assert isinstance(block, ListBlock)
    return f"<ul><li>{escape_inline_html(block.text, xhtml=True)}</li></ul>"


def _xhtml_notice(block: Block, ctx: _ChapterRenderCtx) -> str:
    assert isinstance(block, NoticeBlock)
    idx = len(ctx.notes) + 1
    cleaned = _NOTE_PREFIX_RE.sub("", block.text).strip()
    ctx.notes.append(
        f'<aside id="note-{idx}" epub:type="footnote">'
        f"<p><strong>[{idx}]</strong> {escape_inline_html(cleaned, xhtml=True)}</p></aside>"
    )
    return (
        f'<p class="orv_notice"><a class="orv_noteref" href="#note-{idx}" '
        f'epub:type="noteref">[Прим. {idx}]</a></p>'
    )


def _xhtml_window(block: Block, _ctx: _ChapterRenderCtx) -> str:
    assert isinstance(block, SystemWindowBlock)
    lines_html = ['<div class="orv_window">']
    for raw_line in block.lines:
        cleaned = clean_container_line(raw_line)
        if cleaned == "":
            lines_html.append("<br/>")
        elif SystemWindowBlock.is_header_line(raw_line):
            lines_html.append(
                f'<h3 class="orv_window_title">{escape_inline_html(cleaned, xhtml=True)}</h3>'
            )
        else:
            lines_html.append(f"<p>{escape_inline_html(cleaned, xhtml=True)}</p>")
    lines_html.append("</div>")
    return "\n".join(lines_html)


def _xhtml_box(block: Block, _ctx: _ChapterRenderCtx) -> str:
    assert isinstance(block, GenericBoxBlock)
    lines_html = ['<div class="orv_box">']
    for raw_line in block.lines:
        cleaned = clean_container_line(raw_line)
        lines_html.append(
            "<br/>" if cleaned == "" else f"<p>{escape_inline_html(cleaned, xhtml=True)}</p>"
        )
    lines_html.append("</div>")
    return "\n".join(lines_html)


def _xhtml_asset(block: Block, ctx: _ChapterRenderCtx) -> str:
    assert isinstance(block, AssetBlock)
    safe_name = Path(block.filename).name
    css_class = "orv_cover" if isinstance(block, CoverBlock) else "orv_image"
    alt = escape_inline_html(block.alt or "Иллюстрация", xhtml=True)
    if safe_name in ctx.embedded_images:
        src = f"images/{urlparse.quote(safe_name)}"
        return f'<div class="{css_class}"><img src="{src}" alt="{alt}"/></div>'
    return f'<p class="orv_line">[{alt}]</p>'


_XHTML_DISPATCH: dict[BlockKind, _XhtmlBlockRenderer] = {
    BlockKind.PARAGRAPH: _xhtml_paragraph,
    BlockKind.SYSTEM_MESSAGE: _xhtml_system,
    BlockKind.CONSTELLATION: _xhtml_constellation,
    BlockKind.OUTER_GOD: _xhtml_outergod,
    BlockKind.QUOTE: _xhtml_quote,
    BlockKind.LIST: _xhtml_list,
    BlockKind.NOTICE: _xhtml_notice,
    BlockKind.SYSTEM_WINDOW: _xhtml_window,
    BlockKind.GENERIC_BOX: _xhtml_box,
    BlockKind.COVER: _xhtml_asset,
    BlockKind.IMAGE: _xhtml_asset,
    BlockKind.DIVIDER: lambda _b, _ctx: "<hr/>",
    BlockKind.BLANK_LINE: lambda _b, _ctx: "<br/>",
}


class EpubBookBuilder:
    """Packages chapters into a standards-compliant EPUB 3 archive."""

    def __init__(self, asset_resolver: AssetResolver) -> None:
        self._asset_resolver = asset_resolver

    def build(
        self,
        story: StoryMetadata,
        chapters: list[Chapter],
        output_file: Path,
    ) -> EpubBuildReport:
        """Build an EPUB archive at `output_file` and return `EpubBuildReport`."""
        ordered = sorted(chapters, key=lambda c: c.number)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        embedded_images: dict[str, tuple[Path, str]] = {}
        missing_assets: set[str] = set()

        for ch in ordered:
            for block in ch.blocks:
                if isinstance(block, (CoverBlock, ImageBlock)) and block.filename:
                    safe_name = Path(block.filename).name
                    if safe_name in embedded_images or safe_name in missing_assets:
                        continue
                    resolved = self._asset_resolver.resolve(safe_name)
                    if resolved is None:
                        missing_assets.add(safe_name)
                    else:
                        embedded_images[safe_name] = (
                            resolved,
                            self._asset_resolver.guess_media_type(resolved),
                        )

        chapter_docs = [
            (ch, self._render_chapter_xhtml(ch, embedded_images)) for ch in ordered
        ]

        with zipfile.ZipFile(output_file, "w") as zf:
            # OCF spec requires `mimetype` to be the very first ZIP entry and stored uncompressed.
            zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
            zf.writestr("META-INF/container.xml", _CONTAINER_XML.encode("utf-8"), zipfile.ZIP_DEFLATED)
            zf.writestr("OEBPS/styles/book.css", _EPUB_CSS.encode("utf-8"), zipfile.ZIP_DEFLATED)
            # Emit both EPUB 3 (`nav.xhtml`) and EPUB 2 (`toc.ncx`) TOCs for maximum reader support.
            zf.writestr(
                "OEBPS/nav.xhtml",
                self._render_nav_xhtml(story, ordered).encode("utf-8"),
                zipfile.ZIP_DEFLATED,
            )
            zf.writestr(
                "OEBPS/toc.ncx",
                self._render_toc_ncx(story, ordered).encode("utf-8"),
                zipfile.ZIP_DEFLATED,
            )
            zf.writestr(
                "OEBPS/content.opf",
                self._render_content_opf(story, ordered, embedded_images).encode("utf-8"),
                zipfile.ZIP_DEFLATED,
            )
            for ch, xhtml in chapter_docs:
                zf.writestr(f"OEBPS/ch_{ch.number}.xhtml", xhtml.encode("utf-8"), zipfile.ZIP_DEFLATED)
            for safe_name, (resolved_path, _media_type) in embedded_images.items():
                zf.write(
                    resolved_path,
                    arcname=f"OEBPS/images/{safe_name}",
                    compress_type=zipfile.ZIP_DEFLATED,
                )

        return EpubBuildReport(
            chapters_built=len(ordered),
            assets_embedded=len(embedded_images),
            missing_assets=tuple(sorted(missing_assets)),
            output_file=output_file,
        )

    @staticmethod
    def _render_chapter_xhtml(
        chapter: Chapter,
        embedded_images: dict[str, tuple[Path, str]],
    ) -> str:
        title_xml = escape_inline_html(chapter.title, xhtml=True)
        ctx = _ChapterRenderCtx(embedded_images=embedded_images, notes=[])
        body_parts: list[str] = []

        for block in chapter.blocks:
            renderer = _XHTML_DISPATCH.get(block.kind)
            if renderer is None:
                raise ValueError(f"Unsupported block kind in EPUB builder: {block.kind}")
            rendered = renderer(block, ctx)
            if rendered:
                body_parts.append(rendered)

        endnotes_html = ""
        if ctx.notes:
            endnotes_html = (
                '<section class="orv_endnotes" epub:type="endnotes">\n'
                "<h3>Примечания</h3>\n"
                + "\n".join(ctx.notes)
                + "\n</section>\n"
            )

        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ru">\n'
            "<head>\n"
            '  <meta charset="utf-8"/>\n'
            f"  <title>{title_xml}</title>\n"
            '  <link rel="stylesheet" type="text/css" href="styles/book.css"/>\n'
            "</head>\n"
            "<body>\n"
            f"<h2>{title_xml}</h2>\n"
            "<hr/>\n"
            + "\n".join(body_parts)
            + "\n"
            + endnotes_html
            + "</body>\n</html>\n"
        )

    @staticmethod
    def _render_nav_xhtml(story: StoryMetadata, chapters: list[Chapter]) -> str:
        items = "\n".join(
            f'      <li><a href="ch_{ch.number}.xhtml">{escape_inline_html(ch.title, xhtml=True)}</a></li>'
            for ch in chapters
        )
        title_xml = escape_inline_html(story.title, xhtml=True)
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ru">\n'
            "<head>\n"
            '  <meta charset="utf-8"/>\n'
            f"  <title>{title_xml} — Оглавление</title>\n"
            '  <link rel="stylesheet" type="text/css" href="styles/book.css"/>\n'
            "</head>\n"
            "<body>\n"
            '  <nav epub:type="toc" id="toc">\n'
            "    <h1>Оглавление</h1>\n"
            "    <ol>\n"
            f"{items}\n"
            "    </ol>\n"
            "  </nav>\n"
            "</body>\n</html>\n"
        )

    @staticmethod
    def _render_toc_ncx(story: StoryMetadata, chapters: list[Chapter]) -> str:
        nav_points = "\n".join(
            f'    <navPoint id="nav-{ch.number}" playOrder="{idx}">\n'
            f"      <navLabel><text>{escape_inline_html(ch.title, xhtml=True)}</text></navLabel>\n"
            f'      <content src="ch_{ch.number}.xhtml"/>\n'
            "    </navPoint>"
            for idx, ch in enumerate(chapters, start=1)
        )
        title_xml = escape_inline_html(story.title, xhtml=True)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
            "  <head>\n"
            f'    <meta name="dtb:uid" content="orv-ru-{escape_inline_html(story.slug, xhtml=True)}"/>\n'
            '    <meta name="dtb:depth" content="1"/>\n'
            '    <meta name="dtb:totalPageCount" content="0"/>\n'
            '    <meta name="dtb:maxPageNumber" content="0"/>\n'
            "  </head>\n"
            f"  <docTitle><text>{title_xml}</text></docTitle>\n"
            "  <navMap>\n"
            f"{nav_points}\n"
            "  </navMap>\n"
            "</ncx>\n"
        )

    @staticmethod
    def _render_content_opf(
        story: StoryMetadata,
        chapters: list[Chapter],
        embedded_images: dict[str, tuple[Path, str]],
    ) -> str:
        modified = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest_items = [
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="book-css" href="styles/book.css" media-type="text/css"/>',
        ]
        for ch in chapters:
            manifest_items.append(
                f'<item id="ch_{ch.number}" href="ch_{ch.number}.xhtml" '
                'media-type="application/xhtml+xml"/>'
            )
        for idx, (safe_name, (_path, media_type)) in enumerate(sorted(embedded_images.items())):
            href = f"images/{urlparse.quote(safe_name)}"
            manifest_items.append(f'<item id="img_{idx}" href="{href}" media-type="{media_type}"/>')

        spine_items = ['<itemref idref="nav"/>'] + [
            f'<itemref idref="ch_{ch.number}"/>' for ch in chapters
        ]
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">\n'
            '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            f'    <dc:identifier id="bookid">orv-ru-{escape_inline_html(story.slug, xhtml=True)}</dc:identifier>\n'
            f"    <dc:title>{escape_inline_html(story.title, xhtml=True)}</dc:title>\n"
            f"    <dc:creator>{escape_inline_html(story.author, xhtml=True)}</dc:creator>\n"
            f"    <dc:language>{escape_inline_html(story.language, xhtml=True)}</dc:language>\n"
            f'    <meta property="dcterms:modified">{modified}</meta>\n'
            "  </metadata>\n"
            "  <manifest>\n    "
            + "\n    ".join(manifest_items)
            + "\n  </manifest>\n"
            '  <spine toc="ncx">\n    '
            + "\n    ".join(spine_items)
            + "\n  </spine>\n"
            "</package>\n"
        )
