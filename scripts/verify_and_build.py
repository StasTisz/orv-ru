"""Agent helper: validate translations, check glossary, and build Russian EPUB + site."""

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
        description="Validate translated chapters, check glossary, and build EPUB + static site."
    )
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--source", action="store_true", help="Build from source chapters instead")
    parser.add_argument("--strict-glossary", action="store_true", help="Fail on glossary warnings")
    parser.add_argument("--with-tests", action="store_true", help="Also execute pytest")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    controller = WorkspaceController.from_config(args.config)

    if args.with_tests:
        proc = subprocess.run([sys.executable, "-m", "pytest"], check=False)
        if proc.returncode != 0:
            return proc.returncode

    val_summary = controller.validate(source_only=args.source)
    glossary_summary = (
        controller.check_glossary() if not args.source else None
    )

    val_ok = val_summary.is_valid
    glossary_ok = (
        True
        if glossary_summary is None
        else (
            glossary_summary.is_valid
            and (not args.strict_glossary or glossary_summary.warning_count == 0)
        )
    )

    if not (val_ok and glossary_ok):
        payload = {
            "ok": False,
            "validation": val_summary.to_dict(),
            "glossary": glossary_summary.to_dict() if glossary_summary else None,
        }
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"Проверка не пройдена: ошибок структуры={val_summary.error_count}, "
                f"ошибок глоссария={glossary_summary.error_count if glossary_summary else 0}"
            )
        return 1

    epub_rep = controller.build_epub(use_source=args.source)
    site_rep = controller.build_site(use_source=args.source)

    payload = {
        "ok": True,
        "chapters_built": site_rep.chapters_built,
        "validation_warnings": val_summary.warning_count,
        "glossary_warnings": glossary_summary.warning_count if glossary_summary else 0,
        "epub_file": str(epub_rep.output_file),
        "site_dir": str(site_rep.output_dir),
        "assets_copied": site_rep.assets_copied,
        "missing_assets": list(site_rep.missing_assets),
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"Готово: глав={payload['chapters_built']}, "
            f"EPUB={payload['epub_file']}, сайт={payload['site_dir']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
