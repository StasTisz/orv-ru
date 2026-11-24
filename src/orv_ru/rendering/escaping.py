"""Safe HTML5/XHTML escaping and Russian text formatting helpers."""

from __future__ import annotations

import html
import re

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BR_PLACEHOLDER = "___ORV_RU_BR_PLACEHOLDER___"
_CONTAINER_MARKERS = ("<!>", "<@>", "<#>", "<&>", "<?>")


def escape_inline_html(text: str, *, xhtml: bool = False) -> str:
    """Escape HTML/XML characters while preserving inline `<br>` line-break tags.

    Any ORV-specific angle-bracket terms (e.g. `<Star Stream>`, `<Olympus>`) and
    ampersands are escaped safely so neither HTML5 nor strict XHTML breaks.
    """
    with_placeholders = _BR_RE.sub(_BR_PLACEHOLDER, text)
    escaped = html.escape(with_placeholders, quote=True)
    br_tag = "<br/>" if xhtml else "<br>"
    return escaped.replace(_BR_PLACEHOLDER, br_tag)


def clean_container_line(line: str) -> str:
    """Strip accidental raw inline markers (e.g. `<!>`) inside `+`/`++` container blocks."""
    stripped = line.lstrip()
    for marker in _CONTAINER_MARKERS:
        if stripped.startswith(marker):
            return stripped[len(marker) :]
    return line


def format_ru_words(count: int) -> str:
    """Format a word count with spaces and correct Russian pluralization."""
    formatted_num = f"{count:,}".replace(",", " ")
    mod100 = count % 100
    mod10 = count % 10
    if 11 <= mod100 <= 14:
        noun = "слов"
    elif mod10 == 1:
        noun = "слово"
    elif 2 <= mod10 <= 4:
        noun = "слова"
    else:
        noun = "слов"
    return f"{formatted_num} {noun}"
