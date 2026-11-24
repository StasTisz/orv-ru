from orv_ru.domain.blocks import (
    BlankLineBlock,
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
from orv_ru.rendering.html_blocks import HtmlBlockRenderer


def test_render_all_block_kinds_and_chapter_body() -> None:
    ch = Chapter(
        number=553,
        title="553 Пролог & <Тест>",
        blocks=(
            CoverBlock("cover 553.jpg", "Обложка"),
            ParagraphBlock("Обычный <Звёздный Поток> абзац."),
            SystemMessageBlock("[Навык активирован!]"),
            ConstellationBlock("[Созвездие наблюдает]"),
            OuterGodBlock("【Внешний Бог】"),
            QuoteBlock("「Цитата」<br>— Автор"),
            NoticeBlock("Примечание переводчика"),
            ListBlock("Пункт списка"),
            SystemWindowBlock(("<!>[Сценарий #1]", "Условие: Выжить")),
            GenericBoxBlock(("Рамка", "")),
            ImageBlock("art 1.png", "Арт"),
            DividerBlock(),
            BlankLineBlock(),
        ),
    )

    renderer = HtmlBlockRenderer()
    cover_html, body_html = renderer.render_chapter_body(ch, words_per_minute=250)

    assert '<div class="orv_cover"><img src="../../../assets/images/cover%20553.jpg"' in cover_html
    assert "<h1>553 Пролог &amp; &lt;Тест&gt;</h1>" in body_html
    assert '<p class="orv_line">Обычный &lt;Звёздный Поток&gt; абзац.</p>' in body_html
    assert '<div class="orv_system"><p>[Навык активирован!]</p></div>' in body_html
    assert '<div class="orv_constellation"><p>[Созвездие наблюдает]</p></div>' in body_html
    assert '<div class="orv_outergod"><p>【Внешний Бог】</p></div>' in body_html
    assert '<div class="orv_quote"><p>「 Цитата 」<br>— Автор</p></div>' in body_html
    assert '<div class="orv_notice"><p>Примечание переводчика</p></div>' in body_html
    assert '<ul class="orv_list"><li>Пункт списка</li></ul>' in body_html
    assert '<h3 class="orv_window_title">[Сценарий #1]</h3>' in body_html
    assert '<div class="orv_box">\n<p>Рамка</p>' in body_html
    assert '<div class="orv_image"><img src="../../../assets/images/art%201.png"' in body_html
    # Trailing blank/divider stripped and canonical <br>\n<hr> appended
    assert body_html.endswith("<br>\n<hr>")
