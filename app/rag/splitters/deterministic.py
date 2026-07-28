"""Deterministic multilingual lexical chunking with normalized-text offsets."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.rag.loaders.text import ParsedTextDocument

DETERMINISTIC_CHUNKER_VERSION = "aurum-lexical-v1"
_TOKEN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff]|"
    r"[A-Za-z0-9]+(?:[._/-][A-Za-z0-9]+)*|"
    r"[^\s]",
    re.UNICODE,
)


class ChunkingError(ValueError):
    """A safe, non-retryable failure caused by bounded chunking rules."""


@dataclass(frozen=True, slots=True)
class PreparedChunk:
    chunk_index: int
    content: str
    content_hash: str
    token_count: int
    char_start: int
    char_end: int
    section_path: str | None
    metadata: dict[str, str]


def split_parsed_text(
    parsed: ParsedTextDocument,
    *,
    max_tokens: int,
    overlap_tokens: int,
    max_chunks: int,
) -> list[PreparedChunk]:
    """Split normalized text reproducibly while preserving source coordinates."""

    if max_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ChunkingError("chunk token limits are not valid")
    token_spans = list(_TOKEN.finditer(parsed.text))
    if not token_spans:
        raise ChunkingError("document contains no indexable text")

    chunks: list[PreparedChunk] = []
    start_token = 0
    while start_token < len(token_spans):
        if len(chunks) >= max_chunks:
            raise ChunkingError("document exceeds the configured chunk count limit")
        end_token = min(len(token_spans), start_token + max_tokens)
        end_token = _prefer_paragraph_boundary(
            parsed.text,
            token_spans,
            start_token=start_token,
            end_token=end_token,
            max_tokens=max_tokens,
        )
        char_start = token_spans[start_token].start()
        char_end = token_spans[end_token - 1].end()
        content = parsed.text[char_start:char_end]
        chunks.append(
            PreparedChunk(
                chunk_index=len(chunks),
                content=content,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                token_count=end_token - start_token,
                char_start=char_start,
                char_end=char_end,
                section_path=parsed.section_path_at(char_start),
                metadata={"offset_basis": "normalized_text"},
            )
        )
        if end_token == len(token_spans):
            break
        start_token = end_token - overlap_tokens
    return chunks


def _prefer_paragraph_boundary(
    text: str,
    token_spans: list[re.Match[str]],
    *,
    start_token: int,
    end_token: int,
    max_tokens: int,
) -> int:
    if end_token == len(token_spans):
        return end_token
    minimum = start_token + max(1, max_tokens // 2)
    for candidate in range(end_token, minimum, -1):
        previous_end = token_spans[candidate - 1].end()
        next_start = token_spans[candidate].start()
        if "\n\n" in text[previous_end:next_start]:
            return candidate
    return end_token
