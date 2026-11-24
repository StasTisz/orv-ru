"""Rendering contracts and build report value objects for Stage 3."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from orv_ru.domain.blocks import Block
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.story import StoryMetadata


@dataclass(frozen=True)
class SiteBuildReport:
    """Summary returned after compiling a static HTML reader site."""

    chapters_built: int
    assets_copied: int
    missing_assets: tuple[str, ...]
    output_dir: Path


@dataclass(frozen=True)
class EpubBuildReport:
    """Summary returned after packaging chapters into an EPUB file."""

    chapters_built: int
    assets_embedded: int
    missing_assets: tuple[str, ...]
    output_file: Path


class BlockRenderer(Protocol):
    """Renders a single `Block` into target markup (HTML or XHTML)."""

    def render(self, block: Block) -> str: ...


class SiteBuilder(Protocol):
    """Compiles a sequence of chapters into a static web reader."""

    def build(
        self,
        story: StoryMetadata,
        chapters: list[Chapter],
        output_dir: Path,
    ) -> SiteBuildReport: ...

    def build_collection(
        self,
        stories: Sequence[tuple[StoryMetadata, list[Chapter]]],
        output_dir: Path,
        *,
        primary_slug: str | None = None,
        source_counts: dict[str, int] | None = None,
    ) -> SiteBuildReport: ...


class BookBuilder(Protocol):
    """Compiles a sequence of chapters into a packaged e-book (e.g., EPUB)."""

    def build(
        self,
        story: StoryMetadata,
        chapters: list[Chapter],
        output_file: Path,
    ) -> EpubBuildReport: ...
