"""MIME-based dispatcher for all supported ingestion document loaders."""

from __future__ import annotations

from app.config import Settings
from app.rag.loaders.base import DocumentParsingError, ParsedDocument
from app.rag.loaders.docx import DOCX_MIME_TYPE, parse_docx_document
from app.rag.loaders.pdf import PDF_MIME_TYPE, parse_pdf_document
from app.rag.loaders.tabular import (
    CSV_MIME_TYPE,
    XLSX_MIME_TYPE,
    parse_csv_document,
    parse_xlsx_document,
)
from app.rag.loaders.text import SUPPORTED_TEXT_MIME_TYPES, parse_text_document


def parse_document(content: bytes, mime_type: str, settings: Settings) -> ParsedDocument:
    """Dispatch a validated immutable source to its deterministic parser."""

    if mime_type in SUPPORTED_TEXT_MIME_TYPES:
        return parse_text_document(content, mime_type)
    if mime_type == PDF_MIME_TYPE:
        return parse_pdf_document(content, settings)
    if mime_type == DOCX_MIME_TYPE:
        return parse_docx_document(content, settings)
    if mime_type == CSV_MIME_TYPE:
        return parse_csv_document(content, settings)
    if mime_type == XLSX_MIME_TYPE:
        return parse_xlsx_document(content, settings)
    raise DocumentParsingError("document format is not supported by the current parser")
