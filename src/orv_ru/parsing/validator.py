"""Structural validator guaranteeing zero-broken-tags invariants across translation."""

from __future__ import annotations

from orv_ru.domain.blocks import (
    CoverBlock,
    GenericBoxBlock,
    ImageBlock,
    ParagraphBlock,
    SystemWindowBlock,
)
from orv_ru.domain.chapter import Chapter
from orv_ru.domain.validation import Severity, ValidationIssue, ValidationReport

_KNOWN_PREFIXES = ("<title>", "<cover>", "<img>", "<!>", "<@>", "<#>", "<&>", "<?>", "<list>")
_CONTAINER_MARKERS = ("<!>", "<@>", "<#>", "<&>", "<?>")


class StructuralValidator:
    """Validates single chapters and source/translation pairs."""

    def validate_chapter(self, chapter: Chapter) -> ValidationReport:
        """Validate intrinsic structural integrity of a single `Chapter`."""
        issues: list[ValidationIssue] = []

        if not chapter.title.strip():
            issues.append(
                ValidationIssue(
                    code="EMPTY_TITLE",
                    severity=Severity.ERROR,
                    message="Chapter title must not be empty.",
                )
            )

        if not chapter.blocks:
            issues.append(
                ValidationIssue(
                    code="EMPTY_CHAPTER",
                    severity=Severity.ERROR,
                    message="Chapter contains no content blocks.",
                )
            )

        for idx, block in enumerate(chapter.blocks):
            if isinstance(block, (CoverBlock, ImageBlock)) and not block.filename.strip():
                issues.append(
                    ValidationIssue(
                        code="EMPTY_ASSET_FILENAME",
                        severity=Severity.ERROR,
                        message=f"{block.kind} block is missing an image filename.",
                        block_index=idx,
                    )
                )
            elif isinstance(block, ParagraphBlock):
                stripped = block.text.lstrip()
                if stripped.startswith(_KNOWN_PREFIXES):
                    issues.append(
                        ValidationIssue(
                            code="RAW_TAG_IN_PARAGRAPH",
                            severity=Severity.WARNING,
                            message="Paragraph text starts with a known markup tag prefix.",
                            block_index=idx,
                        )
                    )
            elif isinstance(block, (SystemWindowBlock, GenericBoxBlock)) and any(
                line.lstrip().startswith(_CONTAINER_MARKERS) for line in block.lines
            ):
                issues.append(
                    ValidationIssue(
                        code="RAW_TAG_IN_CONTAINER",
                        severity=Severity.WARNING,
                        message=(
                            f"{block.kind} contains raw inline tag marker (e.g. <!> or <&>)."
                        ),
                        block_index=idx,
                    )
                )

        return ValidationReport(chapter_number=chapter.number, issues=tuple(issues))

    def validate_translation(self, source: Chapter, translated: Chapter) -> ValidationReport:
        """Verify 1:1 structural parity between a source chapter and its translation."""
        issues: list[ValidationIssue] = []

        if source.number != translated.number:
            issues.append(
                ValidationIssue(
                    code="CHAPTER_NUMBER_MISMATCH",
                    severity=Severity.ERROR,
                    message=(
                        f"Chapter number mismatch: expected {source.number}, got {translated.number}."
                    ),
                )
            )

        if len(source.blocks) != len(translated.blocks):
            issues.append(
                ValidationIssue(
                    code="BLOCK_COUNT_MISMATCH",
                    severity=Severity.ERROR,
                    message=(
                        f"Block count mismatch: expected {len(source.blocks)}, "
                        f"got {len(translated.blocks)}."
                    ),
                )
            )
        else:
            for idx, (src_block, dst_block) in enumerate(
                zip(source.blocks, translated.blocks, strict=True)
            ):
                if src_block.kind != dst_block.kind:
                    issues.append(
                        ValidationIssue(
                            code="BLOCK_KIND_MISMATCH",
                            severity=Severity.ERROR,
                            message=(
                                f"Block {idx} kind mismatch: expected {src_block.kind}, "
                                f"got {dst_block.kind}."
                            ),
                            block_index=idx,
                        )
                    )
                    continue

                if src_block.structural_signature() != dst_block.structural_signature():
                    issues.append(
                        ValidationIssue(
                            code="STRUCTURAL_SIGNATURE_MISMATCH",
                            severity=Severity.ERROR,
                            message=(
                                f"Block {idx} ({src_block.kind}) structural invariant changed: "
                                f"{src_block.structural_signature()} != "
                                f"{dst_block.structural_signature()}."
                            ),
                            block_index=idx,
                        )
                    )

                if (
                    src_block.is_translatable
                    and src_block.plain_text().strip()
                    and not dst_block.plain_text().strip()
                ):
                    issues.append(
                        ValidationIssue(
                            code="EMPTY_TRANSLATED_BLOCK",
                            severity=Severity.ERROR,
                            message=f"Block {idx} ({src_block.kind}) became empty after translation.",
                            block_index=idx,
                        )
                    )

        target_report = self.validate_chapter(translated)
        issues.extend(target_report.issues)

        return ValidationReport(chapter_number=source.number, issues=tuple(issues))
