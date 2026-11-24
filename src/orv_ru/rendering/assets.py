"""Asset resolver handling image path lookup and cached extension fallbacks."""

from __future__ import annotations

from pathlib import Path

_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"})
_MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


class AssetResolver:
    """Resolves referenced cover/illustration filenames against a local assets directory."""

    def __init__(self, images_dir: Path | None) -> None:
        self._images_dir = images_dir
        self._stem_index: dict[str, Path] | None = None

    @property
    def images_dir(self) -> Path | None:
        return self._images_dir

    def _get_stem_index(self) -> dict[str, Path]:
        if self._stem_index is None:
            index: dict[str, Path] = {}
            if self._images_dir is not None and self._images_dir.is_dir():
                for candidate in sorted(self._images_dir.iterdir()):
                    if candidate.is_file() and candidate.suffix.lower() in _IMAGE_EXTENSIONS:
                        index.setdefault(candidate.stem.lower(), candidate)
            self._stem_index = index
        return self._stem_index

    def resolve(self, filename: str) -> Path | None:
        """Resolve `filename` cleanly, falling back to a cached stem index if needed."""
        if not filename or self._images_dir is None or not self._images_dir.is_dir():
            return None

        # Strip directory components to prevent path traversal outside `images_dir`.
        safe_name = Path(filename).name
        direct = self._images_dir / safe_name
        if direct.is_file():
            return direct

        return self._get_stem_index().get(Path(safe_name).stem.lower())

    @staticmethod
    def guess_media_type(path: Path) -> str:
        """Return standard MIME media-type for an image file."""
        return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
