"""Filesystem-backed repository implementing `ChapterRepository` via DI."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from orv_ru.domain.chapter import Chapter
from orv_ru.ports.parser import ChapterParser, ChapterSerializer

# Matches both `<N>.txt` (`cont`, `side`, translations) and `chap_<0000N>.txt` (`orv` corpus).
_CHAPTER_FILE_RE = re.compile(r"^(?:chap_)?(\d+)\.txt$")


class FileSystemChapterRepository:
    """Stores and loads chapters as `<number>.txt` (or `chap_<N>.txt`) files in a directory."""

    def __init__(
        self,
        directory: Path,
        parser: ChapterParser,
        serializer: ChapterSerializer,
    ) -> None:
        self._directory = directory
        self._parser = parser
        self._serializer = serializer

    @property
    def directory(self) -> Path:
        return self._directory

    def _scan_files(self) -> dict[int, Path]:
        if not self._directory.exists():
            return {}
        found: dict[int, Path] = {}
        for entry in self._directory.iterdir():
            if not entry.is_file():
                continue
            match = _CHAPTER_FILE_RE.match(entry.name)
            if match:
                num = int(match.group(1))
                # Prefer canonical `<N>.txt` over `chap_<N>.txt` if both exist.
                if num not in found or not entry.name.startswith("chap_"):
                    found[num] = entry
        return found

    def list_chapter_numbers(self) -> list[int]:
        """Return all chapter numbers present in the directory in numeric order."""
        return sorted(self._scan_files())

    def load(self, chapter_number: int) -> Chapter:
        """Load and parse `{chapter_number}.txt` (or `chap_{chapter_number:05d}.txt`) as UTF-8."""
        direct = self._directory / f"{chapter_number}.txt"
        file_path = direct if direct.is_file() else self._scan_files().get(chapter_number)
        if file_path is None or not file_path.is_file():
            raise FileNotFoundError(f"Chapter file not found: {direct}")
        raw_text = file_path.read_text(encoding="utf-8")
        return self._parser.parse(chapter_number, raw_text, source_name=file_path.name)

    def load_all(self) -> list[Chapter]:
        """Load all chapters sorted by chapter number ascending."""
        files = self._scan_files()
        return [
            self._parser.parse(num, files[num].read_text(encoding="utf-8"), source_name=files[num].name)
            for num in sorted(files)
        ]

    def save(self, chapter: Chapter) -> Path:
        """Atomically serialize and write a chapter to `{chapter.number}.txt` in UTF-8."""
        self._directory.mkdir(parents=True, exist_ok=True)
        file_path = self._directory / f"{chapter.number}.txt"
        serialized = self._serializer.serialize(chapter)

        # Write to a sibling temp file first so interrupted batch runs never leave truncated chapters.
        fd, tmp_name = tempfile.mkstemp(
            dir=self._directory,
            prefix=f".{chapter.number}.",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
            os.replace(tmp_path, file_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return file_path
