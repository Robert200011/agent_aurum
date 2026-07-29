"""Deterministic UTF-8 text and Markdown parsing."""

from __future__ import annotations

import re
import unicodedata

from app.rag.loaders.base import DocumentParsingError, ParsedDocument, ParsedSourceSpan

TEXT_PARSER_VERSION = "aurum-text-v1"
SUPPORTED_TEXT_MIME_TYPES = frozenset({"text/plain", "text/markdown"})
_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?$")
_INLINE_WHITESPACE = re.compile(r"[^\S\r\n]+")

class TextParsingError(DocumentParsingError):
    """A safe, non-retryable source parsing failure."""


ParsedTextDocument = ParsedDocument


def parse_text_document(content: bytes, mime_type: str) -> ParsedTextDocument:
    """Decode and normalize bounded UTF-8 source bytes without executing content."""

    if mime_type not in SUPPORTED_TEXT_MIME_TYPES:
        raise TextParsingError("document format is not supported by the current parser")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TextParsingError("text document is not valid UTF-8") from exc
    if "\x00" in decoded:
        raise TextParsingError("text document contains NUL bytes")

    normalized = normalize_text(decoded)
    if not normalized:
        raise TextParsingError("text document is empty after normalization")
    sections = (
        _markdown_sections(normalized)
        if mime_type == "text/markdown"
        else (ParsedSourceSpan(char_start=0, char_end=len(normalized)),)
    )
    return ParsedDocument(
        text=normalized,
        mime_type=mime_type,
        parser_version=TEXT_PARSER_VERSION,
        sources=sections,
    )


def normalize_text(value: str) -> str:
    """Normalize Unicode, line endings, and bounded whitespace deterministically."""

    value = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    blank_count = 0
    for raw_line in value.split("\n"):
        line = _INLINE_WHITESPACE.sub(" ", raw_line).strip()
        if line:
            blank_count = 0
            lines.append(line)
            continue
        blank_count += 1
        if blank_count <= 2:
            lines.append("")
    return "\n".join(lines).strip()


def _markdown_sections(text: str) -> tuple[ParsedSourceSpan, ...]:
    markers: list[tuple[int, str | None]] = [(0, None)]
    heading_stack: list[str] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        heading = _MARKDOWN_HEADING.fullmatch(line.rstrip("\n"))
        if heading is not None:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            heading_stack[level - 1 :] = [title]
            heading_path = " > ".join(heading_stack)
            if markers[-1][0] == offset:
                markers[-1] = (offset, heading_path)
            else:
                markers.append((offset, heading_path))
        offset += len(line)

    sections: list[ParsedSourceSpan] = []
    for index, (char_start, section_path) in enumerate(markers):
        char_end = markers[index + 1][0] if index + 1 < len(markers) else len(text)
        if char_end > char_start:
            sections.append(
                ParsedSourceSpan(
                    section_path=section_path,
                    char_start=char_start,
                    char_end=char_end,
                )
            )
    return tuple(sections)
