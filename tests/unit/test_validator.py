from orv_ru.domain.blocks import (
    CoverBlock,
    ParagraphBlock,
    QuoteBlock,
    SystemMessageBlock,
    SystemWindowBlock,
)
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.validation import Severity
from orv_ru.parsing.validator import StructuralValidator


def test_validate_chapter_catches_errors_and_warnings() -> None:
    bad = Chapter(
        number=1,
        title="   ",
        blocks=(
            CoverBlock("", ""),
            ParagraphBlock("<!>leaked tag"),
            SystemWindowBlock(("<!>[Nested]", "Line")),
        ),
    )
    report = StructuralValidator().validate_chapter(bad)

    assert not report.is_valid
    error_codes = {i.code for i in report.errors}
    warning_codes = {i.code for i in report.warnings}
    assert {"EMPTY_TITLE", "EMPTY_ASSET_FILENAME"} <= error_codes
    assert {"RAW_TAG_IN_PARAGRAPH", "RAW_TAG_IN_CONTAINER"} <= warning_codes


def test_validate_translation_accepts_valid_russian_translation() -> None:
    src = Chapter(
        number=553,
        title="553 Prologue",
        blocks=(
            CoverBlock("cover.jpg", ""),
            ParagraphBlock("Hello world."),
            QuoteBlock("「Quote」<br>— Author"),
            SystemWindowBlock(("[Title]", "Line 1")),
        ),
    )
    dst = src.with_translated_content(
        title="553 Пролог",
        blocks=(
            CoverBlock("cover.jpg", ""),
            ParagraphBlock("Привет, мир."),
            QuoteBlock("「Цитата」<br>— Автор"),
            SystemWindowBlock(("[Заголовок]", "Строка 1")),
        ),
    )

    report = StructuralValidator().validate_translation(src, dst)
    assert report.is_valid
    assert report.issues == ()


def test_validate_translation_detects_all_structural_regressions() -> None:
    src = Chapter(
        number=553,
        title="553 Prologue",
        blocks=(
            CoverBlock("cover.jpg", ""),
            ParagraphBlock("Hello world."),
            QuoteBlock("「Quote」<br>— Author"),
            SystemWindowBlock(("[Title]", "Line 1")),
            SystemMessageBlock("[System]"),
        ),
    )

    # 1. Block count mismatch
    fewer = src.with_translated_content("553 Пролог", src.blocks[:-1])
    rep_count = StructuralValidator().validate_translation(src, fewer)
    assert "BLOCK_COUNT_MISMATCH" in {i.code for i in rep_count.errors}

    # 2. Mutated cover filename, emptied paragraph, dropped <br>, changed window line count, swapped tag kind
    corrupted = src.with_translated_content(
        title="553 Пролог",
        blocks=(
            CoverBlock("renamed.jpg", ""),
            ParagraphBlock("   "),
            QuoteBlock("「Цитата」 — Автор"),
            SystemWindowBlock(("[Заголовок]",)),
            ParagraphBlock("[Система]"),
        ),
    )
    rep_bad = StructuralValidator().validate_translation(src, corrupted)
    assert not rep_bad.is_valid
    by_idx = {(i.block_index, i.code) for i in rep_bad.errors}
    assert (0, "STRUCTURAL_SIGNATURE_MISMATCH") in by_idx
    assert (1, "EMPTY_TRANSLATED_BLOCK") in by_idx
    assert (2, "STRUCTURAL_SIGNATURE_MISMATCH") in by_idx
    assert (3, "STRUCTURAL_SIGNATURE_MISMATCH") in by_idx
    assert (4, "BLOCK_KIND_MISMATCH") in by_idx
    assert all(i.severity == Severity.ERROR for i in rep_bad.errors)
