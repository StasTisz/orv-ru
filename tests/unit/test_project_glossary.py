from pathlib import Path

from orv_ru.translation import GlossaryLoader
from orv_ru.translation.glossary_checker import matches_forbidden_term

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GLOSSARY_PATH = PROJECT_ROOT / "glossary" / "orv_glossary.toml"


def test_project_glossary_integrity_and_invariants() -> None:
    glossary = GlossaryLoader.load(GLOSSARY_PATH)

    assert len(glossary.rules) >= 8
    assert len(glossary.entries) >= 130

    categories = {e.category for e in glossary.entries}
    expected_categories = {
        "characters",
        "side_characters",
        "constellations",
        "nebulae",
        "terms",
        "skills",
        "items",
        "locations",
    }
    assert expected_categories <= categories

    # Zero duplicate `source` keys (case-insensitive)
    seen_sources: dict[str, str] = {}
    for entry in glossary.entries:
        key = entry.source.lower()
        assert key not in seen_sources, f"Duplicate source term: {entry.source!r}"
        seen_sources[key] = entry.target

        # A canonical target must never trip its own forbidden list
        for bad in entry.forbidden:
            assert not matches_forbidden_term(
                bad, entry.target, canonical_target=entry.target
            ), (
                f"Entry {entry.source!r}: forbidden term {bad!r} matches target {entry.target!r}"
            )

    by_source = {e.source: e for e in glossary.entries}
    assert by_source["Secretive Plotter"].target != by_source["Sneaky Schemer"].target
    assert by_source["Oldest Dream"].target == "Древнейшая Мечта"
    assert by_source["Lee Dansu"].target == by_source["Lee Dansoo"].target == "Ли Дансу"
    assert by_source["Jaehwan"].target == by_source["Jeahwan"].target == "Джэхван"
