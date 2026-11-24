"""Agent helper: export the next N untranslated chapter packets into `data/work/`."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from orv_ru.app.controllers import WorkspaceController


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export protected translation packet(s) for the next untranslated chapter(s)."
    )
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--count", type=int, default=1, help="Number of untranslated chapters to export")
    parser.add_argument("--chapter", type=int, default=None, help="Explicit chapter number to export")
    parser.add_argument("--work-dir", type=Path, default=Path("data/work"))
    args = parser.parse_args(argv)

    controller = WorkspaceController.from_config(args.config)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    if args.chapter is not None:
        targets = [args.chapter]
    else:
        if args.count <= 0:
            raise ValueError(f"--count must be positive, got {args.count}")
        plan = controller.plan_translation(next_count=args.count)
        targets = list(plan["target_chapters"])

    exported: list[dict[str, object]] = []
    for num in targets:
        packet = controller.export_packet(num)
        packet_path = args.work_dir / f"packet_{num}.json"
        packet_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        exported.append(
            {
                "chapter_number": num,
                "packet_path": str(packet_path),
                "suggested_translation_path": str(args.work_dir / f"translated_{num}.json"),
                "translatable_items": len(packet["items"]),
                "matched_glossary_terms": len(packet["glossary"]),
                "token_estimate": packet["token_estimate"],
            }
        )

    print(json.dumps({"exported": exported}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
