"""Bounded validation for untrusted knowledge-document uploads."""

from __future__ import annotations

import hashlib
import io
import struct
import zipfile
from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath

from app.config import Settings
from app.errors import BusinessRuleError
from app.rag.constants import MAX_DOCUMENT_FILENAME_LENGTH

ZIP_EOCD_SIGNATURE = b"PK\x05\x06"
ZIP_EOCD_STRUCT = struct.Struct("<4s4H2LH")
ZIP_VALIDATION_CHUNK_BYTES = 64 * 1024
MIN_RATIO_CHECK_BYTES = 1024 * 1024

_FORMATS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass(frozen=True, slots=True)
class ValidatedDocumentUpload:
    filename: str
    mime_type: str
    content: bytes
    content_hash: str
    size_bytes: int
    metadata: dict[str, str]


def validate_document_upload(
    *,
    filename: str | None,
    content: bytes,
    metadata: dict[str, str],
    settings: Settings,
) -> ValidatedDocumentUpload:
    """Validate a bounded upload before it reaches object storage."""

    normalized_filename = _normalize_filename(filename)
    if not content:
        raise BusinessRuleError("document file is empty")
    if len(content) > settings.document_max_size_bytes:
        raise BusinessRuleError("document file exceeds the configured size limit")
    _validate_metadata(metadata, settings)

    suffix = PurePath(normalized_filename).suffix.casefold()
    mime_type = _FORMATS.get(suffix)
    if mime_type is None:
        raise BusinessRuleError("document file type is not supported")
    if suffix == ".pdf":
        _validate_pdf(content)
    elif suffix in {".docx", ".xlsx"}:
        _validate_office_archive(content, suffix, settings)
    else:
        _validate_utf8_text(content)

    return ValidatedDocumentUpload(
        filename=normalized_filename,
        mime_type=mime_type,
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        metadata=dict(metadata),
    )


def _normalize_filename(filename: str | None) -> str:
    if filename is None or not filename.strip():
        raise BusinessRuleError("document filename is required")
    if len(filename) > MAX_DOCUMENT_FILENAME_LENGTH:
        raise BusinessRuleError("document filename is too long")
    if any(ord(character) < 32 for character in filename):
        raise BusinessRuleError("document filename contains unsafe characters")
    path = PurePath(filename)
    if path.name != filename or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise BusinessRuleError("document filename must not contain a path")
    normalized = filename.strip()
    if not normalized or PurePath(normalized).stem.casefold() in {"con", "prn", "aux", "nul"}:
        raise BusinessRuleError("document filename is not valid")
    return normalized


def _validate_metadata(metadata: dict[str, str], settings: Settings) -> None:
    if len(metadata) > settings.document_metadata_max_entries:
        raise BusinessRuleError("document metadata contains too many entries")
    for key, value in metadata.items():
        if (
            not key
            or len(key) > settings.document_metadata_key_max_length
            or len(value) > settings.document_metadata_value_max_length
            or any(ord(character) < 32 for character in key + value)
        ):
            raise BusinessRuleError("document metadata is not valid")


def _validate_pdf(content: bytes) -> None:
    if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-2048:]:
        raise BusinessRuleError("PDF file is not valid")


def _validate_utf8_text(content: bytes) -> None:
    if b"\x00" in content:
        raise BusinessRuleError("text document contains NUL bytes")
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BusinessRuleError("text documents must use UTF-8 encoding") from exc


def _validate_office_archive(content: bytes, suffix: str, settings: Settings) -> None:
    expected_member = "word/document.xml" if suffix == ".docx" else "xl/workbook.xml"
    member_count = _declared_member_count(content, suffix)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) != member_count:
                raise BusinessRuleError("Office archive member count is inconsistent")
            names = {member.filename for member in members}
            if "[Content_Types].xml" not in names or expected_member not in names:
                raise BusinessRuleError("Office document structure is not valid")
            total_uncompressed = 0
            total_compressed = 0
            for member in members:
                _validate_archive_member(member, settings)
                if member.is_dir():
                    continue
                expanded = 0
                with archive.open(member) as source:
                    while chunk := source.read(ZIP_VALIDATION_CHUNK_BYTES):
                        expanded += len(chunk)
                        total_uncompressed += len(chunk)
                        if expanded > settings.document_max_archive_member_bytes:
                            raise BusinessRuleError(
                                "Office archive member exceeds expanded size limit"
                            )
                        if total_uncompressed > settings.document_max_archive_uncompressed_bytes:
                            raise BusinessRuleError("Office archive exceeds expanded size limit")
                total_compressed += member.compress_size
                if (
                    expanded >= MIN_RATIO_CHECK_BYTES
                    and expanded / max(1, member.compress_size)
                    > settings.document_max_archive_compression_ratio
                ):
                    raise BusinessRuleError("Office archive compression ratio is unsafe")
            if (
                total_uncompressed >= MIN_RATIO_CHECK_BYTES
                and total_uncompressed / max(1, total_compressed)
                > settings.document_max_archive_compression_ratio
            ):
                raise BusinessRuleError("Office archive compression ratio is unsafe")
    except BusinessRuleError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError, EOFError) as exc:
        raise BusinessRuleError("Office document is not a valid ZIP archive") from exc


def _declared_member_count(content: bytes, suffix: str) -> int:
    offset = content.rfind(ZIP_EOCD_SIGNATURE, max(0, len(content) - ZIP_EOCD_STRUCT.size - 65535))
    if offset < 0 or len(content) - offset < ZIP_EOCD_STRUCT.size:
        raise BusinessRuleError(f"{suffix[1:].upper()} document is not a valid ZIP archive")
    (
        _signature,
        disk_number,
        central_directory_disk,
        members_on_disk,
        member_count,
        central_directory_size,
        central_directory_offset,
        comment_length,
    ) = ZIP_EOCD_STRUCT.unpack_from(content, offset)
    if offset + ZIP_EOCD_STRUCT.size + comment_length != len(content):
        raise BusinessRuleError("Office archive has an invalid end record")
    if disk_number or central_directory_disk or members_on_disk != member_count:
        raise BusinessRuleError("multi-disk Office archives are not supported")
    if (
        member_count == 0xFFFF
        or central_directory_size == 0xFFFFFFFF
        or central_directory_offset == 0xFFFFFFFF
    ):
        raise BusinessRuleError("ZIP64 Office archives are not supported")
    return int(member_count)


def _validate_archive_member(member: zipfile.ZipInfo, settings: Settings) -> None:
    path = PurePosixPath(member.filename)
    if not member.filename or "\\" in member.filename or path.is_absolute() or ".." in path.parts:
        raise BusinessRuleError("Office archive contains an unsafe member path")
    if member.flag_bits & 0x1:
        raise BusinessRuleError("encrypted Office archive members are not supported")
    if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise BusinessRuleError("Office archive uses an unsupported compression method")
    if member.file_size > settings.document_max_archive_member_bytes:
        raise BusinessRuleError("Office archive member exceeds expanded size limit")
