"""Black-box #1: ORV markup parsing, canonical serialization, and structural validation."""

from orv_ru.parsing.exceptions import MarkupParseError
from orv_ru.parsing.parser import OrvMarkupParser
from orv_ru.parsing.serializer import OrvMarkupSerializer
from orv_ru.parsing.validator import StructuralValidator

__all__ = [
    "MarkupParseError",
    "OrvMarkupParser",
    "OrvMarkupSerializer",
    "StructuralValidator",
]
