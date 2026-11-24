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
class AppConfig:
    """Top-level immutable application configuration."""

    story: StoryMetadata
    paths: PathsConfig
    reader: ReaderConfig


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else (base_dir / candidate).resolve()


def load_config(path: Path) -> AppConfig:
    """Load and validate an application TOML config, resolving relative paths against its parent."""
    config_path = path.resolve()
    base_dir = config_path.parent
    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    story_raw = raw["story"]
    paths_raw = raw["paths"]
    reader_raw = raw["reader"]

    slug = str(story_raw["slug"]).strip()
    if not slug:
        raise ValueError("story.slug in config must not be empty")

    words_per_minute = int(reader_raw["words_per_minute"])
    if words_per_minute <= 0:
        raise ValueError(f"reader.words_per_minute must be positive, got {words_per_minute}")

    story = StoryMetadata(
        slug=slug,
        title=str(story_raw["title"]),
        original_title=str(story_raw["original_title"]),
        author=str(story_raw["author"]),
        language=str(story_raw["language"]),
        status=str(story_raw["status"]),
    )
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
    return AppConfig(story=story, paths=paths, reader=reader)
