"""Deterministic Russian glossary compliance checker with `ё`/`е` and case support."""

from __future__ import annotations

import re
from functools import lru_cache

from orv_ru.domain.chapter import Chapter
from orv_ru.domain.validation import Severity, ValidationIssue, ValidationReport
from orv_ru.translation.glossary import Glossary

_TOKEN_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_ADJ_ENDINGS = ("ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие", "ого", "его", "ому", "ему")
_DECLENSION_SINGLE_ENDINGS = tuple("аяуюеиоыьй")


def _normalize_ru(text: str) -> str:
    lower = text.lower()
    return lower.replace("ё", "е") if "ё" in lower else lower


def _stem_prefix(word: str) -> str:
    lower = _normalize_ru(word)
    if len(lower) >= 5 and lower.endswith(_ADJ_ENDINGS):
        return lower[:-2]
    if len(lower) >= 4 and lower.endswith(_DECLENSION_SINGLE_ENDINGS):
        return lower[:-1]
    return lower


@lru_cache(maxsize=2048)
def _term_stem_plan(term: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    cleaned = _normalize_ru(term.strip())
    tokens = _TOKEN_RE.findall(cleaned)
    plan = tuple((tok, _stem_prefix(tok)) for tok in tokens)
    return cleaned, plan


def _matches_token(token: str, prefix: str, ht: str) -> bool:
    if len(token) < 3:
        return ht == token
    if len(token) == 3:
        return ht == token or (ht.startswith(token) and len(ht) <= 5)
    max_len = len(prefix) + (3 if token.endswith(_ADJ_ENDINGS) else 2)
    return ht.startswith(prefix) and len(ht) <= max_len


def _matches_pretokenized(
    term: str,
    hay_lower: str,
    hay_tokens: tuple[str, ...],
    hay_token_set: frozenset[str],
) -> bool:
    cleaned, plan = _term_stem_plan(term)
    if not cleaned:
        return False
    if cleaned in hay_lower:
        return True
    if not plan or not hay_tokens:
        return False

    n = len(plan)
    if n == 1:
        token, prefix = plan[0]
        return any(_matches_token(token, prefix, ht) for ht in hay_tokens)

    if len(hay_tokens) < n:
        return False

    for i in range(len(hay_tokens) - n + 1):
        window = hay_tokens[i : i + n]
        if all(_matches_token(plan[j][0], plan[j][1], window[j]) for j in range(n)):
            return True

    return False


def matches_russian_term(term: str, haystack: str) -> bool:
    """Check if `term` appears in `haystack`, tolerating Russian case inflections and `ё`/`е`."""
    cleaned = term.strip()
    if not cleaned:
        return False
    hay_lower = _normalize_ru(haystack)
    hay_tokens = tuple(_TOKEN_RE.findall(hay_lower))
    return _matches_pretokenized(cleaned, hay_lower, hay_tokens, frozenset(hay_tokens))


def matches_forbidden_term(
    bad: str,
    haystack: str,
    *,
    canonical_target: str = "",
) -> bool:
    """Match a forbidden variant, using exact boundaries if stem overlaps canonical target."""
    cleaned = bad.strip()
    if not cleaned:
        return False
    if canonical_target and matches_russian_term(cleaned, canonical_target):
        return bool(
            re.search(
                rf"(?<!\w){re.escape(_normalize_ru(cleaned))}(?!\w)",
                _normalize_ru(haystack),
            )
        )
    return matches_russian_term(cleaned, haystack)


class GlossaryChecker:
    """Verifies that translated chapters respect glossary terms and forbidden variants."""

    def check(
        self,
        source: Chapter,
        translated: Chapter,
        glossary: Glossary,
    ) -> ValidationReport:
        """Return a `ValidationReport` of forbidden-term errors and missing-term warnings."""
        if not glossary.entries:
            return ValidationReport(chapter_number=source.number, issues=())

        issues: list[ValidationIssue] = []

        self._check_text_pair(
            src_text=source.title,
            dst_text=translated.title,
            block_index=None,
            glossary=glossary,
            issues=issues,
        )

        if len(source.blocks) == len(translated.blocks):
            for idx, (src_block, dst_block) in enumerate(
                zip(source.blocks, translated.blocks, strict=True)
            ):
                if not src_block.is_translatable or src_block.kind != dst_block.kind:
                    continue
                self._check_text_pair(
                    src_text=src_block.plain_text(),
                    dst_text=dst_block.plain_text(),
                    block_index=idx,
                    glossary=glossary,
                    issues=issues,
                )

        return ValidationReport(chapter_number=source.number, issues=tuple(issues))

    @staticmethod
    def _check_text_pair(
        *,
        src_text: str,
        dst_text: str,
        block_index: int | None,
        glossary: Glossary,
        issues: list[ValidationIssue],
    ) -> None:
        matched_entries = glossary.find_in_text(src_text)
        if not matched_entries:
            return

        dst_lower = _normalize_ru(dst_text)
        dst_tokens = tuple(_TOKEN_RE.findall(dst_lower))
        dst_token_set = frozenset(dst_tokens)

        for entry in matched_entries:
            accepted_forms = (entry.target, *entry.aliases)
            has_accepted = any(
                _matches_pretokenized(form, dst_lower, dst_tokens, dst_token_set)
                for form in accepted_forms
            )
            other_accepted_forms = tuple(
                form
                for other in matched_entries
                if other is not entry
                for form in (other.target, *other.aliases)
            )
            forbidden_hit = next(
                (
                    bad
                    for bad in entry.forbidden
                    if not (
                        has_accepted
                        and any(matches_russian_term(bad, form) for form in other_accepted_forms)
                    )
                    and _matches_forbidden_pretokenized(
                        bad,
                        dst_lower,
                        dst_tokens,
                        dst_token_set,
                        canonical_target=entry.target,
                    )
                ),
                None,
            )
            if forbidden_hit is not None:
                issues.append(
                    ValidationIssue(
                        code="FORBIDDEN_TERM_USED",
                        severity=Severity.ERROR,
                        message=(
                            f"Forbidden translation '{forbidden_hit}' used for "
                            f"'{entry.source}' (expected '{entry.target}')."
                        ),
                        block_index=block_index,
                    )
                )
                continue

            if not has_accepted:
                issues.append(
                    ValidationIssue(
                        code="GLOSSARY_TERM_MISSING",
                        severity=Severity.WARNING,
                        message=(
                            f"Source term '{entry.source}' found, expected '{entry.target}' "
                            "(or alias) in translation."
                        ),
                        block_index=block_index,
                    )
                )


def _matches_forbidden_pretokenized(
    bad: str,
    dst_lower: str,
    dst_tokens: tuple[str, ...],
    dst_token_set: frozenset[str],
    *,
    canonical_target: str,
) -> bool:
    cleaned = bad.strip()
    if not cleaned:
        return False
    if canonical_target and matches_russian_term(cleaned, canonical_target):
        return bool(
            re.search(rf"(?<!\w){re.escape(_normalize_ru(cleaned))}(?!\w)", dst_lower)
        )
    return _matches_pretokenized(cleaned, dst_lower, dst_tokens, dst_token_set)
