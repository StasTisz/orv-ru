import json
from pathlib import Path

from orv_ru.domain.blocks import CoverBlock, ImageBlock, ParagraphBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import StoryMetadata
from orv_ru.rendering import AssetResolver, HtmlBlockRenderer, StaticSiteBuilder


def _make_sample_story() -> tuple[StoryMetadata, list[Chapter]]:
    story = StoryMetadata(
        slug="cont",
        title="Побочная история",
        original_title="ORV Sequel",
        author="Sing Shong",
        language="ru",
        status="Онгоинг",
    )
    chapters = [
        Chapter(
            number=553,
            title="553 Пролог",
            blocks=(CoverBlock("cover.jpg", ""), ParagraphBlock("Первая глава.")),
        ),
        Chapter(
            number=554,
            title="554 Эпизод 1",
            blocks=(ImageBlock("art.jpeg", "Арт"), ParagraphBlock("Вторая глава.")),
        ),
    ]
    return story, chapters


def test_site_builder_outputs_pages_meta_and_assets_with_extension_fallback(
    tmp_path: Path,
) -> None:
    images_dir = tmp_path / "src_images"
    images_dir.mkdir()
    (images_dir / "cover.jpg").write_bytes(b"fake-jpg")
    # Real .jpg on disk, requested as .jpeg (like ch 844 in reference corpus)
    (images_dir / "art.jpg").write_bytes(b"fake-art-jpg")

    project_root = Path(__file__).resolve().parents[2]
    web_dir = project_root / "web"
    story, chapters = _make_sample_story()

    out_dir = tmp_path / "site_out"
    builder = StaticSiteBuilder(
        web_dir=web_dir,
        block_renderer=HtmlBlockRenderer(),
        asset_resolver=AssetResolver(images_dir),
    )
    report = builder.build(story, chapters, out_dir)

    assert report.chapters_built == 2
    assert report.assets_copied == 2
    assert report.missing_assets == ()

    assert (out_dir / "index.html").is_file()
    assert (out_dir / "download.html").is_file()
    assert (out_dir / "404.html").is_file()
    assert (out_dir / "stories" / "index.html").is_file()
    assert (out_dir / "stories" / "cont" / "index.html").is_file()
    assert (out_dir / "assets" / "manifest.json").is_file()
    assert (out_dir / "assets" / "css" / "reader.css").is_file()
    assert (out_dir / "assets" / "css" / "stories.css").is_file()
    assert (out_dir / "assets" / "js" / "reader.js").is_file()
    assert (out_dir / "assets" / "images" / "cover.jpg").is_file()
    assert (out_dir / "assets" / "images" / "art.jpeg").is_file()

    ch553_html = (out_dir / "stories" / "cont" / "read" / "ch_553.html").read_text(encoding="utf-8")
    ch554_html = (out_dir / "stories" / "cont" / "read" / "ch_554.html").read_text(encoding="utf-8")
    assert 'href="./ch_554.html"' in ch553_html
    assert 'href="../index.html"' in ch553_html
    assert 'href="./ch_553.html"' in ch554_html
    assert "<svg" in ch553_html
    assert "←" not in ch553_html and "→" not in ch553_html

    meta_list = json.loads((out_dir / "meta" / "cont.json").read_text(encoding="utf-8"))
    assert [m["href"] for m in meta_list] == ["ch_553.html", "ch_554.html"]
    meta_info = json.loads((out_dir / "meta" / "cont_meta.json").read_text(encoding="utf-8"))
    assert meta_info["chapters"] == 2
    assert meta_info["language"] == "ru"


def test_site_builder_copies_branding_media_without_slop_placeholders(tmp_path: Path) -> None:
    images_dir = tmp_path / "src_images"
    images_dir.mkdir()
    (images_dir / "cover.jpg").write_bytes(b"fake-jpg")
    (images_dir / "art.jpg").write_bytes(b"fake-art-jpg")

    branding_dir = tmp_path / "branding"
    (branding_dir / "covers").mkdir(parents=True)
    for name in (
        "background-stars.avif",
        "background-stars.jpg",
        "background-stars-mobile.jpg",
        "od-stigma.webp",
        "favicon.ico",
        "icon512_rounded.png",
        "icon512_maskable.png",
    ):
        (branding_dir / name).write_bytes(b"media-bytes")
    (branding_dir / "covers" / "cont.webp").write_bytes(b"cover-webp")

    project_root = Path(__file__).resolve().parents[2]
    web_dir = project_root / "web"
    story, chapters = _make_sample_story()

    out_dir = tmp_path / "site_branded"
    builder = StaticSiteBuilder(
        web_dir=web_dir,
        block_renderer=HtmlBlockRenderer(),
        asset_resolver=AssetResolver(images_dir),
        branding_dir=branding_dir,
    )
    report = builder.build(story, chapters, out_dir)

    # Branding assets do not inflate chapter-illustration count
    assert report.assets_copied == 2

    media_dir = out_dir / "assets" / "media"
    assert (media_dir / "background-stars.avif").is_file()
    assert (media_dir / "od-stigma.webp").is_file()
    assert (media_dir / "favicon.ico").is_file()
    assert (media_dir / "covers" / "cont.webp").is_file()

    for html_file in out_dir.rglob("*.html"):
        text = html_file.read_text(encoding="utf-8")
        assert "emblem.svg" not in text
        assert "cover-placeholder.svg" not in text


def test_site_builder_builds_three_story_tabs_with_empty_states(tmp_path: Path) -> None:
    images_dir = tmp_path / "src_images"
    images_dir.mkdir()
    branding_dir = tmp_path / "branding"
    (branding_dir / "covers").mkdir(parents=True)
    for slug in ("orv", "cont", "side"):
        (branding_dir / "covers" / f"{slug}.webp").write_bytes(b"cover-bytes")

    epub_dir = tmp_path / "epubs"
    epub_dir.mkdir()
    (epub_dir / "orv_cont_ru.epub").write_bytes(b"fake-epub")

    orv_meta = StoryMetadata("orv", "Основная история", "ORV", "Sing Shong", "ru", "Завершён", "Синопсис 1")
    cont_meta = StoryMetadata("cont", "Побочная история", "ORV Sequel", "Sing Shong", "ru", "Онгоинг", "Синопсис 2")
    side_meta = StoryMetadata("side", "Ваншоты", "One Shots", "Sing Shong", "ru", "Завершён", "Синопсис 3")

    cont_ch = Chapter(number=553, title="553 Пролог", blocks=(ParagraphBlock("Текст."),))

    builder = StaticSiteBuilder(
        web_dir=Path(__file__).resolve().parents[2] / "web",
        block_renderer=HtmlBlockRenderer(),
        asset_resolver=AssetResolver(images_dir),
        epub_source_dir=epub_dir,
        branding_dir=branding_dir,
    )
    out_dir = tmp_path / "multi_site"
    report = builder.build_collection(
        [(orv_meta, []), (cont_meta, [cont_ch]), (side_meta, [])],
        out_dir,
        primary_slug="cont",
        source_counts={"orv": 551, "cont": 516, "side": 5},
    )

    assert report.chapters_built == 1
    stories_html = (out_dir / "stories" / "index.html").read_text(encoding="utf-8")
    assert 'href="orv/index.html"' in stories_html
    assert 'href="cont/index.html"' in stories_html
    assert 'href="side/index.html"' in stories_html

    orv_index = (out_dir / "stories" / "orv" / "index.html").read_text(encoding="utf-8")
    assert "Синопсис 1" in orv_index
    assert 'disabled aria-disabled="true"' in orv_index
    assert "0 (всего 551)" in orv_index

    download_html = (out_dir / "download.html").read_text(encoding="utf-8")
    assert "./downloads/orv_cont_ru.epub" in download_html
    assert "is-disabled" in download_html

    for slug in ("orv", "cont", "side"):
        assert (out_dir / "assets" / "media" / "covers" / f"{slug}.webp").is_file()
        assert (out_dir / "meta" / f"{slug}.json").is_file()
        assert (out_dir / "meta" / f"{slug}_meta.json").is_file()
