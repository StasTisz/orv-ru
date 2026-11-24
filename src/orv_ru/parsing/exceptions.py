"""Parsing-specific exceptions with file and line diagnostics."""

from __future__ import annotations


class MarkupParseError(ValueError):
    """Raised when raw chapter text violates ORV markup syntax."""

    def __init__(
        self,
        message: str,
        *,
        line_number: int | None = None,
        source_name: str | None = None,
    ) -> None:
        self.message = message
        self.line_number = line_number
        self.source_name = source_name
        location_parts: list[str] = []
        if source_name:
            location_parts.append(source_name)
        if line_number is not None:
            location_parts.append(f"line {line_number}")
        prefix = f"[{': '.join(location_parts)}] " if location_parts else ""
        super().__init__(f"{prefix}{message}")
