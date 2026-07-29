"""Bounded PDF text extraction with page-level source locations."""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.config import Settings
from app.rag.loaders.base import (
    DocumentParsingError,
    ParsedDocument,
    ParsedFragment,
    build_parsed_document,
)
from app.rag.loaders.text import normalize_text

PDF_MIME_TYPE = "application/pdf"
PDF_PARSER_VERSION = "aurum-pdf-pypdf-v1"


def parse_pdf_document(content: bytes, settings: Settings) -> ParsedDocument:
    """Extract normalized text without passwords, OCR, attachments, or active content."""

    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise DocumentParsingError("encrypted PDF documents are not supported")
        page_count = len(reader.pages)
        if page_count == 0:
            raise DocumentParsingError("PDF document contains no pages")
        if page_count > settings.document_max_pdf_pages:
            raise DocumentParsingError("PDF document exceeds the configured page limit")

        fragments: list[ParsedFragment] = []
        extracted_characters = 0
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = normalize_text(page.extract_text() or "")
            if not page_text:
                continue
            extracted_characters += len(page_text)
            if extracted_characters > settings.document_max_extracted_characters:
                raise DocumentParsingError(
                    "PDF document exceeds the configured extracted text limit"
                )
            fragments.append(
                ParsedFragment(
                    text=page_text,
                    page_number=page_number,
                    metadata={"source_kind": "pdf_page"},
                )
            )
    except DocumentParsingError:
        raise
    except (
        PdfReadError,
        IndexError,
        KeyError,
        OSError,
        RecursionError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise DocumentParsingError("PDF document could not be parsed safely") from exc

    if not fragments:
        raise DocumentParsingError(
            "PDF document contains no extractable text; OCR is not enabled"
        )
    return build_parsed_document(
        fragments=fragments,
        mime_type=PDF_MIME_TYPE,
        parser_version=PDF_PARSER_VERSION,
    )
