"""将模型临时来源标记转换为后端可信的结构化引用。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.agents.state import ControlledContextSource, ControlledRagContext

_SOURCE_MARKER_PATTERN = re.compile(r"\[[sS]([^\]\r\n]*)\]")
_PUBLIC_CITATION_PATTERN = re.compile(r"\[[1-9][0-9]*\]")
_UNFINISHED_SOURCE_MARKER_PATTERN = re.compile(r"\[[sS]")
_CONTENT_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class CitationValidationError(RuntimeError):
    """模型引用不满足白名单或可信快照约束。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TrustedCitation:
    """由临时编号映射出的可信引用，不接受任何模型生成的来源字段。"""

    citation_id: int
    marker: str
    document_id: UUID
    document_version_id: UUID
    knowledge_base_id: UUID
    chunk_id: UUID
    title: str
    document_version: int
    page: int | None
    section: str | None
    sheet_name: str | None
    row_start: int | None
    row_end: int | None
    char_start: int | None
    char_end: int | None
    content_hash: str
    quote: str
    score: float

    def source_snapshot(self) -> dict[str, Any]:
        """生成可直接持久化到 message_citations.source_snapshot 的快照。"""

        return {
            "document_id": str(self.document_id),
            "document_version_id": str(self.document_version_id),
            "knowledge_base_id": str(self.knowledge_base_id),
            "chunk_id": str(self.chunk_id),
            "title": self.title,
            "document_version": self.document_version,
            "page": self.page,
            "section": self.section,
            "sheet_name": self.sheet_name,
            "row_start": self.row_start,
            "row_end": self.row_end,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class StructuredCitationResult:
    """已把内部来源标记规范化为公开数字角标的回答。"""

    answer: str
    citations: tuple[TrustedCitation, ...]


def structure_citations(
    *,
    answer: str,
    context: ControlledRagContext,
    require_citation: bool,
) -> StructuredCitationResult:
    """按首次出现顺序编号，只接受本轮受控上下文中的来源。"""

    normalized_answer = answer.strip()
    if not normalized_answer:
        raise CitationValidationError("citation_answer_empty")
    if _PUBLIC_CITATION_PATTERN.search(normalized_answer):
        raise CitationValidationError("citation_marker_untrusted")

    allowed_sources = {source.marker: source for source in context.sources}
    citations_by_marker: dict[str, TrustedCitation] = {}
    citations: list[TrustedCitation] = []

    def replace_marker(match: re.Match[str]) -> str:
        raw_number = match.group(1)
        if (
            not raw_number.isascii()
            or not raw_number.isdigit()
            or raw_number.startswith("0")
        ):
            raise CitationValidationError("citation_marker_malformed")
        marker = f"S{raw_number}"
        source = allowed_sources.get(marker)
        if source is None:
            raise CitationValidationError("citation_marker_not_retrieved")
        citation = citations_by_marker.get(marker)
        if citation is None:
            citation = _trusted_citation(
                citation_id=len(citations) + 1,
                marker=marker,
                source=source,
            )
            citations_by_marker[marker] = citation
            citations.append(citation)
        return f"[{citation.citation_id}]"

    normalized_answer = _SOURCE_MARKER_PATTERN.sub(replace_marker, normalized_answer)
    if _UNFINISHED_SOURCE_MARKER_PATTERN.search(normalized_answer):
        raise CitationValidationError("citation_marker_malformed")
    if require_citation and not citations:
        raise CitationValidationError("citation_required")
    return StructuredCitationResult(
        answer=normalized_answer,
        citations=tuple(citations),
    )


def _trusted_citation(
    *,
    citation_id: int,
    marker: str,
    source: ControlledContextSource,
) -> TrustedCitation:
    chunk = source.chunk
    title = chunk.title.strip()
    quote = source.included_content.strip()
    if (
        not title
        or not quote
        or chunk.document_version < 1
        or not _CONTENT_HASH_PATTERN.fullmatch(chunk.content_hash)
        or (chunk.page_number is not None and chunk.page_number < 1)
        or (chunk.row_start is not None and chunk.row_start < 1)
        or (chunk.row_end is not None and chunk.row_end < 1)
        or (
            chunk.row_start is not None
            and chunk.row_end is not None
            and chunk.row_end < chunk.row_start
        )
        or (chunk.char_start is not None and chunk.char_start < 0)
        or (chunk.char_end is not None and chunk.char_end < 0)
        or (
            chunk.char_start is not None
            and chunk.char_end is not None
            and chunk.char_end < chunk.char_start
        )
        or not -1.0 <= chunk.score <= 1.0
    ):
        raise CitationValidationError("citation_source_invalid")
    return TrustedCitation(
        citation_id=citation_id,
        marker=marker,
        document_id=chunk.document_id,
        document_version_id=chunk.document_version_id,
        knowledge_base_id=chunk.knowledge_base_id,
        chunk_id=chunk.chunk_id,
        title=title,
        document_version=chunk.document_version,
        page=chunk.page_number,
        section=chunk.section_path,
        sheet_name=chunk.sheet_name,
        row_start=chunk.row_start,
        row_end=chunk.row_end,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        content_hash=chunk.content_hash,
        quote=quote,
        score=chunk.score,
    )
