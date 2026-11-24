from pathlib import Path

from orv_ru.domain.blocks import ParagraphBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import GlossaryEntry
from orv_ru.translation import Glossary, GlossaryChecker, GlossaryLoader


def test_glossary_loader_supports_arbitrary_categories_and_aliases(tmp_path: Path) -> None:
    toml_path = tmp_path / "glossary.toml"
    toml_path.write_text(
        """[rules]
tone = "Keep sharp dialogue."

[[characters]]
source = "Kim Dokja"
target = "Ким Докча"
aliases = ["Докча"]
notes = "Main protagonist"

[[skills]]
source = "Bookmark"
target = "Закладка"
forbidden = ["Метка"]
""",
        encoding="utf-8",
    )

    glossary = GlossaryLoader.load(toml_path)
    assert glossary.rules["tone"] == "Keep sharp dialogue."
    assert len(glossary.entries) == 2
    assert glossary.entries[1].category == "skills"
    assert glossary.entries[1].forbidden == ("Метка",)

    # Missing file returns empty glossary via load_optional
    assert GlossaryLoader.load_optional(tmp_path / "missing.toml") == Glossary()


def test_glossary_matcher_and_russian_declension_checker() -> None:
    glossary = Glossary(
        entries=(
            GlossaryEntry(
                source="Kim Dokja",
                target="Ким Докча",
                category="characters",
            ),
            GlossaryEntry(
                source="Oldest Dream",
                target="Древнейшая Мечта",
                category="constellations",
                forbidden=("Самый древний сон",),
            ),
        )
    )

    src = Chapter(
        number=553,
        title="553 Kim Dokja",
        blocks=(
            ParagraphBlock("Kim Dokja looked at the Oldest Dream."),
            ParagraphBlock("Nothing special here."),
        ),
    )

    matched = glossary.match_relevant(src)
    assert [e.source for e in matched] == ["Kim Dokja", "Oldest Dream"]

    # Inflected Russian cases ("Кима Докчи", "Древнейшей Мечтой") should pass with 0 warnings
    good_dst = src.with_translated_content(
        title="553 Ким Докча",
        blocks=(
            ParagraphBlock("Взгляд Кима Докчи упал на Древнейшую Мечту."),
            ParagraphBlock("Ничего особенного здесь нет."),
        ),
    )
    checker = GlossaryChecker()
    good_report = checker.check(src, good_dst, glossary)
    assert good_report.is_valid
    assert good_report.issues == ()

    # Forbidden variant ("самый древний сон" / "самом древнем") triggers ERROR; missing target triggers WARNING
    bad_dst = src.with_translated_content(
        title="553 Безымянный",
        blocks=(
            ParagraphBlock("Герой посмотрел на самый древний сон."),
            ParagraphBlock("Ничего особенного."),
        ),
    )
    bad_report = checker.check(src, bad_dst, glossary)
    assert not bad_report.is_valid
    assert any(i.code == "FORBIDDEN_TERM_USED" for i in bad_report.errors)
    assert any(i.code == "GLOSSARY_TERM_MISSING" for i in bad_report.warnings)


def test_glossary_curly_apostrophe_longest_first_and_yo_equivalence() -> None:
    glossary = Glossary(
        entries=(
            GlossaryEntry(source="Demon King", target="Король Демонов", category="terms"),
            GlossaryEntry(
                source="Demon King of Salvation",
                target="Король Демонов Спасения",
                category="constellations",
            ),
            GlossaryEntry(
                source="Omniscient Reader's Viewpoint",
                target="Точка зрения всеведущего читателя",
                category="terms",
            ),
            GlossaryEntry(
                source="[Fourth Wall]",
                target="[Четвёртая Стена]",
                category="skills",
            ),
        )
    )

    src = Chapter(
        number=553,
        title="553 Omniscient Reader’s Viewpoint",
        blocks=(
            ParagraphBlock("Demon King of Salvation activated [Fourth Wall]."),
        ),
    )

    # Longest-first prevents `Demon King` from firing separately inside `Demon King of Salvation`.
    matched = glossary.match_relevant(src)
    assert [e.source for e in matched] == [
        "Demon King of Salvation",
        "Omniscient Reader's Viewpoint",
        "[Fourth Wall]",
    ]

    # Russian `е` matches glossary `ё` (`Четвертая` vs `Четвёртая`).
    dst = src.with_translated_content(
        title="553 Точка зрения всеведущего читателя",
        blocks=(
            ParagraphBlock("Король Демонов Спасения активировал [Четвертая Стена]."),
        ),
    )
    report = GlossaryChecker().check(src, dst, glossary)
    assert report.is_valid
    assert report.issues == ()


def test_glossary_cooccurring_mutually_forbidden_terms() -> None:
    glossary = Glossary(
        entries=(
            GlossaryEntry(
                source="Secretive Plotter",
                target="Скрытный Интриган",
                category="constellations",
                forbidden=("Коварный Интриган", "Скрытый Проектировщик"),
            ),
            GlossaryEntry(
                source="Sneaky Schemer",
                target="Коварный Интриган",
                category="constellations",
                forbidden=("Скрытный Интриган", "Скрытый Проектировщик"),
            ),
        )
    )

    checker = GlossaryChecker()
    both_src = Chapter(
        number=569,
        title="569 Test",
        blocks=(
            ParagraphBlock(
                "He still confuses 'Sneaky Schemer' with 'Secretive Plotter'."
            ),
        ),
    )

    # 1. Both translated accurately -> valid, 0 issues
    good_dst = both_src.with_translated_content(
        title="569 Тест",
        blocks=(
            ParagraphBlock(
                "Он до сих пор путает «Коварного Интригана» со «Скрытным Интриганом»."
            ),
        ),
    )
    good_report = checker.check(both_src, good_dst, glossary)
    assert good_report.is_valid
    assert good_report.issues == ()

    # 2. Both collapsed to one target -> FORBIDDEN_TERM_USED still fires for the missing entry
    collapsed_dst = both_src.with_translated_content(
        title="569 Тест",
        blocks=(
            ParagraphBlock(
                "Он до сих пор путает «Скрытного Интригана» со «Скрытным Интриганом»."
            ),
        ),
    )
    collapsed_report = checker.check(both_src, collapsed_dst, glossary)
    assert not collapsed_report.is_valid
    assert any(i.code == "FORBIDDEN_TERM_USED" for i in collapsed_report.errors)

    # 3. Unrelated forbidden variant still fires even when both canonical terms exist
    bad_extra_dst = both_src.with_translated_content(
        title="569 Тест",
        blocks=(
            ParagraphBlock(
                "Он путает «Коварного Интригана», «Скрытного Интригана» и «Скрытого Проектировщика»."
            ),
        ),
    )
    bad_extra_report = checker.check(both_src, bad_extra_dst, glossary)
    assert not bad_extra_report.is_valid
    assert any(i.code == "FORBIDDEN_TERM_USED" for i in bad_extra_report.errors)

    # 4. Single source term using the other's target still fires FORBIDDEN_TERM_USED
    single_src = Chapter(
        number=569,
        title="569 Test",
        blocks=(ParagraphBlock("Secretive Plotter smiled."),),
    )
    swapped_dst = single_src.with_translated_content(
        title="569 Тест",
        blocks=(ParagraphBlock("Коварный Интриган улыбнулся."),),
    )
    swapped_report = checker.check(single_src, swapped_dst, glossary)
    assert not swapped_report.is_valid
    assert any(i.code == "FORBIDDEN_TERM_USED" for i in swapped_report.errors)
