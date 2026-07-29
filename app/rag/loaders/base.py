"""Shared normalized-document and source-location contracts for ingestion loaders."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field


class DocumentParsingError(ValueError):
    """A safe, non-retryable failure while parsing an untrusted source document."""


@dataclass(frozen=True, slots=True)
class ParsedSourceSpan:
    """A normalized-text interval mapped back to one source location."""

    char_start: int
    char_end: int
    section_path: str | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> str | None:
        """Keep the original Markdown section-span attribute compatible."""

        return self.section_path


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """The source coordinates covered by one prepared chunk."""

    section_path: str | None
    page_number: int | None
    sheet_name: str | None
    row_start: int | None
    row_end: int | None
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Normalized parser output shared by every supported source format."""

    text: str
    mime_type: str
    parser_version: str
    sources: tuple[ParsedSourceSpan, ...]

    @property
    def sections(self) -> tuple[ParsedSourceSpan, ...]:
        """Keep the original Markdown/TXT parser contract available to callers."""

        return self.sources

    def section_path_at(self, char_offset: int) -> str | None:
        return self._span_at(char_offset).section_path

    def partition_end_at(self, char_offset: int) -> int:
        """Return the end of a page/sheet partition that chunks must not cross."""

        index = self._span_index_at(char_offset)
        source = self.sources[index]
        partition = _partition_key(source)
        if partition is None:
            return len(self.text)
        end = source.char_end
        for following in self.sources[index + 1 :]:
            if _partition_key(following) != partition:
                break
            end = following.char_end
        return end

    def source_location(self, char_start: int, char_end: int) -> SourceLocation:
        """Collapse all source spans overlapping a chunk into stable coordinates."""

        overlapping = tuple(
            source
            for source in self.sources
            if source.char_end > char_start and source.char_start < char_end
        )
        if not overlapping:
            overlapping = (self._span_at(char_start),)
        first = overlapping[0]
        metadata: dict[str, str] = {}
        for source in overlapping:
            metadata.update(source.metadata)

        pages = [source.page_number for source in overlapping if source.page_number is not None]
        sheets = {source.sheet_name for source in overlapping if source.sheet_name is not None}
        row_starts = [source.row_start for source in overlapping if source.row_start is not None]
        row_ends = [source.row_end for source in overlapping if source.row_end is not None]
        if len(set(pages)) > 1:
            metadata["page_start"] = str(min(pages))
            metadata["page_end"] = str(max(pages))
        return SourceLocation(
            section_path=first.section_path,
            page_number=pages[0] if pages else None,
            sheet_name=next(iter(sheets)) if len(sheets) == 1 else None,
            row_start=min(row_starts) if row_starts else None,
            row_end=max(row_ends) if row_ends else None,
            metadata=metadata,
        )

    def _span_at(self, char_offset: int) -> ParsedSourceSpan:
        return self.sources[self._span_index_at(char_offset)]

    def _span_index_at(self, char_offset: int) -> int:
        if not self.sources:
            raise DocumentParsingError("parsed document has no source locations")
        starts = [source.char_start for source in self.sources]
        return max(0, bisect_right(starts, char_offset) - 1)


@dataclass(frozen=True, slots=True)
class ParsedFragment:
    """One already-normalized text fragment and its source coordinates."""

    text: str
    section_path: str | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)


def build_parsed_document(
    *,
    fragments: list[ParsedFragment],
    mime_type: str,
    parser_version: str,
    separator: str = "\n\n",
) -> ParsedDocument:
    """Join normalized fragments while preserving exact output offsets."""

    text_parts: list[str] = []
    sources: list[ParsedSourceSpan] = []
    offset = 0
    for fragment in fragments:
        if not fragment.text:
            continue
        if text_parts:
            text_parts.append(separator)
            offset += len(separator)
        char_start = offset
        text_parts.append(fragment.text)
        offset += len(fragment.text)
        sources.append(
            ParsedSourceSpan(
                char_start=char_start,
                char_end=offset,
                section_path=fragment.section_path,
                page_number=fragment.page_number,
                sheet_name=fragment.sheet_name,
                row_start=fragment.row_start,
                row_end=fragment.row_end,
                metadata=dict(fragment.metadata),
            )
        )
    if not sources:
        raise DocumentParsingError("document is empty after normalization")
    return ParsedDocument(
        text="".join(text_parts),
        mime_type=mime_type,
        parser_version=parser_version,
        sources=tuple(sources),
    )


def _partition_key(source: ParsedSourceSpan) -> tuple[str, object] | None:
    if source.page_number is not None:
        return ("page", source.page_number)
    if source.sheet_name is not None:
        return ("sheet", source.sheet_name)
    return None
