"""TOML glossary loader and trie-compiled single-pass term matcher."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import GlossaryEntry


def normalize_source_text(text: str) -> str:
    """Normalize typographic apostrophes (`’`, `‘`) to ASCII `'` for consistent matching."""
    if "’" in text or "‘" in text:
        return text.replace("’", "'").replace("‘", "'")
    return text


@lru_cache(maxsize=512)
def compile_source_pattern(source: str) -> re.Pattern[str]:
    """Compile a cached case-insensitive matcher for a single glossary term."""
    norm = normalize_source_text(source)
    escaped = re.escape(norm)
    if norm and norm[0].isalnum() and norm[-1].isalnum():
        return re.compile(rf"\b{escaped}\b", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def _trie_to_regex(words: list[str]) -> str:
    """Compile a list of lowercased terms into a prefix-merged regex trie.

    Python's `re` is an NFA engine: a flat 240-branch `A|B|C|...` alternation costs
    O(N * M) backtracking per character, whereas a merged prefix trie dispatches in
    O(1) per character (~50x faster on 14 MB corpora).
    """
    root: dict[str | None, Any] = {}
    for word in words:
        node = root
        for ch in word:
            node = node.setdefault(ch, {})
        node[None] = True

    def _emit(node: dict[str | None, Any]) -> str:
        has_end = None in node
        children = [(k, v) for k, v in node.items() if k is not None]
        if not children:
            return ""
        parts = [re.escape(ch) + _emit(sub) for ch, sub in sorted(children)]
        expr = parts[0] if len(parts) == 1 else f"(?:{'|'.join(parts)})"
        # Greedy `(?:...)?` enforces longest-first matching when a term is a prefix of another.
        return f"(?:{expr})?" if has_end else expr

    return _emit(root)


@dataclass(frozen=True)
class _CompiledGlossaryIndex:
    """Single-pass longest-first trie index across all glossary entries."""

    pattern: re.Pattern[str] | None
    normalized_keys: tuple[str, ...]


def _build_index(entries: tuple[GlossaryEntry, ...]) -> _CompiledGlossaryIndex:
    if not entries:
        return _CompiledGlossaryIndex(pattern=None, normalized_keys=())

    keys_in_order = tuple(normalize_source_text(entry.source).lower() for entry in entries)
    unique_keys = sorted(set(keys_in_order))

    word_bounded = [k for k in unique_keys if k and k[0].isalnum() and k[-1].isalnum()]
    unbounded = [k for k in unique_keys if k and not (k[0].isalnum() and k[-1].isalnum())]

    branches: list[str] = []
    if unbounded:
        branches.append(_trie_to_regex(unbounded))
    if word_bounded:
        branches.append(rf"\b{_trie_to_regex(word_bounded)}\b")

    pattern = re.compile("|".join(branches)) if branches else None
    return _CompiledGlossaryIndex(pattern=pattern, normalized_keys=keys_in_order)


@dataclass(frozen=True)
class Glossary:
    """Immutable collection of ORV terminology entries and translation rules."""

    entries: tuple[GlossaryEntry, ...] = ()
    rules: dict[str, str] = field(default_factory=dict)
    _index_cache: _CompiledGlossaryIndex | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def _get_index(self) -> _CompiledGlossaryIndex:
        if self._index_cache is None:
            object.__setattr__(self, "_index_cache", _build_index(self.entries))
            assert self._index_cache is not None
        return self._index_cache

    def find_in_text(self, text: str) -> tuple[GlossaryEntry, ...]:
        """Find all matching glossary entries in `text` using a single trie regex pass."""
        index = self._get_index()
        if index.pattern is None or not text:
            return ()

        normalized_lower = normalize_source_text(text).lower()
        found_keys = {match.group(0) for match in index.pattern.finditer(normalized_lower)}
        if not found_keys:
            return ()

        matched: list[GlossaryEntry] = []
        seen: set[str] = set()
        for entry, norm_key in zip(self.entries, index.normalized_keys, strict=True):
            if norm_key in found_keys and norm_key not in seen:
                matched.append(entry)
                seen.add(norm_key)
        return tuple(matched)

    def match_relevant(self, chapter: Chapter) -> tuple[GlossaryEntry, ...]:
        """Return entries whose `source` appears in the chapter's translatable text."""
        parts = [chapter.title]
        parts.extend(block.plain_text() for _, block in chapter.translatable_blocks())
        return self.find_in_text("\n".join(parts))

    def format_for_prompt(self, entries: tuple[GlossaryEntry, ...]) -> str:
        """Render rules and matched glossary entries into concise prompt instructions."""
        lines: list[str] = []
        if self.rules:
            lines.append("Общие правила перевода:")
            for key, desc in self.rules.items():
                lines.append(f"- {key}: {desc}")
        if entries:
            if lines:
                lines.append("")
            lines.append("Словарь терминов для этой главы (строго соблюдать):")
            for entry in entries:
                line = f"- {entry.source} -> {entry.target}"
                extras: list[str] = []
                if entry.aliases:
                    extras.append(f"допустимые варианты: {', '.join(entry.aliases)}")
                if entry.forbidden:
                    extras.append(f"ЗАПРЕЩЕНО: {', '.join(entry.forbidden)}")
                if entry.notes:
                    extras.append(entry.notes)
                if extras:
                    line += f" ({'; '.join(extras)})"
                lines.append(line)
        return "\n".join(lines)


class GlossaryLoader:
    """Loads `orv_glossary.toml` dynamically across arbitrary `[[category]]` sections."""

    @staticmethod
    def load(path: Path) -> Glossary:
        with path.open("rb") as f:
            raw = tomllib.load(f)

        rules_raw = raw.get("rules", {})
        rules = (
            {str(k): str(v) for k, v in rules_raw.items()}
            if isinstance(rules_raw, dict)
            else {}
        )

        entries: list[GlossaryEntry] = []
        for category, value in raw.items():
            if category == "rules" or not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source", "")).strip()
                target = str(item.get("target", "")).strip()
                if not source or not target:
                    continue
                aliases = tuple(str(a) for a in item.get("aliases", ()) if str(a).strip())
                forbidden = tuple(str(b) for b in item.get("forbidden", ()) if str(b).strip())
                entries.append(
                    GlossaryEntry(
                        source=source,
                        target=target,
                        category=str(category),
                        notes=str(item.get("notes", "")).strip(),
                        aliases=aliases,
                        forbidden=forbidden,
                    )
                )

        return Glossary(entries=tuple(entries), rules=rules)

    @classmethod
    def load_optional(cls, path: Path) -> Glossary:
        """Load glossary if present, otherwise return an empty `Glossary`."""
        if not path.is_file():
            return Glossary()
        return cls.load(path)
