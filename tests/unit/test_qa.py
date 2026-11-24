import json
from pathlib import Path

from orv_ru.app.cli import main
from orv_ru.domain.blocks import (
    NoticeBlock,
    OuterGodBlock,
    ParagraphBlock,
    QuoteBlock,
    SystemMessageBlock,
    SystemWindowBlock,
)
from orv_ru.domain.chapter import Chapter
from orv_ru.qa import QualityAuditor, TypographyAutoFixer, build_suspects_payload


def test_quality_auditor_detects_typography_brackets_calques_and_omissions() -> None:
    src = Chapter(
        number=10,
        title="Ch 10 — Test",
        blocks=(
            ParagraphBlock("“Hello,” she said."),
            ParagraphBlock("He used [Breaking the Sky Sword Aura] now."),
            QuoteBlock("「Look at me」"),
            ParagraphBlock("*Amazing* move."),
            ParagraphBlock('"Wait here," he muttered.'),
            ParagraphBlock("This sentence has more than forty five characters for length parity check."),
            ParagraphBlock("First sentence. Second sentence. Third sentence is definitely important."),
            ParagraphBlock("I can't do that right now."),
            ParagraphBlock("He saw a dark monster approaching quickly."),
            NoticeBlock("[1] Footnote with Dark Gamer term in English."),
            OuterGodBlock("【Do  not  come  here .】"),
        ),
    )

    dst = Chapter(
        number=10,
        title="Гл 10 - Тест",
        blocks=(
            ParagraphBlock("— Привет.»"),
            ParagraphBlock("Он применил Ауру Меча, Рассекающего Небеса……"),
            QuoteBlock("Смотри на меня"),
            ParagraphBlock("Потрясающий ход."),
            ParagraphBlock("— «Жди». — Он сказал."),
            ParagraphBlock("Коротко."),
            ParagraphBlock("Первое предложение."),
            ParagraphBlock("Я могу сделать это прямо сейчас."),
            ParagraphBlock("Он увидел мечт в этот момент времени and something totally untranslated here."),
            NoticeBlock("[1] Примечание (Dark Gamer: игрок тёмного гейминга)."),
            OuterGodBlock("【Не  при хо ди  сю да .】"),
        ),
    )

    report = QualityAuditor().audit_chapter(dst, src)
    codes_by_block = {(i.block_index, i.code) for i in report.issues}

    assert (None, "HYPHEN_INSTEAD_OF_DASH") in codes_by_block
    assert (0, "AMERICAN_QUOTE_PERIOD") in codes_by_block
    assert (1, "INLINE_SKILL_BRACKET_MISMATCH") in codes_by_block
    assert (1, "ASIAN_OR_BROKEN_ELLIPSIS") in codes_by_block
    assert (2, "INLINE_CORNER_BRACKET_MISMATCH") in codes_by_block
    assert (3, "DROPPED_ITALIC_EMPHASIS") in codes_by_block
    assert (5, "LENGTH_RATIO_TOO_SHORT") in codes_by_block
    assert (6, "SENTENCE_DROP_SUSPECTED") in codes_by_block
    assert (7, "NEGATION_POLARITY_MISMATCH") in codes_by_block
    assert (8, "NON_STANDARD_MECHT") in codes_by_block
    assert (8, "CALQUE_MOMENT_IN_TIME") in codes_by_block
    assert (8, "UNTRANSLATED_LATIN_LEAK") in codes_by_block
    # NoticeBlock is exempt from untranslated latin prose leak warnings
    assert not any(i.block_index == 9 for i in report.issues)
    # OuterGodBlock preserves deliberate multi-spaces
    assert not any(i.block_index == 10 and i.code == "EXTRA_WHITESPACE" for i in report.issues)


def test_quality_auditor_detects_dangling_tag_repetition_and_allows_ellipsis_quote() -> None:
    src = Chapter(
        number=11,
        title="Ch 11",
        blocks=(
            ParagraphBlock('"Really?"'),
            ParagraphBlock("Lee Jihye muttered."),
            ParagraphBlock('“Maybe...”'),
            SystemMessageBlock("[System]"),
        ),
    )
    dst = Chapter(
        number=11,
        title="Гл 11",
        blocks=(
            ParagraphBlock("— Правда?"),
            ParagraphBlock("Пробормотала Ли Джихё."),
            ParagraphBlock("«Может быть...» и они оба оба замолчали."),
            SystemMessageBlock("[Система]"),
        ),
    )

    report = QualityAuditor().audit_chapter(dst, src)
    codes = {i.code for i in report.issues}
    assert "DANGLING_DIALOGUE_TAG" in codes
    assert "REPEATED_ADJACENT_WORD" in codes
    # Legitimate ellipsis before closing chevron (`...»`) must NOT trigger AMERICAN_QUOTE_PERIOD
    assert "AMERICAN_QUOTE_PERIOD" not in codes


def test_typography_auto_fixer_fixes_mechanical_bugs_and_preserves_br() -> None:
    src = Chapter(
        number=12,
        title="Ch 12 — Start",
        blocks=(
            ParagraphBlock('"Wait," she said.'),
            QuoteBlock("First<br>Second"),
            OuterGodBlock("【Spaced  text】"),
            SystemWindowBlock(("[Title]", "Line 1")),
        ),
    )
    dst = Chapter(
        number=12,
        title="Гл 12 - Начало",
        blocks=(
            ParagraphBlock('- "Подожди," сказал он……<br>— Вот так.»  '),
            QuoteBlock('  «Слова...»<br>- Ответ.'),
            OuterGodBlock("【Разреженный  текст】"),
            SystemWindowBlock(("[Заголовок]", "— Пункт один.")),
        ),
    )

    res = TypographyAutoFixer().fix_chapter(dst, src)
    assert len(res.changes) >= 3
    assert res.chapter.title == "Гл 12 — Начало"
    assert res.chapter.blocks[0].plain_text() == "— «Подожди,» сказал он…<br>— Вот так»."
    assert res.chapter.blocks[1].plain_text() == "«Слова...»<br>— Ответ."
    # Deliberate source spacing in OuterGodBlock must stay untouched
    assert res.chapter.blocks[2].plain_text() == "【Разреженный  текст】"


def test_build_suspects_payload_contains_only_flagged_blocks_with_context() -> None:
    src = Chapter(
        number=5,
        title="Ch 5",
        blocks=(
            ParagraphBlock("Previous line."),
            ParagraphBlock("I can't run away."),
            ParagraphBlock("Next line."),
        ),
    )
    dst = Chapter(
        number=5,
        title="Гл 5",
        blocks=(
            ParagraphBlock("Предыдущая строка."),
            ParagraphBlock("Я могу убежать."),
            ParagraphBlock("Следующая строка."),
        ),
    )
    rep = QualityAuditor().audit_chapter(dst, src)
    payload = build_suspects_payload(story_slug="side", chapter_pairs=[(dst, src, rep)])
    assert payload["suspect_count"] == 1
    item = payload["suspects"][0]
    assert item["block_index"] == 1
    assert item["prev_context"] == "Предыдущая строка."
    assert item["next_context"] == "Следующая строка."
    assert item["issues"][0]["code"] == "NEGATION_POLARITY_MISMATCH"


def test_cli_audit_fix_and_import_auto_fix(tmp_path: Path, capsys) -> None:
    src_dir = tmp_path / "src"
    tr_dir = tmp_path / "tr"
    img_dir = tmp_path / "img"
    src_dir.mkdir()
    tr_dir.mkdir()
    img_dir.mkdir()
    (tmp_path / "web").symlink_to(Path(__file__).resolve().parents[2] / "web")

    (src_dir / "1.txt").write_text("<title>Ch 1\n\"Hello.\"\n", encoding="utf-8")
    (src_dir / "2.txt").write_text("<title>Ch 2\n\"World.\"\n", encoding="utf-8")
    (tr_dir / "1.txt").write_text("<title>Гл 1\n«Привет.»\n", encoding="utf-8")

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f"""[story]
slug = "side"
title = "Ваншоты"
original_title = "Side"
author = "Sing Shong"
language = "ru"
status = "Завершён"

[paths]
source_chapters = "{src_dir}"
translated_chapters = "{tr_dir}"
assets_images = "{img_dir}"
glossary = "glossary/orv_glossary.toml"
site_output = "{tmp_path / 'site'}"
epub_output = "{tmp_path / 'epub'}"

[reader]
words_per_minute = 250
default_theme = "dark"
""",
        encoding="utf-8",
    )

    suspects_file = tmp_path / "suspects.json"
    # Before --fix, --strict should fail with warning on `.»`
    assert main(["--config", str(cfg), "audit", "--strict", "--export-suspects", str(suspects_file), "--json"]) == 1
    audit_res = json.loads(capsys.readouterr().out)
    assert audit_res["warning_count"] == 1
    assert suspects_file.is_file()
    assert json.loads(suspects_file.read_text(encoding="utf-8"))["suspect_count"] == 1

    # With --fix and --strict, `.»` is auto-fixed to `».` and passes cleanly
    assert main(["--config", str(cfg), "audit", "--fix", "--strict", "--json"]) == 0
    fixed_res = json.loads(capsys.readouterr().out)
    assert fixed_res["fixes_count"] == 1
    assert fixed_res["warning_count"] == 0
    assert "«Привет»." in (tr_dir / "1.txt").read_text(encoding="utf-8")

    # import-translation --auto-fix cleans straight quotes before saving chapter 2
    payload_2 = tmp_path / "p2.json"
    payload_2.write_text(
        json.dumps({"chapter_number": 2, "title": "Гл 2", "items": [{"block_index": 0, "lines": ['"Мир."']}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert main(["--config", str(cfg), "import-translation", "2", str(payload_2), "--auto-fix", "--json"]) == 0
    imp_res = json.loads(capsys.readouterr().out)
    assert imp_res["accepted"] is True
    assert len(imp_res["qa_fixes"]) >= 1
    assert "«Мир»." in (tr_dir / "2.txt").read_text(encoding="utf-8")
