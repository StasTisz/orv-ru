"""Agent helper: validate translations, check glossary, and build Russian EPUBs + multi-story site."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from orv_ru.app.controllers import WorkspaceController


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate translated chapters, check glossary, and build EPUBs + static site."
    )
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--story", type=str, default=None, help="Optional single story slug")
    parser.add_argument("--source", action="store_true", help="Build from source chapters instead")
    parser.add_argument("--strict-glossary", action="store_true", help="Fail on glossary warnings")
    parser.add_argument("--with-tests", action="store_true", help="Also execute pytest")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    controller = WorkspaceController.from_config(args.config, story_slug=args.story)

    if args.with_tests:
        proc = subprocess.run([sys.executable, "-m", "pytest"], check=False)
        if proc.returncode != 0:
            return proc.returncode

    stories = (
        (controller.config.resolve_story(args.story),)
        if args.story is not None
        else controller.config.stories
    )

    total_val_errors = 0
    total_val_warnings = 0
    total_gl_errors = 0
    total_gl_warnings = 0
    val_reports: list[dict[str, object]] = []
    gl_reports: list[dict[str, object]] = []
    buildable_slugs: list[str] = []

    for entry in stories:
        scoped = controller.for_story(entry.story.slug)
        val_summary = scoped.validate(source_only=args.source)
        if val_summary.checked_chapters == 0:
            continue
        buildable_slugs.append(entry.story.slug)
        total_val_errors += val_summary.error_count
        total_val_warnings += val_summary.warning_count
        val_reports.append({"story": entry.story.slug, **val_summary.to_dict()})

        if not args.source:
            gl_summary = scoped.check_glossary()
            total_gl_errors += gl_summary.error_count
            total_gl_warnings += gl_summary.warning_count
            gl_reports.append({"story": entry.story.slug, **gl_summary.to_dict()})

    val_ok = total_val_errors == 0
    glossary_ok = total_gl_errors == 0 and (not args.strict_glossary or total_gl_warnings == 0)

    if not (val_ok and glossary_ok):
        payload = {
            "ok": False,
            "validation": val_reports,
            "glossary": gl_reports,
        }
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"Проверка не пройдена: ошибок структуры={total_val_errors}, "
                f"ошибок глоссария={total_gl_errors}"
            )
        return 1

    epub_files: list[str] = []
    for slug in buildable_slugs:
        epub_rep = controller.for_story(slug).build_epub(use_source=args.source)
        epub_files.append(str(epub_rep.output_file))

    site_rep = controller.build_site(use_source=args.source)

    primary_epub = epub_files[0] if epub_files else ""
    for ep in epub_files:
        if f"orv_{controller.active_story.slug}_" in ep:
            primary_epub = ep
            break

    payload = {
        "ok": True,
        "chapters_built": site_rep.chapters_built,
        "stories_with_chapters": buildable_slugs,
        "validation_warnings": total_val_warnings,
        "glossary_warnings": total_gl_warnings,
        "epub_file": primary_epub,
        "epub_files": epub_files,
        "site_dir": str(site_rep.output_dir),
        "assets_copied": site_rep.assets_copied,
        "missing_assets": list(site_rep.missing_assets),
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"Готово: глав={payload['chapters_built']}, "
            f"EPUB={payload['epub_files']}, сайт={payload['site_dir']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
