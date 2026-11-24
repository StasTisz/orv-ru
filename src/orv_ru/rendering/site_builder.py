"""Static HTML site builder compiling chapters, templates, assets, and metadata."""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
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
_SVG_DOWNLOAD = (
    '<svg xmlns="http://www.w3.org/2000/svg" height="20" width="20" '
    'viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true">'
    '<path d="M480-320 280-520l56-58 104 104v-326h80v326l104-104 56 58-200 200ZM'
    '240-160q-33 0-56.5-23.5T160-240v-120h80v120h480v-120h80v120q0 33-23.5 56.5'
    'T720-160H240Z"/></svg>'
)
_SVG_BOOK = (
    '<svg xmlns="http://www.w3.org/2000/svg" height="24" width="24" '
    'viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true">'
    '<path d="M240-80q-33 0-56.5-23.5T160-160v-640q0-33 23.5-56.5T240-880h480q33 0 '
    '56.5 23.5T800-800v640q0 33-23.5 56.5T720-80H240Zm0-80h480v-640h-80v280l-100-60'
    '-100 60v-280H240v640Z"/></svg>'
)
_SVG_LIST = (
    '<svg xmlns="http://www.w3.org/2000/svg" height="24" width="24" '
    'viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true">'
    '<path d="M280-600v-80h560v80H280Zm0 160v-80h560v80H280Zm0 160v-80h560v80H280ZM'
    '160-600q-17 0-28.5-11.5T120-640q0-17 11.5-28.5T160-680q17 0 28.5 11.5T200-640q0 '
    '17-11.5 28.5T160-600Zm0 160q-17 0-28.5-11.5T120-480q0-17 11.5-28.5T160-520q17 0 '
    '28.5 11.5T200-480q0 17-11.5 28.5T160-440Zm0 160q-17 0-28.5-11.5T120-320q0-17 '
    '11.5-28.5T160-360q17 0 28.5 11.5T200-320q0 17-11.5 28.5T160-280Z"/></svg>'
)
_SVG_PLAY = (
    '<svg xmlns="http://www.w3.org/2000/svg" height="24" width="24" '
    'viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true">'
    '<path d="m380-300 280-180-280-180v360ZM480-80q-83 0-156-31.5T197-197q-54-54'
    '-85.5-127T80-480q0-83 31.5-156T197-763q54-54 127-85.5T480-880q83 0 156 31.5T763-763'
    'q54 54 85.5 127T880-480q0 83-31.5 156T763-197q-54 54-127 85.5T480-80Zm0-80q134 0 '
    '227-93t93-227q0-134-93-227t-227-93q-134 0-227 93t-93 227q0 134 93 227t227 93Z"/></svg>'
)


def _apply_placeholders(template: str, mapping: dict[str, str]) -> str:
    result = template
    for key, value in mapping.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


class StaticSiteBuilder:
    """Compiles one or more stories into a self-contained static web reader."""

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
        """Build a single-story static site into `output_dir`."""
        return self.build_collection(
            [(story, chapters)],
            output_dir,
            primary_slug=story.slug,
        )

    def build_collection(
        self,
        stories: Sequence[tuple[StoryMetadata, list[Chapter]]],
        output_dir: Path,
        *,
        primary_slug: str | None = None,
        source_counts: dict[str, int] | None = None,
    ) -> SiteBuildReport:
        """Build a multi-story static site (ORV, Sequel, Side Stories) into `output_dir`."""
        if not stories:
            raise ValueError("At least one story is required to build a static site.")

        ordered_stories = [
            (story, sorted(chapters, key=lambda c: c.number)) for story, chapters in stories
        ]
        primary = self._select_primary(ordered_stories, primary_slug)
        all_chapters = [ch for _story, chs in ordered_stories for ch in chs]

        output_dir.mkdir(parents=True, exist_ok=True)
        self._copy_web_assets(output_dir)
        self._copy_branding_assets([story for story, _ in ordered_stories], output_dir)
        assets_copied, missing_assets = self._copy_chapter_images(all_chapters, output_dir)
        self._copy_epubs_if_present(output_dir)

        meta_dir = output_dir / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        for story, ordered in ordered_stories:
            src_total = source_counts.get(story.slug) if source_counts else None
            self._write_metadata(story, ordered, meta_dir, source_chapters=src_total)

        templates_dir = self._web_dir / "templates"
        self._render_global_pages(
            ordered_stories,
            primary,
            templates_dir,
            output_dir,
            source_counts=source_counts,
        )
        for story, ordered in ordered_stories:
            src_total = source_counts.get(story.slug) if source_counts else None
            self._render_story_pages(
                story,
                ordered,
                templates_dir,
                output_dir,
                source_chapters=src_total,
            )

        return SiteBuildReport(
            chapters_built=len(all_chapters),
            assets_copied=assets_copied,
            missing_assets=tuple(sorted(missing_assets)),
            output_dir=output_dir,
        )

    @staticmethod
    def _select_primary(
        ordered_stories: list[tuple[StoryMetadata, list[Chapter]]],
        primary_slug: str | None,
    ) -> tuple[StoryMetadata, list[Chapter]]:
        if primary_slug is not None:
            for pair in ordered_stories:
                if pair[0].slug == primary_slug:
                    return pair
        for pair in ordered_stories:
            if pair[1]:
                return pair
        return ordered_stories[0]

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

    def _copy_branding_assets(self, stories: list[StoryMetadata], output_dir: Path) -> None:
        if self._branding_dir is None or not self._branding_dir.is_dir():
            return

        media_out = output_dir / "assets" / "media"
        media_out.mkdir(parents=True, exist_ok=True)

        for filename in _BRANDING_FILES:
            src_file = self._branding_dir / filename
            if src_file.is_file():
                shutil.copy2(src_file, media_out / filename)

        covers_src_dir = self._branding_dir / "covers"
        if not covers_src_dir.is_dir():
            return
        covers_out = media_out / "covers"
        covers_out.mkdir(parents=True, exist_ok=True)

        # Copy all available branding covers (e.g. orv.webp, cont.webp, side.webp).
        for cover_file in covers_src_dir.iterdir():
            if cover_file.is_file() and cover_file.name != ".DS_Store":
                shutil.copy2(cover_file, covers_out / cover_file.name)

        # Ensure every configured story slug has a cover file (fallback to cont.webp).
        fallback = covers_src_dir / "cont.webp"
        for story in stories:
            target = covers_out / f"{story.slug}.webp"
            if not target.is_file() and fallback.is_file():
                shutil.copy2(fallback, target)

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
        *,
        source_chapters: int | None = None,
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

        meta_payload: dict[str, object] = {
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
        if source_chapters is not None:
            meta_payload["source_chapters"] = source_chapters
        (meta_dir / f"{story.slug}_meta.json").write_text(
            json.dumps(meta_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _render_global_pages(
        self,
        ordered_stories: list[tuple[StoryMetadata, list[Chapter]]],
        primary: tuple[StoryMetadata, list[Chapter]],
        templates_dir: Path,
        output_dir: Path,
        *,
        source_counts: dict[str, int] | None = None,
    ) -> None:
        primary_story, primary_chapters = primary
        first_from_root = (
            f"stories/{primary_story.slug}/read/ch_{primary_chapters[0].number}.html"
            if primary_chapters
            else f"stories/{primary_story.slug}/index.html"
        )
        first_ch_label = (
            f"Глава {primary_chapters[0].number}" if primary_chapters else "Оглавление"
        )

        cards_html = "".join(
            f'<a href="{escape_inline_html(story.slug)}/index.html" class="card">'
            f'<img src="../assets/media/covers/{escape_inline_html(story.slug)}.webp" '
            f'alt="Обложка: {escape_inline_html(story.title)}">'
            f"<p>{escape_inline_html(story.title)}</p></a>"
            for story, _ in ordered_stories
        )

        epub_buttons: list[str] = []
        ready_notes: list[str] = []
        for story, chs in ordered_stories:
            epub_name = f"orv_{story.slug}_{story.language}.epub"
            title_esc = escape_inline_html(story.title)
            if (output_dir / "downloads" / epub_name).is_file():
                ready_notes.append(f"{title_esc} ({len(chs)} гл.)")
                epub_buttons.append(
                    f'<a href="./downloads/{epub_name}" download="{epub_name}" '
                    f'class="btn btn-primary">{_SVG_DOWNLOAD}'
                    f"<span>Скачать: {title_esc} ({len(chs)} гл.)</span></a>"
                )
            else:
                src_total = source_counts.get(story.slug) if source_counts else None
                hint = f"скоро · 0/{src_total}" if src_total else "скоро"
                epub_buttons.append(
                    f'<span class="btn btn-secondary is-disabled" aria-disabled="true">'
                    f"{_SVG_DOWNLOAD}<span>{title_esc} ({hint})</span></span>"
                )

        epub_status_note = (
            "Доступно: " + " · ".join(ready_notes)
            if ready_notes
            else "EPUB ещё не собран (выполните команду build-epub)"
        )

        if len(ordered_stories) > 1:
            short_labels = {
                "orv": "Основная история",
                "cont": "Побочная история",
                "side": "Ваншоты",
            }
            quick_links_html = "".join(
                f'<a href="stories/{escape_inline_html(story.slug)}/index.html" class="link-btn">'
                f'{_SVG_BOOK}<span>{escape_inline_html(short_labels.get(story.slug, story.title))}</span></a>'
                for story, _ in ordered_stories
            )
            credit_line = "Вселенная ORV · Русское издание"
        else:
            quick_links_html = (
                f'<a href="stories/{escape_inline_html(primary_story.slug)}/index.html" class="link-btn">'
                f"{_SVG_LIST}<span>Оглавление</span></a>"
                f'<a href="download.html" class="link-btn">{_SVG_DOWNLOAD}<span>EPUB</span></a>'
                f'<a href="{first_from_root}" class="link-btn">{_SVG_PLAY}'
                f"<span>{escape_inline_html(first_ch_label)}</span></a>"
            )
            credit_line = f"{primary_story.title} · Русское издание"

        primary_epub = f"orv_{primary_story.slug}_{primary_story.language}.epub"
        mapping = {
            "STORY_SLUG": escape_inline_html(primary_story.slug),
            "STORY_TITLE": escape_inline_html(primary_story.title),
            "STORY_AUTHOR": escape_inline_html(primary_story.author),
            "FIRST_CHAPTER_FROM_ROOT": first_from_root,
            "EPUB_FILENAME": primary_epub,
            "EPUB_HREF": f"./downloads/{primary_epub}",
            "EPUB_STATUS_NOTE": epub_status_note,
            "EPUB_BUTTONS_HTML": "".join(epub_buttons),
            "STORY_CARDS_HTML": cards_html,
            "QUICK_LINKS_HTML": quick_links_html,
            "CREDIT_LINE": escape_inline_html(credit_line),
        }

        landing_tpl = (templates_dir / "landing.html").read_text(encoding="utf-8")
        (output_dir / "index.html").write_text(
            _apply_placeholders(landing_tpl, mapping),
            encoding="utf-8",
        )

        download_tpl = (templates_dir / "download.html").read_text(encoding="utf-8")
        (output_dir / "download.html").write_text(
            _apply_placeholders(download_tpl, mapping),
            encoding="utf-8",
        )

        not_found_path = templates_dir / "404.html"
        if not_found_path.is_file():
            not_found_tpl = not_found_path.read_text(encoding="utf-8")
            (output_dir / "404.html").write_text(
                _apply_placeholders(not_found_tpl, mapping),
                encoding="utf-8",
            )

        stories_dir = output_dir / "stories"
        stories_dir.mkdir(parents=True, exist_ok=True)
        stories_tpl = (templates_dir / "stories.html").read_text(encoding="utf-8")
        (stories_dir / "index.html").write_text(
            _apply_placeholders(stories_tpl, mapping),
            encoding="utf-8",
        )

    def _render_story_pages(
        self,
        story: StoryMetadata,
        chapters: list[Chapter],
        templates_dir: Path,
        output_dir: Path,
        *,
        source_chapters: int | None = None,
    ) -> None:
        story_dir = output_dir / "stories" / story.slug
        story_dir.mkdir(parents=True, exist_ok=True)

        first_href = f"./read/ch_{chapters[0].number}.html" if chapters else "#"
        chapter_count_label = (
            f"{len(chapters)} (всего {source_chapters})"
            if source_chapters is not None and source_chapters != len(chapters)
            else str(len(chapters))
        )
        if chapters:
            initial_chapters_html = "".join(
                f'<div class="chapter_item"><a href="./read/ch_{ch.number}.html">'
                f"<p>{escape_inline_html(ch.title)}</p></a></div>"
                for ch in chapters
            )
            read_btn_text = "Читать"
            read_btn_disabled = ""
        else:
            initial_chapters_html = (
                '<div class="chapter_item is-empty">'
                "<p>Перевод первых глав ещё готовится — загляните чуть позже.</p></div>"
            )
            read_btn_text = "Скоро"
            read_btn_disabled = ' disabled aria-disabled="true"'

        synopsis = story.synopsis or (
            "Русское издание новеллы «Точка зрения всеведущего читателя»."
        )
        story_tpl = (templates_dir / "story_index.html").read_text(encoding="utf-8")
        (story_dir / "index.html").write_text(
            _apply_placeholders(
                story_tpl,
                {
                    "STORY_SLUG": escape_inline_html(story.slug),
                    "STORY_TITLE": escape_inline_html(story.title),
                    "STORY_AUTHOR": escape_inline_html(story.author),
                    "STORY_STATUS": escape_inline_html(story.status),
                    "STORY_SYNOPSIS": escape_inline_html(synopsis),
                    "CHAPTER_COUNT": chapter_count_label,
                    "FIRST_CHAPTER_HREF": first_href,
                    "READ_BTN_TEXT": read_btn_text,
                    "READ_BTN_DISABLED_ATTR": read_btn_disabled,
                    "INITIAL_CHAPTER_ITEMS": initial_chapters_html,
                },
            ),
            encoding="utf-8",
        )

        read_dir = story_dir / "read"
        read_dir.mkdir(parents=True, exist_ok=True)
        if chapters:
            self._render_chapters(story, chapters, templates_dir, read_dir)

    def _render_chapters(
        self,
        story: StoryMetadata,
        chapters: list[Chapter],
        templates_dir: Path,
        read_dir: Path,
    ) -> None:
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
