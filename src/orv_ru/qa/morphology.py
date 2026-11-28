"""Level 2 Russian morphological & contextual QA checks powered by pymorphy3 and razdel."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from orv_ru.domain.blocks import Block, NoticeBlock, ParagraphBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.validation import Severity, ValidationIssue, ValidationReport

_WORD_RE = re.compile(r"[а-яё]+", re.IGNORECASE)

_OBLIQUE_PREPS = frozenset(
    {
        "у",
        "от",
        "до",
        "для",
        "без",
        "из",
        "к",
        "ко",
        "с",
        "со",
        "о",
        "об",
        "при",
        "перед",
        "после",
        "против",
        "возле",
        "около",
        "вокруг",
        "ради",
        "мимо",
        "кроме",
    }
)

# Common declinable Korean feminine names ending in -а/-я (uninflected forms).
_DEFAULT_DECLINABLE_NAMES = frozenset({"миа", "сана", "хва", "суа", "джиа", "сера", "юра"})

# High-frequency verbs/words where repetition within a short window is idiomatic or harmless.
_TAUTOLOGY_STOP_LEMMAS = frozenset(
    {
        "быть",
        "стать",
        "мочь",
        "хотеть",
        "сказать",
        "говорить",
        "спросить",
        "ответить",
        "думать",
        "знать",
        "видеть",
        "смотреть",
        "посмотреть",
        "делать",
        "сделать",
        "пойти",
        "прийти",
        "время",
        "человек",
        "место",
        "слово",
        "рука",
        "глаз",
        "лицо",
        "сторона",
        "конец",
        "начало",
        "сценарий",
        "история",
        "система",
        "созвездие",
        "читать",
        "читатель",
        "докча",
        "джунхёк",
        "суён",
    }
)

_FORMAL_YOU_RE = re.compile(
    r"\b(?:вы|вам|вас|вами|ваш|ваша|ваше|ваши|вашего|вашему|вашем|вашей|ваших|вашими)\b",
    re.IGNORECASE,
)
_PLURAL_GROUP_YOU_RE = re.compile(
    r"\b(?:вы\s+(?:все|оба|обе|двое|трое|ребята)|вас\s+всех|вам\s+всем)\b",
    re.IGNORECASE,
)
_INFORMAL_YOU_RE = re.compile(
    r"\b(?:ты|тебя|тебе|тобой|тобою|твой|твоя|твоё|твои|твоего|твоему|тво[ёе]м|твоей|твоих|твоими)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _get_nlp_tools() -> tuple[Any, Any, Any] | None:
    """Lazy-load pymorphy3 and razdel, returning None if optional [qa] extras are absent."""
    try:
        import pymorphy3
        import razdel
    except ImportError:
        return None
    return pymorphy3.MorphAnalyzer(), razdel.sentenize, razdel.tokenize


@lru_cache(maxsize=8192)
def _analyze_word(word_lower: str) -> tuple[str, str | None, str | None, frozenset[str]]:
    """Return `(normal_form, pos, gender, cases)` for a lowercase Russian word."""
    tools = _get_nlp_tools()
    if tools is None:
        return word_lower, None, None, frozenset()
    morph = tools[0]
    parsed = morph.parse(word_lower)
    if not parsed:
        return word_lower, None, None, frozenset()
    best = parsed[0]
    cases = frozenset(p.tag.case for p in parsed if p.tag.case is not None)
    return str(best.normal_form), best.tag.POS, best.tag.gender, cases


def _has_clear_fem_adj_sing(word_lower: str) -> bool:
    """Return True if all ADJF parses of `word_lower` are strictly singular feminine."""
    tools = _get_nlp_tools()
    if tools is None:
        return False
    morph = tools[0]
    parsed = morph.parse(word_lower)
    adj_parses = [p for p in parsed if p.tag.POS == "ADJF"]
    if not adj_parses:
        return False
    if any(p.tag.number != "sing" for p in adj_parses):
        return False
    genders = {p.tag.gender for p in adj_parses if p.tag.gender is not None}
    return genders == {"femn"}


def _is_strictly_masc_sing_noun(word_lower: str) -> bool:
    tools = _get_nlp_tools()
    if tools is None:
        return False
    morph = tools[0]
    parsed = morph.parse(word_lower)
    if not parsed:
        return False
    noun_parses = [p for p in parsed if p.tag.POS == "NOUN"]
    if not noun_parses:
        return False
    if any("ms-f" in str(p.tag) or p.tag.number != "sing" for p in noun_parses):
        return False
    genders = {p.tag.gender for p in noun_parses if p.tag.gender is not None}
    return genders == {"masc"}


class MorphologyAuditor:
    """Runs Level 2 Russian morphological checks (cases, agreement, tautologies, register)."""

    def __init__(self, declinable_names: frozenset[str] | None = None) -> None:
        self._declinable_names = declinable_names or _DEFAULT_DECLINABLE_NAMES

    @staticmethod
    def is_available() -> bool:
        """Return True if optional `pymorphy3` and `razdel` packages are installed."""
        return _get_nlp_tools() is not None

    def audit_chapter(self, translated: Chapter) -> ValidationReport:
        """Analyze `translated` chapter blocks using Russian morphology."""
        tools = _get_nlp_tools()
        if tools is None:
            return ValidationReport(chapter_number=translated.number, issues=())

        sentenize = tools[1]
        tokenize = tools[2]
        issues: list[ValidationIssue] = []

        self._check_block_text(
            text=translated.title,
            block_index=None,
            sentenize=sentenize,
            tokenize=tokenize,
            issues=issues,
        )

        last_dialogue_idx: int | None = None
        last_dialogue_register: str | None = None

        for idx, block in enumerate(translated.blocks):
            if not block.is_translatable:
                if idx - (last_dialogue_idx or 0) > 2:
                    last_dialogue_register = None
                continue

            if isinstance(block, NoticeBlock):
                continue

            text = block.plain_text()
            self._check_block_text(
                text=text,
                block_index=idx,
                sentenize=sentenize,
                tokenize=tokenize,
                issues=issues,
            )

            last_dialogue_idx, last_dialogue_register = self._check_dialogue_register(
                block=block,
                idx=idx,
                text=text,
                last_dialogue_idx=last_dialogue_idx,
                last_dialogue_register=last_dialogue_register,
                issues=issues,
            )

        return ValidationReport(chapter_number=translated.number, issues=tuple(issues))

    def _check_block_text(
        self,
        *,
        text: str,
        block_index: int | None,
        sentenize: Any,
        tokenize: Any,
        issues: list[ValidationIssue],
    ) -> None:
        clean = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
        for sent in sentenize(clean):
            tokens = [t.text for t in tokenize(sent.text)]
            self._check_uninflected_names(tokens, block_index, issues)
            self._check_gender_agreement(tokens, block_index, issues)
            self._check_tautologies(tokens, block_index, issues)

    def _check_uninflected_names(
        self,
        tokens: list[str],
        block_index: int | None,
        issues: list[ValidationIssue],
    ) -> None:
        for i, tok in enumerate(tokens):
            low = tok.lower()
            if low not in _OBLIQUE_PREPS:
                continue
            for offset in (1, 2):
                if i + offset >= len(tokens):
                    break
                cand = tokens[i + offset]
                if not cand[:1].isupper():
                    continue
                cand_low = cand.lower()
                if cand_low in self._declinable_names:
                    issues.append(
                        ValidationIssue(
                            code="UNINFLECTED_DECLINABLE_NAME",
                            severity=Severity.WARNING,
                            message=(
                                f"Имя '{cand}' после предлога '{tok}' не просклонено "
                                "(женские имена на -а/-я в русском склоняются)."
                            ),
                            block_index=block_index,
                        )
                    )
                    return

    @staticmethod
    def _check_gender_agreement(
        tokens: list[str],
        block_index: int | None,
        issues: list[ValidationIssue],
    ) -> None:
        for i in range(len(tokens) - 1):
            w1 = tokens[i].lower()
            w2 = tokens[i + 1].lower()
            if not (_WORD_RE.fullmatch(w1) and _WORD_RE.fullmatch(w2)):
                continue

            _, pos1, _, _ = _analyze_word(w1)
            _, pos2, _, _ = _analyze_word(w2)

            # Pattern: feminine singular adjective + strictly masculine singular noun (e.g. "новую менеджер")
            if (
                pos1 == "ADJF"
                and pos2 == "NOUN"
                and not w1.startswith("котор")
                and _has_clear_fem_adj_sing(w1)
                and _is_strictly_masc_sing_noun(w2)
            ):
                issues.append(
                    ValidationIssue(
                        code="GENDER_AGREEMENT_MISMATCH",
                        severity=Severity.WARNING,
                        message=f"Вероятное рассогласование рода: '{tokens[i]} {tokens[i + 1]}'.",
                        block_index=block_index,
                    )
                )
                return

            # Pattern: "[masc noun], которую/которая"
            if (
                i + 3 < len(tokens)
                and tokens[i + 1] == ","
                and tokens[i + 2].lower() in {"которая", "которую", "которой"}
                and _is_strictly_masc_sing_noun(w1)
            ):
                issues.append(
                    ValidationIssue(
                        code="GENDER_AGREEMENT_MISMATCH",
                        severity=Severity.WARNING,
                        message=(
                            f"Рассогласование рода с относительным местоимением: "
                            f"'{tokens[i]}, {tokens[i + 2]}'."
                        ),
                        block_index=block_index,
                    )
                )
                return

    @staticmethod
    def _check_tautologies(
        tokens: list[str],
        block_index: int | None,
        issues: list[ValidationIssue],
    ) -> None:
        content: list[tuple[int, str, str]] = []
        for idx, tok in enumerate(tokens):
            low = tok.lower()
            if len(low) < 5 or not _WORD_RE.fullmatch(low):
                continue
            lemma, pos, _, _ = _analyze_word(low)
            if pos not in {"NOUN", "VERB", "INFN", "ADJF", "ADJS", "ADVB"}:
                continue
            if lemma in _TAUTOLOGY_STOP_LEMMAS or len(lemma) < 5:
                continue
            content.append((idx, tok, lemma[:5]))

        for i in range(len(content)):
            pos_i, raw_i, stem_i = content[i]
            for j in range(i + 1, len(content)):
                pos_j, raw_j, stem_j = content[j]
                if pos_j - pos_i > 4:
                    break
                if raw_i.lower() == raw_j.lower():
                    continue
                if stem_i == stem_j:
                    issues.append(
                        ValidationIssue(
                            code="SAME_ROOT_TAUTOLOGY",
                            severity=Severity.WARNING,
                            message=f"Однокоренная тавтология рядом в предложении: '{raw_i}' ... '{raw_j}'.",
                            block_index=block_index,
                        )
                    )
                    return

    @staticmethod
    def _check_dialogue_register(
        *,
        block: Block,
        idx: int,
        text: str,
        last_dialogue_idx: int | None,
        last_dialogue_register: str | None,
        issues: list[ValidationIssue],
    ) -> tuple[int | None, str | None]:
        if not isinstance(block, ParagraphBlock) or not text.lstrip().startswith("—"):
            if last_dialogue_idx is not None and idx - last_dialogue_idx > 2:
                return None, None
            return last_dialogue_idx, last_dialogue_register

        has_formal = bool(_FORMAL_YOU_RE.search(text)) and not bool(_PLURAL_GROUP_YOU_RE.search(text))
        has_informal = bool(_INFORMAL_YOU_RE.search(text))

        if has_formal and has_informal:
            return idx, None
        current = "formal" if has_formal else ("informal" if has_informal else None)
        if current is None:
            return idx, last_dialogue_register

        if (
            last_dialogue_idx is not None
            and idx - last_dialogue_idx <= 2
            and last_dialogue_register is not None
            and current != last_dialogue_register
        ):
            issues.append(
                ValidationIssue(
                    code="DIALOGUE_REGISTER_SHIFT",
                    severity=Severity.WARNING,
                    message="Резкая смена регистра обращения «вы»/«ты» в соседних репликах диалога.",
                    block_index=idx,
                )
            )
        return idx, current
