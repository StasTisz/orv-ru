from pathlib import Path

from orv_ru.config import load_config


def test_load_project_config() -> None:
    project_root = Path(__file__).resolve().parents[2]
    cfg = load_config(project_root / "config.toml")

    assert cfg.story.slug == "cont"
    assert cfg.story.language == "ru"
    assert cfg.story.author == "Sing Shong"
    assert cfg.reader.words_per_minute == 250
    assert cfg.reader.default_theme == "dark"
    assert cfg.paths.glossary == (project_root / "glossary/orv_glossary.toml").resolve()
    assert cfg.paths.translated_chapters == (project_root / "data/chapters/cont").resolve()
    assert (
        cfg.paths.assets_branding
        == (project_root / "../reference-orv-reader/website/assets").resolve()
    )
