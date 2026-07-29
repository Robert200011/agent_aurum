"""Bounded DOCX body extraction with heading-path source locations."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from typing import Protocol, cast

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.config import Settings
from app.rag.loaders.base import (
    DocumentParsingError,
    ParsedDocument,
    ParsedFragment,
    build_parsed_document,
)
from app.rag.loaders.text import normalize_text

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_PARSER_VERSION = "aurum-docx-openxml-v1"
_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": _WORD_NAMESPACE}
_W_VAL = f"{{{_WORD_NAMESPACE}}}val"
_HEADING_STYLE = re.compile(r"^(?:heading|标题)\s*([1-9])$", re.IGNORECASE)


class _XmlElement(Protocol):
    tag: str
    text: str | None

    def __iter__(self) -> Iterator[_XmlElement]: ...

    def iter(self) -> Iterator[_XmlElement]: ...

    def find(
        self,
        path: str,
        namespaces: dict[str, str] | None = None,
    ) -> _XmlElement | None: ...

    def findall(
        self,
        path: str,
        namespaces: dict[str, str] | None = None,
    ) -> list[_XmlElement]: ...

    def get(self, key: str, default: str | None = None) -> str | None: ...


def parse_docx_document(content: bytes, settings: Settings) -> ParsedDocument:
    """Extract paragraphs and table rows without evaluating fields or relationships."""

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
    except (
        EOFError,
        KeyError,
        NotImplementedError,
        OSError,
        RuntimeError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ) as exc:
        raise DocumentParsingError("DOCX document could not be opened safely") from exc
    if len(document_xml) > settings.document_max_archive_member_bytes:
        raise DocumentParsingError("DOCX document XML exceeds the configured member limit")

    try:
        root = cast(
            _XmlElement,
            ElementTree.fromstring(
                document_xml,
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            ),
        )
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise DocumentParsingError("DOCX document XML is not valid") from exc
    body = root.find("w:body", _NS)
    if body is None:
        raise DocumentParsingError("DOCX document body is missing")

    fragments: list[ParsedFragment] = []
    heading_stack: list[str] = []
    extracted_characters = 0
    for child in body:
        if child.tag == f"{{{_WORD_NAMESPACE}}}p":
            paragraph = normalize_text(_paragraph_text(child))
            if not paragraph:
                continue
            heading_level = _heading_level(child)
            if heading_level is not None:
                heading_stack[heading_level - 1 :] = [paragraph]
            section_path = " > ".join(heading_stack) or None
            extracted_characters = _append_fragment(
                fragments,
                ParsedFragment(
                    text=paragraph,
                    section_path=section_path,
                    metadata={"source_kind": "docx_paragraph"},
                ),
                extracted_characters,
                settings,
            )
        elif child.tag == f"{{{_WORD_NAMESPACE}}}tbl":
            section_path = " > ".join(heading_stack) or None
            for row in child.findall("w:tr", _NS):
                cells = [
                    normalize_text(
                        " ".join(
                            _paragraph_text(paragraph)
                            for paragraph in cell.findall(".//w:p", _NS)
                        )
                    )
                    for cell in row.findall("w:tc", _NS)
                ]
                rendered = " | ".join(cell for cell in cells if cell)
                if not rendered:
                    continue
                extracted_characters = _append_fragment(
                    fragments,
                    ParsedFragment(
                        text=rendered,
                        section_path=section_path,
                        metadata={"source_kind": "docx_table_row"},
                    ),
                    extracted_characters,
                    settings,
                )

    return build_parsed_document(
        fragments=fragments,
        mime_type=DOCX_MIME_TYPE,
        parser_version=DOCX_PARSER_VERSION,
    )


def _paragraph_text(paragraph: _XmlElement) -> str:
    parts: list[str] = []
    for element in paragraph.iter():
        if element.tag == f"{{{_WORD_NAMESPACE}}}t" and element.text:
            parts.append(element.text)
        elif element.tag == f"{{{_WORD_NAMESPACE}}}tab":
            parts.append("\t")
        elif element.tag in {
            f"{{{_WORD_NAMESPACE}}}br",
            f"{{{_WORD_NAMESPACE}}}cr",
        }:
            parts.append("\n")
    return "".join(parts)


def _heading_level(paragraph: _XmlElement) -> int | None:
    style = paragraph.find("w:pPr/w:pStyle", _NS)
    if style is not None:
        style_name = (style.get(_W_VAL) or "").replace("_", " ").strip()
        match = _HEADING_STYLE.fullmatch(style_name)
        if match is not None:
            return int(match.group(1))
    outline = paragraph.find("w:pPr/w:outlineLvl", _NS)
    if outline is not None:
        raw_level = outline.get(_W_VAL)
        if raw_level is not None and raw_level.isdigit():
            return min(9, int(raw_level) + 1)
    return None


def _append_fragment(
    fragments: list[ParsedFragment],
    fragment: ParsedFragment,
    extracted_characters: int,
    settings: Settings,
) -> int:
    extracted_characters += len(fragment.text)
    if extracted_characters > settings.document_max_extracted_characters:
        raise DocumentParsingError("DOCX document exceeds the configured extracted text limit")
    fragments.append(fragment)
    return extracted_characters
