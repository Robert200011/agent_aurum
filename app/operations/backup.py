"""Safe archive primitives shared by the P6.4 operational scripts."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tarfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from Crypto.Cipher import AES

BACKUP_FORMAT_VERSION = "aurum-backup-v1"
BACKUP_MAGIC = b"AURUM-BACKUP-V1\n"
NONCE_BYTES = 12
TAG_BYTES = 16
CHUNK_BYTES = 1024 * 1024


class BackupValidationError(ValueError):
    """Raised before unsafe or invalid backup operations can proceed."""


def decode_backup_key(value: str) -> bytes:
    """Decode a dedicated 256-bit base64 backup key without accepting passphrases."""

    try:
        key = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise BackupValidationError("backup key must be valid base64") from exc
    if len(key) != 32:
        raise BackupValidationError("backup key must decode to exactly 32 bytes")
    return key


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def encrypt_file(source: Path, destination: Path, key: bytes) -> None:
    """Encrypt a file with authenticated AES-256-GCM using a random nonce."""

    nonce = os.urandom(NONCE_BYTES)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_handle, destination.open("xb") as output_handle:
        output_handle.write(BACKUP_MAGIC)
        output_handle.write(nonce)
        while chunk := input_handle.read(CHUNK_BYTES):
            output_handle.write(cipher.encrypt(chunk))
        output_handle.write(cipher.digest())


def decrypt_file(source: Path, destination: Path, key: bytes) -> None:
    """Authenticate and decrypt an Aurum backup, deleting partial plaintext on failure."""

    total_size = source.stat().st_size
    minimum_size = len(BACKUP_MAGIC) + NONCE_BYTES + TAG_BYTES
    if total_size <= minimum_size:
        raise BackupValidationError("encrypted backup is truncated")
    try:
        with source.open("rb") as input_handle:
            if input_handle.read(len(BACKUP_MAGIC)) != BACKUP_MAGIC:
                raise BackupValidationError("unsupported backup format")
            nonce = input_handle.read(NONCE_BYTES)
            ciphertext_bytes = total_size - minimum_size
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as output_handle:
                remaining = ciphertext_bytes
                while remaining:
                    chunk = input_handle.read(min(CHUNK_BYTES, remaining))
                    if not chunk:
                        raise BackupValidationError("encrypted backup is truncated")
                    output_handle.write(cipher.decrypt(chunk))
                    remaining -= len(chunk)
                tag = input_handle.read(TAG_BYTES)
                cipher.verify(tag)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def create_archive(source_directory: Path, destination: Path) -> None:
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(source_directory.rglob("*")):
            if path.is_file() and path.resolve() != destination.resolve():
                archive.add(path, arcname=path.relative_to(source_directory))


def extract_archive(source: Path, destination: Path) -> None:
    """Extract only regular files whose resolved paths remain under the target."""

    destination_root = destination.resolve()
    with tarfile.open(source, "r:gz") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if destination_root not in target.parents or not member.isfile():
                raise BackupValidationError("backup archive contains an unsafe member")
        archive.extractall(destination, filter="data")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BackupValidationError("JSON document must be an object")
    return value


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise BackupValidationError("unsupported manifest version")
    required = {"backup_id", "created_at", "database", "object_storage", "configuration"}
    if not required.issubset(manifest):
        raise BackupValidationError("backup manifest is incomplete")


def retention_candidates(
    paths: Iterable[Path], *, now: datetime, retention_days: int
) -> list[Path]:
    """Return expired backup artifacts while always preserving the newest backup set."""

    if retention_days < 1:
        raise BackupValidationError("retention_days must be positive")
    archives = sorted(
        (path for path in paths if path.name.endswith(".aurum-backup")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    cutoff = now - timedelta(days=retention_days)
    expired: list[Path] = []
    for path in archives[1:]:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if modified < cutoff:
            expired.extend([path, path.with_suffix(path.suffix + ".sha256.json")])
    return [path for path in expired if path.exists()]
