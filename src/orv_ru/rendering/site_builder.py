"""Static HTML site builder compiling chapters, templates, assets, and metadata."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from orv_ru.domain.blocks import CoverBlock, ImageBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import StoryMetadata
from orv_ru.ports.renderer import SiteBuildReport
from orv_ru.rendering.assets import AssetResolver
from orv_ru.rendering.escaping import escape_inline_html, format_ru_words
from orv_ru.rendering.html_blocks import HtmlBlockRenderer

_BRANDING_FILES: tuple[str, ...] = (
    "background-stars.avif",
    "background-stars.jpg",
    "background-stars-mobile.jpg",
    "od-stigma.webp",
    "favicon.ico",
    "icon512_rounded.png",
    "icon512_maskable.png",
)

_SVG_HOME = (
    '<svg xmlns="http://www.w3.org/2000/svg" height="24" width="24" '
    'viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true">'
    '<path d="M240-200h120v-240h240v240h120v-360L480-740 240-560v360Zm'
    '-80 80v-480l320-240 320 240v480H520v-240h-80v240H160Z"/></svg>'
)
_SVG_PREV = (
    '<svg xmlns="http://www.w3.org/2000/svg" height="24" width="24" '
    'viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true">'
    '<path d="M400-80 0-480l400-400 71 71-329 329 329 329-71 71Z"/></svg>'
)
_SVG_NEXT = (
    '<svg xmlns="http://www.w3.org/2000/svg" height="24" width="24" '
    'viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true">'
    '<path d="m321-80-71-71 329-329-329-329 71-71 400 400L321-80Z"/></svg>'
)


def _apply_placeholders(template: str, mapping: dict[str, str]) -> str:
    result = template
    for key, value in mapping.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


class StaticSiteBuilder:
    """Compiles a collection of `Chapter` objects into a self-contained static web reader."""

    def __init__(
        self,
        web_dir: Path,
        block_renderer: HtmlBlockRenderer,
        asset_resolver: AssetResolver,
        *,
        words_per_minute: int = 250,
        epub_source_dir: Path | None = None,
        branding_dir: Path | None = None,
    ) -> None:
        self._web_dir = web_dir
        self._renderer = block_renderer
        self._asset_resolver = asset_resolver
        self._words_per_minute = words_per_minute
        self._epub_source_dir = epub_source_dir
        self._branding_dir = branding_dir

    def build(
        self,
        story: StoryMetadata,
        chapters: list[Chapter],
        output_dir: Path,
    ) -> SiteBuildReport:
        """Build the complete static site into `output_dir` and return a `SiteBuildReport`."""
        ordered = sorted(chapters, key=lambda c: c.number)
        output_dir.mkdir(parents=True, exist_ok=True)

        self._copy_web_assets(output_dir)
        self._copy_branding_assets(story, output_dir)
        assets_copied, missing_assets = self._copy_chapter_images(ordered, output_dir)
        self._copy_epubs_if_present(output_dir)

        meta_dir = output_dir / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        self._write_metadata(story, ordered, meta_dir)

        templates_dir = self._web_dir / "templates"
        self._render_top_pages(story, ordered, templates_dir, output_dir)
        self._render_chapters(story, ordered, templates_dir, output_dir)

        return SiteBuildReport(
            chapters_built=len(ordered),
            assets_copied=assets_copied,
            missing_assets=tuple(sorted(missing_assets)),
            output_dir=output_dir,
        )

    def _copy_web_assets(self, output_dir: Path) -> None:
        src_assets = self._web_dir / "assets"
        dst_assets = output_dir / "assets"
        if dst_assets.exists():
            shutil.rmtree(dst_assets)
        if src_assets.is_dir():
            shutil.copytree(
                src_assets,
                dst_assets,
                ignore=shutil.ignore_patterns(".DS_Store"),
            )

    def _copy_branding_assets(self, story: StoryMetadata, output_dir: Path) -> None:
        if self._branding_dir is None or not self._branding_dir.is_dir():
            return

        media_out = output_dir / "assets" / "media"
        media_out.mkdir(parents=True, exist_ok=True)

        for filename in _BRANDING_FILES:
            src_file = self._branding_dir / filename
            if src_file.is_file():
                shutil.copy2(src_file, media_out / filename)

        covers_src_dir = self._branding_dir / "covers"
        cover_src = covers_src_dir / f"{story.slug}.webp"
        if not cover_src.is_file():
            cover_src = covers_src_dir / "cont.webp"
        if cover_src.is_file():
            covers_out = media_out / "covers"
            covers_out.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cover_src, covers_out / f"{story.slug}.webp")

    def _copy_chapter_images(
        self,
        chapters: list[Chapter],
        output_dir: Path,
    ) -> tuple[int, set[str]]:
        requested_names: set[str] = set()
        for ch in chapters:
            for block in ch.blocks:
                if isinstance(block, (CoverBlock, ImageBlock)) and block.filename:
                    requested_names.add(block.filename)

        images_out = output_dir / "assets" / "images"
        images_out.mkdir(parents=True, exist_ok=True)
        copied = 0
        missing: set[str] = set()
        for name in sorted(requested_names):
            resolved = self._asset_resolver.resolve(name)
            if resolved is None:
                missing.add(name)
                continue
            target = images_out / Path(name).name
            shutil.copy2(resolved, target)
            copied += 1
        return copied, missing

    def _copy_epubs_if_present(self, output_dir: Path) -> None:
        if self._epub_source_dir is None or not self._epub_source_dir.is_dir():
            return
        epubs = list(self._epub_source_dir.glob("*.epub"))
        if not epubs:
            return
        downloads_dir = output_dir / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        for epub in epubs:
            shutil.copy2(epub, downloads_dir / epub.name)

    @staticmethod
    def _write_metadata(
        story: StoryMetadata,
        chapters: list[Chapter],
        meta_dir: Path,
    ) -> None:
        index_entries = [
            {
                "number": ch.number,
                "index": ch.number - 1,
                "title": ch.title,
                "href": f"ch_{ch.number}.html",
                "words": ch.word_count,
            }
            for ch in chapters
        ]
        (meta_dir / f"{story.slug}.json").write_text(
            json.dumps(index_entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        meta_payload = {
            "slug": story.slug,
            "title": story.title,
            "original_title": story.original_title,
            "author": story.author,
            "language": story.language,
            "status": story.status,
            "chapters": len(chapters),
            "first_chapter": chapters[0].number if chapters else None,
            "last_chapter": chapters[-1].number if chapters else None,
        }
        (meta_dir / f"{story.slug}_meta.json").write_text(
            json.dumps(meta_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _render_top_pages(
        self,
        story: StoryMetadata,
        chapters: list[Chapter],
        templates_dir: Path,
        output_dir: Path,
    ) -> None:
        first_href = f"./read/ch_{chapters[0].number}.html" if chapters else "#"
        first_from_root = (
            f"stories/{story.slug}/read/ch_{chapters[0].number}.html"
            if chapters
            else f"stories/{story.slug}/index.html"
        )
        epub_name = f"orv_{story.slug}_{story.language}.epub"
        epub_exists = (output_dir / "downloads" / epub_name).is_file()
        epub_status_note = (
            f"{story.title} · {len(chapters)} гл. · {epub_name}"
            if epub_exists
            else "EPUB ещё не собран (выполните команду build-epub)"
        )
        initial_chapters_html = "".join(
            f'<div class="chapter_item"><a href="./read/ch_{ch.number}.html">'
            f"<p>{escape_inline_html(ch.title)}</p></a></div>"
            for ch in chapters
        )

        common = {
            "STORY_SLUG": escape_inline_html(story.slug),
            "STORY_TITLE": escape_inline_html(story.title),
            "STORY_AUTHOR": escape_inline_html(story.author),
            "STORY_STATUS": escape_inline_html(story.status),
            "CHAPTER_COUNT": str(len(chapters)),
            "FIRST_CHAPTER_HREF": first_href,
            "FIRST_CHAPTER_FROM_ROOT": first_from_root,
            "EPUB_FILENAME": epub_name,
            "EPUB_HREF": f"./downloads/{epub_name}",
            "EPUB_STATUS_NOTE": escape_inline_html(epub_status_note),
            "INITIAL_CHAPTER_ITEMS": initial_chapters_html,
        }

        landing_tpl = (templates_dir / "landing.html").read_text(encoding="utf-8")
        (output_dir / "index.html").write_text(
            _apply_placeholders(landing_tpl, common),
            encoding="utf-8",
        )

        download_tpl = (templates_dir / "download.html").read_text(encoding="utf-8")
        (output_dir / "download.html").write_text(
            _apply_placeholders(download_tpl, common),
            encoding="utf-8",
        )

        not_found_path = templates_dir / "404.html"
        if not_found_path.is_file():
            not_found_tpl = not_found_path.read_text(encoding="utf-8")
            (output_dir / "404.html").write_text(
                _apply_placeholders(not_found_tpl, common),
                encoding="utf-8",
            )

        stories_dir = output_dir / "stories"
        stories_dir.mkdir(parents=True, exist_ok=True)
        stories_tpl = (templates_dir / "stories.html").read_text(encoding="utf-8")
        (stories_dir / "index.html").write_text(
            _apply_placeholders(stories_tpl, common),
            encoding="utf-8",
        )

        story_dir = stories_dir / story.slug
        story_dir.mkdir(parents=True, exist_ok=True)
        story_tpl = (templates_dir / "story_index.html").read_text(encoding="utf-8")
        (story_dir / "index.html").write_text(
            _apply_placeholders(story_tpl, common),
            encoding="utf-8",
        )

    def _render_chapters(
        self,
        story: StoryMetadata,
        chapters: list[Chapter],
        templates_dir: Path,
        output_dir: Path,
    ) -> None:
        read_dir = output_dir / "stories" / story.slug / "read"
        read_dir.mkdir(parents=True, exist_ok=True)
        chapter_tpl = (templates_dir / "chapter.html").read_text(encoding="utf-8")

        for idx, ch in enumerate(chapters):
            cover_html, body_html = self._renderer.render_chapter_body(
                ch, words_per_minute=self._words_per_minute
            )
            if idx == 0:
                prev_href = "../index.html"
                prev_label = "Оглавление"
                prev_svg = _SVG_HOME
            else:
                prev_href = f"./ch_{chapters[idx - 1].number}.html"
                prev_label = "Предыдущая"
                prev_svg = _SVG_PREV

            if idx == len(chapters) - 1:
                next_href = "../index.html"
                next_label = "Оглавление"
                next_svg = _SVG_HOME
            else:
                next_href = f"./ch_{chapters[idx + 1].number}.html"
                next_label = "Следующая"
                next_svg = _SVG_NEXT

            rendered = _apply_placeholders(
                chapter_tpl,
                {
                    "TITLE": escape_inline_html(ch.title),
                    "STORY_SLUG": escape_inline_html(story.slug),
                    "STORY_TITLE": escape_inline_html(story.title),
                    "CHAPTER_NUMBER": str(ch.number),
                    "WORD_COUNT_LABEL": escape_inline_html(format_ru_words(ch.word_count)),
                    "READ_TIME": str(ch.reading_time_minutes(self._words_per_minute)),
                    "COVER": cover_html,
                    "CONTENT": body_html,
                    "PREV_HREF": prev_href,
                    "PREV_LABEL": prev_label,
                    "PREV_SVG": prev_svg,
                    "NEXT_HREF": next_href,
                    "NEXT_LABEL": next_label,
                    "NEXT_SVG": next_svg,
                },
            )
            (read_dir / f"ch_{ch.number}.html").write_text(rendered, encoding="utf-8")
