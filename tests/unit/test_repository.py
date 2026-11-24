from pathlib import Path

import pytest

from orv_ru.domain.blocks import ParagraphBlock
from orv_ru.domain.chapter import Chapter
from orv_ru.parsing.parser import OrvMarkupParser
from orv_ru.parsing.serializer import OrvMarkupSerializer
from orv_ru.storage.fs_repository import FileSystemChapterRepository


def test_fs_repository_numeric_order_and_round_trip(tmp_path: Path) -> None:
    repo = FileSystemChapterRepository(
        directory=tmp_path,
        parser=OrvMarkupParser(),
        serializer=OrvMarkupSerializer(),
    )

    assert repo.list_chapter_numbers() == []

    # Save out of order with 3- and 4-digit numbers to verify numeric sort
    for num in (1000, 553, 999):
        repo.save(
            Chapter(
                number=num,
                title=f"{num} Глава",
                blocks=(ParagraphBlock(f"Текст главы {num}."),),
            )
        )

    # Non-chapter files must be ignored
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")

    assert repo.list_chapter_numbers() == [553, 999, 1000]

    loaded = repo.load_all()
    assert [c.number for c in loaded] == [553, 999, 1000]
    assert loaded[0].title == "553 Глава"

    with pytest.raises(FileNotFoundError):
        repo.load(777)

    # Atomic overwrite leaves no leftover `.tmp` files and updates content cleanly
    repo.save(
        Chapter(
            number=553,
            title="553 Обновлено",
            blocks=(ParagraphBlock("Новый текст."),),
        )
    )
    assert repo.load(553).title == "553 Обновлено"
    assert not list(tmp_path.glob("*.tmp"))
