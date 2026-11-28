"""Black-box #4: Glossary, protected payload export/import, chunker, and LLM pipeline."""

from orv_ru.translation.chunker import ChapterChunker, TranslationChunk
from orv_ru.translation.clients import (
    GeminiLLMClient,
    OpenAICompatibleLLMClient,
    extract_json_object,
)
from orv_ru.translation.exceptions import (
    LLMClientError,
    TranslationError,
    TranslationValidationError,
)
from orv_ru.translation.glossary import Glossary, GlossaryLoader
from orv_ru.translation.glossary_checker import GlossaryChecker
from orv_ru.translation.packet import (
    TranslatableItem,
    TranslatedItem,
    TranslatedPayload,
    TranslationPacket,
    apply_payload,
    estimate_packet_tokens,
    extract_packet,
)
from orv_ru.translation.pipeline import ChapterTranslationPipeline
from orv_ru.translation.prompt_builder import PromptBuilder

__all__ = [
    "ChapterChunker",
    "ChapterTranslationPipeline",
    "GeminiLLMClient",
    "Glossary",
    "GlossaryChecker",
    "GlossaryLoader",
    "LLMClientError",
    "OpenAICompatibleLLMClient",
    "PromptBuilder",
    "TranslatableItem",
    "TranslatedItem",
    "TranslatedPayload",
    "TranslationChunk",
    "TranslationError",
    "TranslationPacket",
    "TranslationValidationError",
    "apply_payload",
    "estimate_packet_tokens",
    "extract_json_object",
    "extract_packet",
]
