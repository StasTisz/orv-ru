import json
from pathlib import Path

from orv_ru.app.cli import main


def _setup_agent_workspace(tmp_path: Path) -> Path:
    src_dir = tmp_path / "src_chapters"
    tr_dir = tmp_path / "tr_chapters"
    img_dir = tmp_path / "images"
    src_dir.mkdir()
    tr_dir.mkdir()
    img_dir.mkdir()

    (src_dir / "553.txt").write_text(
        "<title>553 Prologue\n"
        "<cover>[cover.jpg][]\n"
        "Kim Dokja looked at Oldest Dream.\n"
        "<&>「Quote」<br>— Author\n",
        encoding="utf-8",
    )
    (src_dir / "554.txt").write_text("<title>554 Ep 1\nSecond chapter.\n", encoding="utf-8")
    (img_dir / "cover.jpg").write_bytes(b"jpg-bytes")

    glossary_path = tmp_path / "glossary.toml"
    glossary_path.write_text(
        """[[characters]]
source = "Kim Dokja"
target = "Ким Докча"

[[constellations]]
source = "Oldest Dream"
target = "Древнейшая Мечта"
forbidden = ["Самый древний сон"]
""",
        encoding="utf-8",
    )

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
glossary = "{glossary_path}"
site_output = "{tmp_path / 'out_site'}"
epub_output = "{tmp_path / 'out_epub'}"

[reader]
words_per_minute = 250
default_theme = "dark"
""",
        encoding="utf-8",
    )
    return cfg_path


def test_agent_cli_end_to_end_export_import_glossary_and_dry_run(tmp_path: Path, capsys) -> None:
    cfg = _setup_agent_workspace(tmp_path)
    packet_file = tmp_path / "packet_553.json"

    # 1. Export packet
    assert main(["--config", str(cfg), "export-packet", "553", "--output", str(packet_file), "--json"]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["chapter_number"] == 553
    # Block 0 is CoverBlock -> excluded; items should be blocks 1 and 2
    assert [i["block_index"] for i in exported["items"]] == [1, 2]
    assert len(exported["glossary"]) == 2
    assert exported["token_estimate"]["estimated_total_tokens"] > 0

    # 2. Reject broken payload (missing <br> AND forbidden glossary term) and do NOT write .txt
    bad_payload_file = tmp_path / "bad_553.json"
    bad_payload_file.write_text(
        json.dumps(
            {
                "chapter_number": 553,
                "title": "553 Пролог",
                "items": [
                    {"block_index": 1, "lines": ["Ким Докча увидел самого древнего сна."]},
                    {"block_index": 2, "lines": ["「Цитата」 — Автор"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert main(["--config", str(cfg), "import-translation", "553", str(bad_payload_file), "--json"]) == 1
    bad_res = json.loads(capsys.readouterr().out)
    assert bad_res["accepted"] is False
    assert bad_res["saved"] is False
    assert not (tmp_path / "tr_chapters" / "553.txt").exists()

    # 3. Accept valid payload -> writes tr_chapters/553.txt preserving <cover>
    good_payload_file = tmp_path / "good_553.json"
    good_payload_file.write_text(
        json.dumps(
            {
                "chapter_number": 553,
                "title": "553 Пролог",
                "items": [
                    {"block_index": 1, "lines": ["Ким Докча посмотрел на Древнейшую Мечту."]},
                    {"block_index": 2, "lines": ["「Цитата」<br>— Автор"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert main(["--config", str(cfg), "import-translation", "553", str(good_payload_file), "--json"]) == 0
    good_res = json.loads(capsys.readouterr().out)
    assert good_res["accepted"] is True
    assert good_res["saved"] is True
    saved_txt = (tmp_path / "tr_chapters" / "553.txt").read_text(encoding="utf-8")
    assert "<cover>[cover.jpg][]" in saved_txt

    # 4. check-glossary --strict passes on 553
    assert main(["--config", str(cfg), "check-glossary", "--strict", "--json"]) == 0
    gl_res = json.loads(capsys.readouterr().out)
    assert gl_res["checked_chapters"] == 1
    assert gl_res["error_count"] == 0
    assert gl_res["warning_count"] == 0

    # 5. translate --dry-run skips already-valid 553 and plans 554
    assert main(["--config", str(cfg), "translate", "--dry-run", "--json"]) == 0
    plan_res = json.loads(capsys.readouterr().out)
    assert plan_res["skipped_already_valid"] == [553]
    assert plan_res["target_chapters"] == [554]

    # 6. Build EPUB & site from translated 553
    assert main(["--config", str(cfg), "build-epub", "--json"]) == 0
    capsys.readouterr()
    assert main(["--config", str(cfg), "build-site", "--json"]) == 0
    site_res = json.loads(capsys.readouterr().out)
    assert site_res["chapters_built"] == 1
