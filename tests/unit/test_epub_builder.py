import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from orv_ru.domain.blocks import (
    CoverBlock,
    ImageBlock,
    NoticeBlock,
    ParagraphBlock,
    SystemWindowBlock,
)
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import StoryMetadata
from orv_ru.rendering import AssetResolver, EpubBookBuilder


def test_epub_builder_spec_compliance_and_strict_xml(tmp_path: Path) -> None:
    images_dir = tmp_path / "imgs"
    images_dir.mkdir()
    (images_dir / "cover.jpg").write_bytes(b"jpg-bytes")

    story = StoryMetadata(
        slug="cont",
        title="Побочная история <Тест>",
        original_title="ORV Sequel",
        author="Sing Shong",
        language="ru",
        status="Онгоинг",
    )
    chapters = [
        Chapter(
            number=553,
            title="553 Пролог & Начало",
            blocks=(
                CoverBlock("cover.jpg", "Обложка"),
                ParagraphBlock("Текст с <Звёздным Потоком><br>и переносом."),
                NoticeBlock("[1] Пояснение к тексту"),
                SystemWindowBlock(("<!>[Окно]", "Строка")),
                ImageBlock("missing.png", "Отсутствующая картинка"),
            ),
        )
    ]

    epub_path = tmp_path / "out" / "book.epub"
    report = EpubBookBuilder(AssetResolver(images_dir)).build(story, chapters, epub_path)

    assert report.chapters_built == 1
    assert report.assets_embedded == 1
    assert report.missing_assets == ("missing.png",)
    assert epub_path.is_file()

    with zipfile.ZipFile(epub_path, "r") as zf:
        names = zf.namelist()
        # EPUB spec: mimetype MUST be first and uncompressed
        assert names[0] == "mimetype"
        mime_info = zf.getinfo("mimetype")
        assert mime_info.compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == b"application/epub+zip"

        # Every XML / XHTML file inside the EPUB must parse strictly
        for name in names:
            if name.endswith((".xml", ".opf", ".ncx", ".xhtml")):
                ET.fromstring(zf.read(name))

        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "<dc:language>ru</dc:language>" in opf
        assert 'href="images/cover.jpg"' in opf
        assert "missing.png" not in opf

        ch_xhtml = zf.read("OEBPS/ch_553.xhtml").decode("utf-8")
        assert "Пояснение к тексту" in ch_xhtml
        assert 'epub:type="endnotes"' in ch_xhtml
        assert "[Отсутствующая картинка]" in ch_xhtml
