from pathlib import Path

import pytest

from orv_ru.domain.blocks import CoverBlock, ImageBlock, NoticeBlock, QuoteBlock
from orv_ru.parsing.parser import OrvMarkupParser
from orv_ru.parsing.serializer import OrvMarkupSerializer
from orv_ru.parsing.validator import StructuralValidator
from orv_ru.storage.fs_repository import FileSystemChapterRepository

CORPUS_DIR = Path(__file__).resolve().parents[3] / "reference-orv-reader" / "chapters" / "cont"


@pytest.mark.skipif(
    not CORPUS_DIR.is_dir(),
    reason="Local reference-orv-reader/chapters/cont corpus is not present.",
)
def test_full_cont_corpus_parse_roundtrip_and_validation() -> None:
    parser = OrvMarkupParser()
    serializer = OrvMarkupSerializer()
    validator = StructuralValidator()
    repo = FileSystemChapterRepository(CORPUS_DIR, parser, serializer)

    numbers = repo.list_chapter_numbers()
    assert len(numbers) == 516
    assert numbers[0] == 553
    assert numbers[-1] == 1068
    assert numbers == list(range(553, 1069))

    chapters = repo.load_all()
    assert len(chapters) == 516

    for ch in chapters:
        # 1. Intrinsic validation has zero errors across all 516 chapters
        intrinsic = validator.validate_chapter(ch)
        assert intrinsic.is_valid, f"Chapter {ch.number} failed: {intrinsic.errors}"

        # 2. Canonical serialization round-trip preserves exact AST equality
        reparsed = parser.parse(ch.number, serializer.serialize(ch), source_name=ch.source_name)
        assert reparsed == ch, f"Round-trip mismatch in chapter {ch.number}"

        # 3. Identity translation check passes with zero errors
        identity_report = validator.validate_translation(ch, ch)
        assert identity_report.is_valid

    # Spot-check real edge-case chapters
    by_num = {ch.number: ch for ch in chapters}

    ch553 = by_num[553]
    assert ch553.cover == CoverBlock("Cover Part 6 - 553.jpg", "")
    assert any(isinstance(b, NoticeBlock) for b in ch553.blocks)

    ch762 = by_num[762]
    assert isinstance(ch762.blocks[0], QuoteBlock)
    assert "Mass Production Maker" in ch762.blocks[0].text

    ch795 = by_num[795]
    assert ch795.cover == CoverBlock("Cover Part 7 - 795.jpg", "")
    assert any(isinstance(b, ImageBlock) for b in ch795.blocks)

    ch1068 = by_num[1068]
    assert ch1068.word_count > 1000
