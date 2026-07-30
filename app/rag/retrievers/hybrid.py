"""Deterministic Reciprocal Rank Fusion for Dense and Sparse candidates."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.providers.sparse_store import SparseSearchResult
from app.providers.vector_store import VectorSearchResult


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    """A fused retrieval hit with a normalized RRF score."""

    chunk_id: UUID
    document_version_id: UUID
    knowledge_base_id: UUID
    score: float
    retrieval_source: str


class _RankedHit(Protocol):
    @property
    def chunk_id(self) -> UUID: ...

    @property
    def document_version_id(self) -> UUID: ...

    @property
    def knowledge_base_id(self) -> UUID: ...


def reciprocal_rank_fuse(
    *,
    dense_hits: Sequence[VectorSearchResult],
    sparse_hits: Sequence[SparseSearchResult],
    limit: int,
    rrf_k: int,
) -> list[HybridSearchResult]:
    """Fuse ranked lists and normalize the maximum two-list score to one."""

    if limit <= 0:
        return []
    if rrf_k < 1:
        raise ValueError("RRF rank constant must be positive")

    identities: dict[UUID, tuple[UUID, UUID]] = {}
    scores: dict[UUID, float] = {}
    sources: dict[UUID, set[str]] = {}
    best_ranks: dict[UUID, tuple[int, int]] = {}
    ranked_lists: tuple[tuple[str, Sequence[_RankedHit]], ...] = (
        ("dense", dense_hits),
        ("sparse", sparse_hits),
    )
    missing_rank = len(dense_hits) + len(sparse_hits) + 1

    for source_index, (source_name, hits) in enumerate(ranked_lists):
        seen: set[UUID] = set()
        for rank, hit in enumerate(hits, start=1):
            if hit.chunk_id in seen:
                continue
            seen.add(hit.chunk_id)
            identity = (hit.document_version_id, hit.knowledge_base_id)
            previous_identity = identities.setdefault(hit.chunk_id, identity)
            if previous_identity != identity:
                raise ValueError("retrieval providers returned inconsistent chunk scope")
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            sources.setdefault(hit.chunk_id, set()).add(source_name)
            dense_rank, sparse_rank = best_ranks.get(
                hit.chunk_id,
                (missing_rank, missing_rank),
            )
            if source_index == 0:
                dense_rank = rank
            else:
                sparse_rank = rank
            best_ranks[hit.chunk_id] = (dense_rank, sparse_rank)

    maximum_score = 2.0 / (rrf_k + 1)
    ordered_ids = sorted(
        scores,
        key=lambda chunk_id: (
            -scores[chunk_id],
            min(best_ranks[chunk_id]),
            best_ranks[chunk_id],
            str(chunk_id),
        ),
    )
    fused: list[HybridSearchResult] = []
    for chunk_id in ordered_ids[:limit]:
        document_version_id, knowledge_base_id = identities[chunk_id]
        hit_sources = sources[chunk_id]
        retrieval_source = (
            "hybrid" if len(hit_sources) == 2 else next(iter(hit_sources))
        )
        fused.append(
            HybridSearchResult(
                chunk_id=chunk_id,
                document_version_id=document_version_id,
                knowledge_base_id=knowledge_base_id,
                score=min(1.0, scores[chunk_id] / maximum_score),
                retrieval_source=retrieval_source,
            )
        )
    return fused
