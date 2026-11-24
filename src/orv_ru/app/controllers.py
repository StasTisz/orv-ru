"""GRASP Controller coordinating parsing, storage, validation, rendering, and translation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orv_ru.app.models import ValidationSummary, WorkspaceStatus, serialize_report
from orv_ru.config import AppConfig, StoryConfigEntry, load_config
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import StoryMetadata
from orv_ru.domain.validation import Severity, ValidationIssue, ValidationReport
from orv_ru.parsing import OrvMarkupParser, OrvMarkupSerializer, StructuralValidator
from orv_ru.ports.renderer import BookBuilder, EpubBuildReport, SiteBuilder, SiteBuildReport
from orv_ru.ports.repository import ChapterReader, ChapterRepository
from orv_ru.ports.translator import LLMClient
from orv_ru.rendering import AssetResolver, EpubBookBuilder, HtmlBlockRenderer, StaticSiteBuilder
from orv_ru.storage import FileSystemChapterRepository
from orv_ru.translation import (
    ChapterChunker,
    ChapterTranslationPipeline,
    Glossary,
    GlossaryChecker,
    GlossaryLoader,
    PromptBuilder,
    TranslatedPayload,
    apply_payload,
    estimate_packet_tokens,
    extract_packet,
)


class WorkspaceController:
    """Coordinates black-box subsystems strictly through `ports/` Protocols (DIP)."""

    def __init__(
        self,
        config: AppConfig,
        source_repo: ChapterReader,
        translated_repo: ChapterRepository,
        validator: StructuralValidator,
        site_builder: SiteBuilder,
        epub_builder: BookBuilder,
        glossary_checker: GlossaryChecker | None = None,
        *,
        active_story: StoryMetadata | None = None,
        parser: OrvMarkupParser | None = None,
        serializer: OrvMarkupSerializer | None = None,
    ) -> None:
        self._config = config
        self._source_repo = source_repo
        self._translated_repo = translated_repo
        self._validator = validator
        self._site_builder = site_builder
        self._epub_builder = epub_builder
        self._glossary_checker = glossary_checker or GlossaryChecker()
        self._active_story = active_story or config.story
        self._parser = parser or OrvMarkupParser()
        self._serializer = serializer or OrvMarkupSerializer()

    @classmethod
    def from_config(
        cls,
        config_path: Path,
        *,
        story_slug: str | None = None,
    ) -> WorkspaceController:
        """Composition root wiring concrete adapters from `config.toml`."""
        resolved_cfg = config_path.resolve()
        cfg = load_config(resolved_cfg)
        entry = cfg.resolve_story(story_slug)
        web_dir = resolved_cfg.parent / "web"

        parser = OrvMarkupParser()
        serializer = OrvMarkupSerializer()
        validator = StructuralValidator()

        source_repo = FileSystemChapterRepository(entry.source_chapters, parser, serializer)
        translated_repo = FileSystemChapterRepository(
            entry.translated_chapters, parser, serializer
        )
        asset_resolver = AssetResolver(cfg.paths.assets_images)
        site_builder = StaticSiteBuilder(
            web_dir=web_dir,
            block_renderer=HtmlBlockRenderer(),
            asset_resolver=asset_resolver,
            words_per_minute=cfg.reader.words_per_minute,
            epub_source_dir=cfg.paths.epub_output,
            branding_dir=cfg.paths.assets_branding,
        )
        epub_builder = EpubBookBuilder(asset_resolver=asset_resolver)
        return cls(
            config=cfg,
            source_repo=source_repo,
            translated_repo=translated_repo,
            validator=validator,
            site_builder=site_builder,
            epub_builder=epub_builder,
            glossary_checker=GlossaryChecker(),
            active_story=entry.story,
            parser=parser,
            serializer=serializer,
        )

    @property
    def active_story(self) -> StoryMetadata:
        return self._active_story

    def for_story(self, slug: str) -> WorkspaceController:
        """Return a controller view bound to another configured story slug."""
        entry = self._config.resolve_story(slug)
        if entry.story.slug == self._active_story.slug:
            return self
        return WorkspaceController(
            config=self._config,
            source_repo=FileSystemChapterRepository(
                entry.source_chapters, self._parser, self._serializer
            ),
            translated_repo=FileSystemChapterRepository(
                entry.translated_chapters, self._parser, self._serializer
            ),
            validator=self._validator,
            site_builder=self._site_builder,
            epub_builder=self._epub_builder,
            glossary_checker=self._glossary_checker,
            active_story=entry.story,
            parser=self._parser,
            serializer=self._serializer,
        )

    @property
    def config(self) -> AppConfig:
        return self._config

    def load_glossary(self) -> Glossary:
        """Load the configured TOML glossary (or empty glossary if absent)."""
        return GlossaryLoader.load_optional(self._config.paths.glossary)

    def status(self) -> WorkspaceStatus:
        """Return translation progress and structural health across source/translated dirs."""
        source_nums = self._source_repo.list_chapter_numbers()
        source_set = set(source_nums)
        translated_nums = self._translated_repo.list_chapter_numbers()
        translated_set = set(translated_nums)
        remaining = [n for n in source_nums if n not in translated_set]

        valid_count = 0
        invalid_chapters: list[int] = []
        for num in translated_nums:
            dst = self._translated_repo.load(num)
            if num in source_set:
                src = self._source_repo.load(num)
                report = self._validator.validate_translation(src, dst)
            else:
                report = self._validator.validate_chapter(dst)
            if report.is_valid:
                valid_count += 1
            else:
                invalid_chapters.append(num)

        return WorkspaceStatus(
            story_slug=self._active_story.slug,
            source_count=len(source_nums),
            translated_count=len(translated_nums),
            remaining_count=len(remaining),
            valid_translated_count=valid_count,
            invalid_translated_chapters=tuple(invalid_chapters),
            next_untranslated=tuple(remaining[:5]),
        )

    def validate(
        self,
        chapter_numbers: list[int] | None = None,
        *,
        source_only: bool = False,
    ) -> ValidationSummary:
        """Validate source chapters or source-vs-translated pairs."""
        reports: list[ValidationReport] = []

        if source_only:
            targets = (
                sorted(chapter_numbers)
                if chapter_numbers is not None
                else self._source_repo.list_chapter_numbers()
            )
            for num in targets:
                reports.append(self._validator.validate_chapter(self._source_repo.load(num)))
            mode = "source"
        else:
            translated_nums = self._translated_repo.list_chapter_numbers()
            translated_set = set(translated_nums)
            targets = sorted(chapter_numbers) if chapter_numbers is not None else translated_nums
            source_set = set(self._source_repo.list_chapter_numbers())
            for num in targets:
                if num not in translated_set:
                    reports.append(
                        ValidationReport(
                            chapter_number=num,
                            issues=(
                                ValidationIssue(
                                    code="MISSING_TRANSLATION",
                                    severity=Severity.ERROR,
                                    message=f"Translated chapter {num}.txt does not exist.",
                                ),
                            ),
                        )
                    )
                    continue
                dst = self._translated_repo.load(num)
                if num in source_set:
                    src = self._source_repo.load(num)
                    reports.append(self._validator.validate_translation(src, dst))
                else:
                    reports.append(self._validator.validate_chapter(dst))
            mode = "translation"

        error_count = sum(len(r.errors) for r in reports)
        warning_count = sum(len(r.warnings) for r in reports)
        return ValidationSummary(
            mode=mode,
            checked_chapters=len(reports),
            error_count=error_count,
            warning_count=warning_count,
            is_valid=(error_count == 0),
            reports=tuple(reports),
        )

    def export_packet(self, chapter_number: int) -> dict[str, Any]:
        """Export a protected translation packet + token estimate for one chapter."""
        chapter = self._source_repo.load(chapter_number)
        glossary = self.load_glossary()
        packet = extract_packet(chapter, glossary)
        data = packet.to_dict()
        data["token_estimate"] = estimate_packet_tokens(packet)
        return data

    def import_translation(
        self,
        chapter_number: int,
        payload_data: dict[str, Any],
        *,
        strict_glossary: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Apply, validate, and optionally persist a translated JSON payload."""
        source = self._source_repo.load(chapter_number)
        payload = TranslatedPayload.from_dict(
            payload_data, fallback_chapter_number=chapter_number
        )
        if payload.chapter_number != chapter_number:
            raise ValueError(
                f"Payload chapter_number ({payload.chapter_number}) does not match "
                f"target chapter {chapter_number}."
            )

        translated = apply_payload(source, payload)
        structural_report = self._validator.validate_translation(source, translated)
        glossary_report = self._glossary_checker.check(source, translated, self.load_glossary())

        accepted = (
            structural_report.is_valid
            and glossary_report.is_valid
            and (not strict_glossary or not glossary_report.warnings)
        )

        saved_path: Path | None = None
        if accepted and not dry_run:
            saved_path = self._translated_repo.save(translated)

        return {
            "chapter_number": chapter_number,
            "accepted": accepted,
            "saved": saved_path is not None,
            "output_path": str(saved_path) if saved_path is not None else None,
            "structural_validation": serialize_report(structural_report),
            "glossary_validation": serialize_report(glossary_report),
        }

    def check_glossary(self, chapter_numbers: list[int] | None = None) -> ValidationSummary:
        """Run deterministic glossary compliance checks across translated chapters."""
        glossary = self.load_glossary()
        source_set = set(self._source_repo.list_chapter_numbers())
        translated_nums = self._translated_repo.list_chapter_numbers()
        translated_set = set(translated_nums)
        targets = sorted(chapter_numbers) if chapter_numbers is not None else translated_nums

        reports: list[ValidationReport] = []
        for num in targets:
            if num not in translated_set:
                reports.append(
                    ValidationReport(
                        chapter_number=num,
                        issues=(
                            ValidationIssue(
                                code="MISSING_TRANSLATION",
                                severity=Severity.ERROR,
                                message=f"Translated chapter {num}.txt does not exist.",
                            ),
                        ),
                    )
                )
                continue
            if num not in source_set:
                continue
            src = self._source_repo.load(num)
            dst = self._translated_repo.load(num)
            reports.append(self._glossary_checker.check(src, dst, glossary))

        error_count = sum(len(r.errors) for r in reports)
        warning_count = sum(len(r.warnings) for r in reports)
        return ValidationSummary(
            mode="glossary",
            checked_chapters=len(reports),
            error_count=error_count,
            warning_count=warning_count,
            is_valid=(error_count == 0),
            reports=tuple(reports),
        )

    def plan_translation(
        self,
        chapter_numbers: list[int] | None = None,
        *,
        next_count: int | None = None,
        force: bool = False,
        max_chars: int = 3500,
    ) -> dict[str, Any]:
        """Compute chunk counts and token budget without calling any LLM."""
        targets, skipped = self._select_translation_targets(
            chapter_numbers=chapter_numbers, next_count=next_count, force=force
        )
        glossary = self.load_glossary()
        chunker = ChapterChunker(max_chars=max_chars)

        plan_items: list[dict[str, Any]] = []
        total_chunks = 0
        total_input_tokens = 0
        total_output_tokens = 0

        for num in targets:
            ch = self._source_repo.load(num)
            packet = extract_packet(ch, glossary)
            chunks = chunker.split(packet)
            estimate = estimate_packet_tokens(packet)
            total_chunks += len(chunks)
            total_input_tokens += estimate["estimated_input_tokens"]
            total_output_tokens += estimate["estimated_output_tokens_ru"]
            plan_items.append(
                {
                    "chapter_number": num,
                    "chunks": len(chunks),
                    "translatable_items": len(packet.items),
                    "matched_glossary_terms": len(packet.matched_glossary),
                    **estimate,
                }
            )

        return {
            "target_chapters": targets,
            "skipped_already_valid": skipped,
            "total_chapters": len(targets),
            "total_chunks": total_chunks,
            "estimated_input_tokens": total_input_tokens,
            "estimated_output_tokens_ru": total_output_tokens,
            "estimated_total_tokens": total_input_tokens + total_output_tokens,
            "chapters": plan_items,
        }

    def translate_chapters(
        self,
        llm_client: LLMClient,
        chapter_numbers: list[int] | None = None,
        *,
        next_count: int | None = None,
        force: bool = False,
        max_chars: int = 3500,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """Run resumable LLM translation across selected chapters, saving each valid result."""
        targets, skipped = self._select_translation_targets(
            chapter_numbers=chapter_numbers, next_count=next_count, force=force
        )
        glossary = self.load_glossary()
        pipeline = ChapterTranslationPipeline(
            llm_client=llm_client,
            validator=self._validator,
            glossary_checker=self._glossary_checker,
            prompt_builder=PromptBuilder(self._active_story),
            chunker=ChapterChunker(max_chars=max_chars),
            max_retries=max_retries,
        )

        translated_results: list[dict[str, Any]] = []
        failed_results: list[dict[str, Any]] = []

        for num in targets:
            src = self._source_repo.load(num)
            try:
                res = pipeline.translate(src, glossary.entries, rules=glossary.rules)
                out_path = self._translated_repo.save(res.chapter)
                translated_results.append(
                    {
                        "chapter_number": num,
                        "chunks_processed": res.chunks_processed,
                        "attempts": res.attempts,
                        "glossary_warnings": len(res.glossary_report.warnings),
                        "output_path": str(out_path),
                    }
                )
            except Exception as exc:
                failed_results.append({"chapter_number": num, "error": str(exc)})

        return {
            "skipped_already_valid": skipped,
            "translated": translated_results,
            "failed": failed_results,
            "translated_count": len(translated_results),
            "failed_count": len(failed_results),
        }

    def build_site(
        self,
        *,
        use_source: bool = False,
        limit: int | None = None,
    ) -> SiteBuildReport:
        """Build the static HTML reader across all configured stories."""
        entries: tuple[StoryConfigEntry, ...] = self._config.stories
        if len(entries) <= 1:
            chapters = self._load_chapters_for_build(use_source=use_source, limit=limit)
            return self._site_builder.build(
                story=self._active_story,
                chapters=chapters,
                output_dir=self._config.paths.site_output,
            )

        if limit is not None and limit <= 0:
            raise ValueError(f"--limit must be positive, got {limit}")

        collection: list[tuple[StoryMetadata, list[Chapter]]] = []
        source_counts: dict[str, int] = {}
        total_chapters = 0
        for entry in entries:
            scoped = self.for_story(entry.story.slug)
            src_nums = scoped._source_repo.list_chapter_numbers()
            source_counts[entry.story.slug] = len(src_nums)
            repo: ChapterReader = scoped._source_repo if use_source else scoped._translated_repo
            numbers = repo.list_chapter_numbers()
            if limit is not None:
                numbers = numbers[:limit]
            loaded = [repo.load(num) for num in numbers]
            total_chapters += len(loaded)
            collection.append((entry.story, loaded))

        if total_chapters == 0:
            label = "source" if use_source else "translated"
            raise FileNotFoundError(f"No {label} chapters available for build.")

        return self._site_builder.build_collection(
            collection,
            self._config.paths.site_output,
            primary_slug=self._active_story.slug,
            source_counts=source_counts,
        )

    def build_epub(
        self,
        *,
        use_source: bool = False,
        limit: int | None = None,
    ) -> EpubBuildReport:
        """Build the EPUB book for the active story from translated (or source) chapters."""
        chapters = self._load_chapters_for_build(use_source=use_source, limit=limit)
        epub_name = f"orv_{self._active_story.slug}_{self._active_story.language}.epub"
        output_file = self._config.paths.epub_output / epub_name
        return self._epub_builder.build(
            story=self._active_story,
            chapters=chapters,
            output_file=output_file,
        )

    def _select_translation_targets(
        self,
        *,
        chapter_numbers: list[int] | None,
        next_count: int | None,
        force: bool,
    ) -> tuple[list[int], list[int]]:
        source_nums = self._source_repo.list_chapter_numbers()
        source_set = set(source_nums)
        translated_set = set(self._translated_repo.list_chapter_numbers())

        if chapter_numbers is not None:
            missing_src = [n for n in chapter_numbers if n not in source_set]
            if missing_src:
                raise FileNotFoundError(f"Source chapters not found: {missing_src}")
            candidates = sorted(dict.fromkeys(chapter_numbers))
        else:
            candidates = source_nums

        targets: list[int] = []
        skipped: list[int] = []
        for num in candidates:
            if not force and num in translated_set:
                src = self._source_repo.load(num)
                dst = self._translated_repo.load(num)
                if self._validator.validate_translation(src, dst).is_valid:
                    skipped.append(num)
                    continue
            targets.append(num)

        if next_count is not None:
            if next_count <= 0:
                raise ValueError(f"--next must be positive, got {next_count}")
            targets = targets[:next_count]

        return targets, skipped

    def _load_chapters_for_build(
        self,
        *,
        use_source: bool,
        limit: int | None,
    ) -> list[Chapter]:
        repo: ChapterReader = self._source_repo if use_source else self._translated_repo
        numbers = repo.list_chapter_numbers()
        if limit is not None:
            if limit <= 0:
                raise ValueError(f"--limit must be positive, got {limit}")
            numbers = numbers[:limit]
        if not numbers:
            label = "source" if use_source else "translated"
            raise FileNotFoundError(f"No {label} chapters available for build.")
        return [repo.load(num) for num in numbers]
