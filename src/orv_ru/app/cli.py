"""Command-line interface for human users and autonomous translation agents."""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from orv_ru.app.controllers import WorkspaceController
from orv_ru.translation import GeminiLLMClient

_CommandHandler = Callable[[argparse.Namespace, WorkspaceController], int]


def _build_parser() -> argparse.ArgumentParser:
    root_common = argparse.ArgumentParser(add_help=False)
    root_common.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to TOML configuration file (default: config.toml)",
    )
    root_common.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        default=False,
        help="Emit machine-readable JSON output",
    )

    # `SUPPRESS` prevents subparsers from overwriting `--config`/`--json` given before the command.
    sub_common = argparse.ArgumentParser(add_help=False)
    sub_common.add_argument(
        "--config",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to TOML configuration file (default: config.toml)",
    )
    sub_common.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        default=argparse.SUPPRESS,
        help="Emit machine-readable JSON output",
    )

    parser = argparse.ArgumentParser(
        prog="orv-ru",
        description="ORV Side Story clean-room builder, validator, and translation workbench",
        parents=[root_common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", parents=[sub_common], help="Show translation & validation status")

    val_p = sub.add_parser("validate", parents=[sub_common], help="Validate chapter structure")
    val_p.add_argument("--source", action="store_true", help="Validate source chapters only")
    val_p.add_argument(
        "--chapters",
        type=int,
        nargs="+",
        default=None,
        help="Specific chapter numbers to validate",
    )

    exp_p = sub.add_parser(
        "export-packet",
        parents=[sub_common],
        help="Export protected translation packet JSON for one chapter",
    )
    exp_p.add_argument("chapter", type=int, help="Source chapter number")
    exp_p.add_argument("--output", type=Path, default=None, help="Optional JSON output file path")

    imp_p = sub.add_parser(
        "import-translation",
        parents=[sub_common],
        help="Validate and save a translated JSON payload for one chapter",
    )
    imp_p.add_argument("chapter", type=int, help="Target chapter number")
    imp_p.add_argument("file", type=Path, help="Path to translated JSON payload file")
    imp_p.add_argument(
        "--strict-glossary",
        action="store_true",
        help="Reject payload if glossary warnings are present",
    )
    imp_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without writing the translated .txt file",
    )

    gl_p = sub.add_parser(
        "check-glossary",
        parents=[sub_common],
        help="Check glossary consistency across translated chapters",
    )
    gl_p.add_argument(
        "--chapters",
        type=int,
        nargs="+",
        default=None,
        help="Specific chapter numbers to check",
    )
    gl_p.add_argument(
        "--strict",
        action="store_true",
        help="Treat missing glossary warnings as exit code 1",
    )

    tr_p = sub.add_parser(
        "translate",
        parents=[sub_common],
        help="Translate chapters via LLM pipeline (or estimate budget with --dry-run)",
    )
    tr_p.add_argument(
        "--chapters",
        type=int,
        nargs="+",
        default=None,
        help="Specific chapter numbers to translate",
    )
    tr_p.add_argument(
        "--next",
        type=int,
        default=None,
        dest="next_count",
        help="Translate next N untranslated chapters",
    )
    tr_p.add_argument(
        "--model", default="gemini-2.5-pro", help="Gemini model ID (default: gemini-2.5-pro)"
    )
    tr_p.add_argument("--max-chars", type=int, default=3500, help="Max characters per LLM chunk")
    tr_p.add_argument("--max-retries", type=int, default=2, help="Self-healing retries per chunk")
    tr_p.add_argument("--force", action="store_true", help="Re-translate even valid chapters")
    tr_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan chunks and token budget without calling LLM",
    )

    site_p = sub.add_parser("build-site", parents=[sub_common], help="Compile static HTML site")
    site_p.add_argument("--source", action="store_true", help="Build from source chapters")
    site_p.add_argument("--limit", type=int, default=None, help="Build only first N chapters")

    epub_p = sub.add_parser("build-epub", parents=[sub_common], help="Package EPUB e-book")
    epub_p.add_argument("--source", action="store_true", help="Build from source chapters")
    epub_p.add_argument("--limit", type=int, default=None, help="Package only first N chapters")

    serve_p = sub.add_parser("serve", parents=[sub_common], help="Preview built static site locally")
    serve_p.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")

    return parser


def _print_output(payload: dict[str, Any], *, as_json: bool, text_lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in text_lines:
            print(line)


def _cmd_status(args: argparse.Namespace, controller: WorkspaceController) -> int:
    st = controller.status()
    _print_output(
        st.to_dict(),
        as_json=args.as_json,
        text_lines=[
            f"История: {st.story_slug}",
            f"Исходных глав: {st.source_count}",
            f"Переведено: {st.translated_count} (валидных: {st.valid_translated_count})",
            f"Осталось: {st.remaining_count}",
            f"Следующие к переводу: {list(st.next_untranslated)}",
        ],
    )
    return 0 if not st.invalid_translated_chapters else 1


def _cmd_validate(args: argparse.Namespace, controller: WorkspaceController) -> int:
    summary = controller.validate(chapter_numbers=args.chapters, source_only=args.source)
    lines = [
        f"Режим: {summary.mode} | Проверено глав: {summary.checked_chapters}",
        f"Ошибок: {summary.error_count} | Предупреждений: {summary.warning_count}",
    ]
    for rep in summary.reports:
        for issue in rep.issues:
            loc = f"блок {issue.block_index}" if issue.block_index is not None else "глава"
            lines.append(
                f"  [{issue.severity.upper()}] гл.{rep.chapter_number} ({loc}) "
                f"{issue.code}: {issue.message}"
            )
    _print_output(summary.to_dict(), as_json=args.as_json, text_lines=lines)
    return 0 if summary.is_valid else 1


def _cmd_export_packet(args: argparse.Namespace, controller: WorkspaceController) -> int:
    packet_data = controller.export_packet(args.chapter)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(packet_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if not args.as_json:
            est = packet_data["token_estimate"]
            print(
                f"Пакет главы {args.chapter} сохранён в {args.output} "
                f"(блоков: {len(packet_data['items'])}, ~{est['estimated_total_tokens']} токенов)"
            )
            return 0
    _print_output(
        packet_data,
        as_json=bool(args.as_json or args.output is None),
        text_lines=[f"Экспортирован пакет главы {args.chapter}"],
    )
    return 0


def _cmd_import_translation(args: argparse.Namespace, controller: WorkspaceController) -> int:
    raw_payload: dict[str, Any] = json.loads(args.file.read_text(encoding="utf-8"))
    res = controller.import_translation(
        args.chapter,
        raw_payload,
        strict_glossary=args.strict_glossary,
        dry_run=args.dry_run,
    )
    st_val = res["structural_validation"]
    gl_val = res["glossary_validation"]
    lines = [
        f"Глава {args.chapter}: {'ПРИНЯТА' if res['accepted'] else 'ОТКЛОНЕНА'}",
        f"Структура: ошибок={st_val['error_count']}, предупреждений={st_val['warning_count']}",
        f"Глоссарий: ошибок={gl_val['error_count']}, предупреждений={gl_val['warning_count']}",
    ]
    if res["saved"]:
        lines.append(f"Сохранено в: {res['output_path']}")
    _print_output(res, as_json=args.as_json, text_lines=lines)
    return 0 if res["accepted"] else 1


def _cmd_check_glossary(args: argparse.Namespace, controller: WorkspaceController) -> int:
    summary = controller.check_glossary(chapter_numbers=args.chapters)
    lines = [
        f"Проверено глав по глоссарию: {summary.checked_chapters}",
        (
            f"Ошибок (запрещённые термины): {summary.error_count} | "
            f"Предупреждений: {summary.warning_count}"
        ),
    ]
    for rep in summary.reports:
        for issue in rep.issues:
            loc = f"блок {issue.block_index}" if issue.block_index is not None else "заголовок"
            lines.append(
                f"  [{issue.severity.upper()}] гл.{rep.chapter_number} ({loc}) "
                f"{issue.code}: {issue.message}"
            )
    _print_output(summary.to_dict(), as_json=args.as_json, text_lines=lines)
    ok = summary.is_valid and (not args.strict or summary.warning_count == 0)
    return 0 if ok else 1


def _cmd_translate(args: argparse.Namespace, controller: WorkspaceController) -> int:
    if args.dry_run:
        plan = controller.plan_translation(
            chapter_numbers=args.chapters,
            next_count=args.next_count,
            force=args.force,
            max_chars=args.max_chars,
        )
        lines = [
            (
                f"План перевода (dry-run): глав={plan['total_chapters']}, "
                f"пропущено готовых={len(plan['skipped_already_valid'])}"
            ),
            (
                f"Чанков: {plan['total_chunks']} | "
                f"Оценка токенов: ~{plan['estimated_total_tokens']} "
                f"(вход ~{plan['estimated_input_tokens']}, выход ~{plan['estimated_output_tokens_ru']})"
            ),
        ]
        _print_output(plan, as_json=args.as_json, text_lines=lines)
        return 0

    client = GeminiLLMClient(model=args.model)
    result = controller.translate_chapters(
        client,
        chapter_numbers=args.chapters,
        next_count=args.next_count,
        force=args.force,
        max_chars=args.max_chars,
        max_retries=args.max_retries,
    )
    lines = [
        (
            f"Переведено глав: {result['translated_count']}, "
            f"пропущено: {len(result['skipped_already_valid'])}, "
            f"ошибок: {result['failed_count']}"
        )
    ]
    for item in result["failed"]:
        lines.append(f"  [ERROR] гл.{item['chapter_number']}: {item['error']}")
    _print_output(result, as_json=args.as_json, text_lines=lines)
    return 0 if result["failed_count"] == 0 else 1


def _cmd_build_site(args: argparse.Namespace, controller: WorkspaceController) -> int:
    site_rep = controller.build_site(use_source=args.source, limit=args.limit)
    payload: dict[str, Any] = {
        "chapters_built": site_rep.chapters_built,
        "assets_copied": site_rep.assets_copied,
        "missing_assets": list(site_rep.missing_assets),
        "output_dir": str(site_rep.output_dir),
    }
    _print_output(
        payload,
        as_json=args.as_json,
        text_lines=[
            f"Сайт собран: {site_rep.output_dir}",
            (
                f"Глав: {site_rep.chapters_built}, изображений: {site_rep.assets_copied}, "
                f"пропущено: {len(site_rep.missing_assets)}"
            ),
        ],
    )
    return 0


def _cmd_build_epub(args: argparse.Namespace, controller: WorkspaceController) -> int:
    epub_rep = controller.build_epub(use_source=args.source, limit=args.limit)
    payload: dict[str, Any] = {
        "chapters_built": epub_rep.chapters_built,
        "assets_embedded": epub_rep.assets_embedded,
        "missing_assets": list(epub_rep.missing_assets),
        "output_file": str(epub_rep.output_file),
    }
    _print_output(
        payload,
        as_json=args.as_json,
        text_lines=[
            f"EPUB собран: {epub_rep.output_file}",
            (
                f"Глав: {epub_rep.chapters_built}, встроено изображений: {epub_rep.assets_embedded}, "
                f"пропущено: {len(epub_rep.missing_assets)}"
            ),
        ],
    )
    return 0


def _cmd_serve(args: argparse.Namespace, controller: WorkspaceController) -> int:
    site_dir = controller.config.paths.site_output
    if not site_dir.is_dir():
        raise FileNotFoundError(
            f"Site output directory does not exist: {site_dir}. Run build-site first."
        )
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site_dir))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"Локальная читалка доступна по адресу: http://127.0.0.1:{args.port}/")
        print("Нажмите Ctrl+C для остановки.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nСервер остановлен.")
    return 0


_COMMAND_HANDLERS: dict[str, _CommandHandler] = {
    "status": _cmd_status,
    "validate": _cmd_validate,
    "export-packet": _cmd_export_packet,
    "import-translation": _cmd_import_translation,
    "check-glossary": _cmd_check_glossary,
    "translate": _cmd_translate,
    "build-site": _cmd_build_site,
    "build-epub": _cmd_build_epub,
    "serve": _cmd_serve,
}


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning POSIX exit code (`0` success, `1` error)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        controller = WorkspaceController.from_config(args.config)
    except Exception as exc:
        _print_output(
            {"error": str(exc)},
            as_json=args.as_json,
            text_lines=[f"Ошибка конфигурации: {exc}"],
        )
        return 1

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:
        return 1

    try:
        return handler(args, controller)
    except Exception as exc:
        _print_output(
            {"error": str(exc)},
            as_json=args.as_json,
            text_lines=[f"Ошибка выполнения: {exc}"],
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
