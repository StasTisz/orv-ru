import json
from pathlib import Path

from orv_ru.app.cli import main


def _write_test_workspace(tmp_path: Path) -> Path:
    src_dir = tmp_path / "src_chapters"
    tr_dir = tmp_path / "tr_chapters"
    img_dir = tmp_path / "images"
    src_dir.mkdir()
    tr_dir.mkdir()
    img_dir.mkdir()

    (src_dir / "553.txt").write_text("<title>553 Prologue\nHello world.\n", encoding="utf-8")
    (src_dir / "554.txt").write_text("<title>554 Ep 1\nSecond chapter.\n", encoding="utf-8")
    (tr_dir / "553.txt").write_text("<title>553 Пролог\nПривет, мир.\n", encoding="utf-8")

    # Symlink `web/` next to temporary config so WorkspaceController finds clean-room templates
    project_web = Path(__file__).resolve().parents[2] / "web"
    (tmp_path / "web").symlink_to(project_web)

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f"""[story]
slug = "cont"
title = "Побочная история"
original_title = "ORV Sequel"
author = "Sing Shong"
language = "ru"
status = "Онгоинг"

[paths]
source_chapters = "{src_dir}"
translated_chapters = "{tr_dir}"
assets_images = "{img_dir}"
glossary = "glossary/orv_glossary.toml"
site_output = "{tmp_path / 'out_site'}"
epub_output = "{tmp_path / 'out_epub'}"

[reader]
words_per_minute = 250
default_theme = "dark"
""",
        encoding="utf-8",
    )
    return cfg_path


def test_cli_status_validate_and_builds(tmp_path: Path, capsys) -> None:
    cfg = _write_test_workspace(tmp_path)

    # 1. status --json
    rc = main(["--config", str(cfg), "status", "--json"])
    assert rc == 0
    status_data = json.loads(capsys.readouterr().out)
    assert status_data["source_count"] == 2
    assert status_data["translated_count"] == 1
    assert status_data["remaining_count"] == 1
    assert status_data["next_untranslated"] == [554]

    # 2. validate --json (passes for valid 553)
    rc = main(["--config", str(cfg), "validate", "--json"])
    assert rc == 0
    val_data = json.loads(capsys.readouterr().out)
    assert val_data["is_valid"] is True

    # 3. Break translation of 553 (add extra paragraph -> block count mismatch) -> exit code 1
    (tmp_path / "tr_chapters" / "553.txt").write_text(
        "<title>553 Пролог\nПривет, мир.\nЛишняя строка.\n", encoding="utf-8"
    )
    rc = main(["--config", str(cfg), "validate", "--json"])
    assert rc == 1
    bad_val = json.loads(capsys.readouterr().out)
    assert bad_val["is_valid"] is False
    assert bad_val["error_count"] >= 1

    # Restore valid 553 and build epub + site
    (tmp_path / "tr_chapters" / "553.txt").write_text(
        "<title>553 Пролог\nПривет, мир.\n", encoding="utf-8"
    )
    assert main(["--config", str(cfg), "build-epub", "--json"]) == 0
    epub_data = json.loads(capsys.readouterr().out)
    assert epub_data["chapters_built"] == 1
    assert Path(epub_data["output_file"]).is_file()

    assert main(["--config", str(cfg), "build-site", "--json"]) == 0
    site_data = json.loads(capsys.readouterr().out)
    assert site_data["chapters_built"] == 1
    assert (Path(site_data["output_dir"]) / "downloads" / "orv_cont_ru.epub").is_file()
