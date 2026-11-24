"""Typed configuration loader using standard-library tomllib."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from orv_ru.domain.story import StoryMetadata


@dataclass(frozen=True)
class PathsConfig:
    """Resolved filesystem paths used across build and translation pipelines."""

    source_chapters: Path
    translated_chapters: Path
    assets_images: Path
    glossary: Path
    site_output: Path
    epub_output: Path
    assets_branding: Path | None = None


@dataclass(frozen=True)
class ReaderConfig:
    """Reader presentation and metric defaults."""

    words_per_minute: int
    default_theme: str


@dataclass(frozen=True)
class StoryConfigEntry:
    """Configuration for one story collection (e.g., `orv`, `cont`, `side`)."""

    story: StoryMetadata
    source_chapters: Path
    translated_chapters: Path


@dataclass(frozen=True)
class AppConfig:
    """Top-level immutable application configuration."""

    story: StoryMetadata
    paths: PathsConfig
    reader: ReaderConfig
    stories: tuple[StoryConfigEntry, ...] = ()

    def resolve_story(self, slug: str | None = None) -> StoryConfigEntry:
        """Return the configured story matching `slug`, or the primary configured story."""
        entries = self.stories or (
            StoryConfigEntry(
                story=self.story,
                source_chapters=self.paths.source_chapters,
                translated_chapters=self.paths.translated_chapters,
            ),
        )
        if slug is None:
            for entry in entries:
                if entry.story.slug == self.story.slug:
                    return entry
            return entries[0]
        for entry in entries:
            if entry.story.slug == slug:
                return entry
        known = ", ".join(entry.story.slug for entry in entries)
        raise ValueError(f"Unknown story slug '{slug}'. Configured stories: {known}")


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else (base_dir / candidate).resolve()


def _parse_story_metadata(raw: dict[str, object], *, default_author: str = "Sing Shong") -> StoryMetadata:
    slug = str(raw["slug"]).strip()
    if not slug:
        raise ValueError("story.slug in config must not be empty")
    return StoryMetadata(
        slug=slug,
        title=str(raw["title"]),
        original_title=str(raw["original_title"]),
        author=str(raw.get("author", default_author)),
        language=str(raw.get("language", "ru")),
        status=str(raw.get("status", "Онгоинг")),
        synopsis=str(raw.get("synopsis", "")),
    )


def load_config(path: Path) -> AppConfig:
    """Load and validate an application TOML config, resolving relative paths against its parent."""
    config_path = path.resolve()
    base_dir = config_path.parent
    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    story_raw = raw["story"]
    paths_raw = raw["paths"]
    reader_raw = raw["reader"]

    words_per_minute = int(reader_raw["words_per_minute"])
    if words_per_minute <= 0:
        raise ValueError(f"reader.words_per_minute must be positive, got {words_per_minute}")

    story = _parse_story_metadata(story_raw)
    raw_branding = paths_raw.get("assets_branding")
    paths = PathsConfig(
        source_chapters=_resolve_path(base_dir, str(paths_raw["source_chapters"])),
        translated_chapters=_resolve_path(base_dir, str(paths_raw["translated_chapters"])),
        assets_images=_resolve_path(base_dir, str(paths_raw["assets_images"])),
        glossary=_resolve_path(base_dir, str(paths_raw["glossary"])),
        site_output=_resolve_path(base_dir, str(paths_raw["site_output"])),
        epub_output=_resolve_path(base_dir, str(paths_raw["epub_output"])),
        assets_branding=_resolve_path(base_dir, str(raw_branding)) if raw_branding else None,
    )
    reader = ReaderConfig(
        words_per_minute=words_per_minute,
        default_theme=str(reader_raw["default_theme"]),
    )

    raw_stories = raw.get("stories")
    story_entries: list[StoryConfigEntry] = []
    if isinstance(raw_stories, list):
        for item in raw_stories:
            entry_meta = _parse_story_metadata(item, default_author=story.author)
            src_raw = item.get("source_chapters")
            tr_raw = item.get("translated_chapters")
            story_entries.append(
                StoryConfigEntry(
                    story=entry_meta,
                    source_chapters=_resolve_path(base_dir, str(src_raw))
                    if src_raw
                    else paths.source_chapters,
                    translated_chapters=_resolve_path(base_dir, str(tr_raw))
                    if tr_raw
                    else paths.translated_chapters,
                )
            )

    if not story_entries:
        story_entries.append(
            StoryConfigEntry(
                story=story,
                source_chapters=paths.source_chapters,
                translated_chapters=paths.translated_chapters,
            )
        )

    return AppConfig(story=story, paths=paths, reader=reader, stories=tuple(story_entries))
