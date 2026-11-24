"""Abstract ports (Protocol interfaces) decoupling domain logic from adapters."""

from orv_ru.ports.parser import ChapterParser, ChapterSerializer
from orv_ru.ports.renderer import (
    BlockRenderer,
    BookBuilder,
    EpubBuildReport,
    SiteBuilder,
    SiteBuildReport,
)
from orv_ru.ports.repository import ChapterReader, ChapterRepository, ChapterWriter
from orv_ru.ports.translator import ChapterTranslator, LLMClient, TranslationResult

__all__ = [
    "BlockRenderer",
    "BookBuilder",
    "ChapterParser",
    "ChapterReader",
    "ChapterRepository",
    "ChapterSerializer",
    "ChapterTranslator",
    "ChapterWriter",
    "EpubBuildReport",
    "LLMClient",
    "SiteBuildReport",
    "SiteBuilder",
    "TranslationResult",
]
