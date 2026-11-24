"""Black-box #3: Clean-room HTML site builder, EPUB packager, and asset resolver."""

from orv_ru.rendering.assets import AssetResolver
from orv_ru.rendering.epub_builder import EpubBookBuilder
from orv_ru.rendering.escaping import clean_container_line, escape_inline_html, format_ru_words
from orv_ru.rendering.html_blocks import HtmlBlockRenderer
from orv_ru.rendering.site_builder import StaticSiteBuilder

__all__ = [
    "AssetResolver",
    "EpubBookBuilder",
    "HtmlBlockRenderer",
    "StaticSiteBuilder",
    "clean_container_line",
    "escape_inline_html",
    "format_ru_words",
]
