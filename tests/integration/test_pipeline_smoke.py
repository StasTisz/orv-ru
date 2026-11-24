import re
import urllib.parse as urlparse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from orv_ru.domain.story import StoryMetadata
from orv_ru.parsing import OrvMarkupParser, OrvMarkupSerializer
from orv_ru.rendering import AssetResolver, EpubBookBuilder, HtmlBlockRenderer, StaticSiteBuilder
from orv_ru.storage import FileSystemChapterRepository
from orv_ru.translation import ChapterChunker, GlossaryLoader, extract_packet

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REF_ROOT = Path(__file__).resolve().parents[3] / "reference-orv-reader"
CORPUS_DIR = REF_ROOT / "chapters" / "cont"
IMAGES_DIR = REF_ROOT / "website" / "assets" / "images"
BRANDING_DIR = REF_ROOT / "website" / "assets"

_LOCAL_ASSET_ATTR_RE = re.compile(r'(?:src|href)="([^"]+)"')


@pytest.mark.skipif(
    not CORPUS_DIR.is_dir() or not IMAGES_DIR.is_dir() or not BRANDING_DIR.is_dir(),
    reason="Local reference-orv-reader corpus/images/branding are not present.",
)
def test_pipeline_smoke_on_real_edge_case_chapters(tmp_path: Path) -> None:
    repo = FileSystemChapterRepository(CORPUS_DIR, OrvMarkupParser(), OrvMarkupSerializer())
    edge_numbers = [553, 762, 795, 844, 1030, 1068]
    chapters = [repo.load(n) for n in edge_numbers]

    story = StoryMetadata(
        slug="cont",
        title="Побочная история ORV",
        original_title="ORV Sequel",
        author="Sing Shong",
        language="ru",
        status="Онгоинг",
    )
    resolver = AssetResolver(IMAGES_DIR)
    project_web = PROJECT_ROOT / "web"

    site_dir = tmp_path / "site"
    site_report = StaticSiteBuilder(
        web_dir=project_web,
        block_renderer=HtmlBlockRenderer(),
        asset_resolver=resolver,
        branding_dir=BRANDING_DIR,
    ).build(story, chapters, site_dir)

    assert site_report.chapters_built == len(edge_numbers)
    assert site_report.missing_assets == ()
    assert site_report.assets_copied >= 4

    media_dir = site_dir / "assets" / "media"
    for expected_media in (
        media_dir / "background-stars.avif",
        media_dir / "background-stars.jpg",
        media_dir / "od-stigma.webp",
        media_dir / "favicon.ico",
        media_dir / "covers" / "cont.webp",
    ):
        assert expected_media.is_file() and expected_media.stat().st_size > 0

    pages_to_verify = [
        site_dir / "index.html",
        site_dir / "download.html",
        site_dir / "stories" / "index.html",
        site_dir / "stories" / "cont" / "index.html",
        site_dir / "stories" / "cont" / "read" / "ch_553.html",
    ]
    for page in pages_to_verify:
        html_text = page.read_text(encoding="utf-8")
        for target in _LOCAL_ASSET_ATTR_RE.findall(html_text):
            if target.startswith(("http://", "https://", "#", "/", "mailto:")) or "downloads/" in target:
                continue
            resolved = (page.parent / urlparse.unquote(target)).resolve()
            assert resolved.is_file() and resolved.stat().st_size > 0, (
                f"Broken local reference {target!r} in {page}"
            )

    epub_file = tmp_path / "smoke.epub"
    epub_report = EpubBookBuilder(resolver).build(story, chapters, epub_file)
    assert epub_report.chapters_built == len(edge_numbers)
    assert epub_report.missing_assets == ()
    assert epub_report.assets_embedded >= 4

    # Strictly validate all XML/XHTML inside generated EPUB
    with zipfile.ZipFile(epub_file, "r") as zf:
        for name in zf.namelist():
            if name.endswith((".xml", ".opf", ".ncx", ".xhtml")):
                ET.fromstring(zf.read(name))


@pytest.mark.skipif(
    not CORPUS_DIR.is_dir(),
    reason="Local reference-orv-reader corpus is not present.",
)
def test_translation_packet_glossary_and_chunker_on_real_chapters() -> None:
    repo = FileSystemChapterRepository(CORPUS_DIR, OrvMarkupParser(), OrvMarkupSerializer())
    glossary = GlossaryLoader.load(PROJECT_ROOT / "glossary" / "orv_glossary.toml")
    chunker = ChapterChunker(max_chars=3500)

    for num in (553, 762, 1068):
        ch = repo.load(num)
        packet = extract_packet(ch, glossary)
        assert len(packet.items) == len(ch.translatable_blocks())
        assert len(packet.matched_glossary) >= 1
        chunks = chunker.split(packet)
        assert len(chunks) >= 1
        assert chunks[0].include_title is True
