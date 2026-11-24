import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_agent_helper_scripts_end_to_end(tmp_path: Path, capsys) -> None:
    src_dir = tmp_path / "src_chapters"
    tr_dir = tmp_path / "tr_chapters"
    img_dir = tmp_path / "images"
    work_dir = tmp_path / "work"
    src_dir.mkdir()
    tr_dir.mkdir()
    img_dir.mkdir()

    (src_dir / "553.txt").write_text("<title>553 Prologue\nKim Dokja smiled.\n", encoding="utf-8")
    (tr_dir / "553.txt").write_text("<title>553 Пролог\nКим Докча улыбнулся.\n", encoding="utf-8")
    (tmp_path / "web").symlink_to(PROJECT_ROOT / "web")

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
glossary = "{PROJECT_ROOT / 'glossary' / 'orv_glossary.toml'}"
site_output = "{tmp_path / 'out_site'}"
epub_output = "{tmp_path / 'out_epub'}"

[reader]
words_per_minute = 250
default_theme = "dark"
""",
        encoding="utf-8",
    )

    next_packet = _load_script("next_packet.py")
    assert next_packet.main(
        ["--config", str(cfg_path), "--chapter", "553", "--work-dir", str(work_dir)]
    ) == 0
    out_next = json.loads(capsys.readouterr().out)
    assert len(out_next["exported"]) == 1
    assert (work_dir / "packet_553.json").is_file()

    verify_and_build = _load_script("verify_and_build.py")
    assert verify_and_build.main(
        ["--config", str(cfg_path), "--strict-glossary", "--json"]
    ) == 0
    out_build = json.loads(capsys.readouterr().out)
    assert out_build["ok"] is True
    assert out_build["chapters_built"] == 1
    assert Path(out_build["epub_file"]).is_file()
    assert (Path(out_build["site_dir"]) / "stories" / "cont" / "read" / "ch_553.html").is_file()
