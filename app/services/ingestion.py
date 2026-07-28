"""Lease-aware document ingestion orchestration and atomic version publication."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models.rag import Document, DocumentChunk, DocumentVersion, IngestionJob
from app.errors import ServiceUnavailableError
from app.providers.model_provider import EmbeddingProvider
from app.providers.object_storage import ObjectStorageProvider
from app.providers.pgvector_store import PgVectorStoreProvider
from app.providers.vector_store import VectorChunk
from app.rag.constants import (
    DOCUMENT_STATUS_PUBLISHED,
    DOCUMENT_VERSION_STATUS_AWAITING_PIPELINE,
    DOCUMENT_VERSION_STATUS_FAILED,
    DOCUMENT_VERSION_STATUS_PROCESSING,
    DOCUMENT_VERSION_STATUS_PUBLISHED,
    DOCUMENT_VERSION_STATUS_SUPERSEDED,
    INGESTION_JOB_STATUS_AWAITING_PIPELINE,
    INGESTION_JOB_STATUS_COMPLETED,
    INGESTION_JOB_STATUS_FAILED,
    INGESTION_JOB_STATUS_PROCESSING,
)
from app.rag.embeddings.dashscope import EmbeddingProviderFailure
from app.rag.loaders.text import TextParsingError, parse_text_document
from app.rag.splitters.deterministic import (
    DETERMINISTIC_CHUNKER_VERSION,
    ChunkingError,
    PreparedChunk,
    split_parsed_text,
)

logger = logging.getLogger(__name__)


class IngestionRetryRequested(RuntimeError):
    """Signal the synchronous Celery boundary to schedule a delayed retry."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class IngestionWork:
    job_id: UUID
    document_id: UUID
    document_version_id: UUID
    knowledge_base_id: UUID
    source_object_key: str
    source_content_hash: str
    mime_type: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    lease_owner: str


@dataclass(frozen=True, slots=True)
class PipelineFailure:
    code: str
    message: str
    retryable: bool


class IngestionPipeline:
    """Transform one immutable source version and publish all index state atomically."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        object_storage: ObjectStorageProvider,
        embedding_provider: EmbeddingProvider,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._object_storage = object_storage
        self._embedding_provider = embedding_provider
        self._settings = settings

    async def run(self, job_id: UUID) -> str:
        work = await self._claim(job_id)
        if work is None:
            return "skipped"
        try:
            source = await self._object_storage.get(work.source_object_key)
            if hashlib.sha256(source).hexdigest() != work.source_content_hash:
                raise _PermanentPipelineError(
                    PipelineFailure(
                        code="source_integrity_mismatch",
                        message="source object failed its integrity check",
                        retryable=False,
                    )
                )
            parsed = parse_text_document(source, work.mime_type)
            chunks = split_parsed_text(
                parsed,
                max_tokens=self._settings.chunk_max_tokens,
                overlap_tokens=self._settings.chunk_overlap_tokens,
                max_chunks=self._settings.document_max_chunks,
            )
            parsed_object_key = f"{work.source_object_key}/parsed/{parsed.parser_version}/text"
            parsed_bytes = parsed.text.encode("utf-8")
            parsed_hash = hashlib.sha256(parsed_bytes).hexdigest()
            await self._object_storage.put(
                parsed_object_key,
                parsed_bytes,
                "text/plain; charset=utf-8",
                metadata={
                    "sha256": parsed_hash,
                    "parser-version": parsed.parser_version,
                },
                checksum_sha256=parsed_hash,
            )
            await self._record_parsed(
                work,
                parsed_object_key=parsed_object_key,
                parser_version=parsed.parser_version,
            )
            vectors = await self._vectors_for_chunks(work, chunks)
            await self._publish(
                work,
                chunks=chunks,
                vectors=vectors,
                parsed_object_key=parsed_object_key,
                parser_version=parsed.parser_version,
            )
            return "completed"
        except _PermanentPipelineError as exc:
            await self._record_failure(work, exc.failure)
            return "failed"
        except (TextParsingError, ChunkingError) as exc:
            await self._record_failure(
                work,
                PipelineFailure(
                    code=(
                        "unsupported_document_format"
                        if isinstance(exc, TextParsingError)
                        else "document_chunking_failed"
                    ),
                    message=str(exc),
                    retryable=False,
                ),
            )
            return "failed"
        except EmbeddingProviderFailure as exc:
            retry = await self._record_failure(
                work,
                PipelineFailure(
                    code=exc.code,
                    message="document embedding failed",
                    retryable=exc.retryable,
                ),
            )
            if retry:
                raise IngestionRetryRequested(exc.code) from exc
            return "failed"
        except ServiceUnavailableError as exc:
            retry = await self._record_failure(
                work,
                PipelineFailure(
                    code="ingestion_dependency_unavailable",
                    message="an ingestion dependency is unavailable",
                    retryable=True,
                ),
            )
            if retry:
                raise IngestionRetryRequested("ingestion_dependency_unavailable") from exc
            return "failed"
        except Exception as exc:
            logger.exception("unexpected ingestion pipeline failure", extra={"job_id": str(job_id)})
            retry = await self._record_failure(
                work,
                PipelineFailure(
                    code="ingestion_internal_error",
                    message="an internal ingestion error occurred",
                    retryable=True,
                ),
            )
            if retry:
                raise IngestionRetryRequested("ingestion_internal_error") from exc
            return "failed"

    async def _claim(self, job_id: UUID) -> IngestionWork | None:
        now = datetime.now(UTC)
        lease_owner = f"ingestion-worker:{uuid4()}"
        async with self._session_factory() as session:
            job = await session.scalar(
                select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
            )
            if job is None:
                logger.warning("ingestion job was not found", extra={"job_id": str(job_id)})
                return None
            if job.status in {INGESTION_JOB_STATUS_COMPLETED, INGESTION_JOB_STATUS_FAILED}:
                return None
            if (
                job.status == INGESTION_JOB_STATUS_PROCESSING
                and job.lease_expires_at is not None
                and job.lease_expires_at > now
            ):
                return None
            if job.status == INGESTION_JOB_STATUS_PROCESSING:
                if job.retry_count >= job.max_retries:
                    await self._fail_exhausted_claim(session, job, now=now)
                    return None
                job.retry_count += 1

            document = await session.scalar(
                select(Document)
                .where(Document.id == job.document_id)
                .with_for_update()
            )
            version = await session.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.id == job.document_version_id)
                .with_for_update()
            )
            if (
                document is None
                or version is None
                or document.deleted_at is not None
                or not document.is_enabled
            ):
                await self._fail_exhausted_claim(
                    session,
                    job,
                    now=now,
                    code="ingestion_source_unavailable",
                    message="document source is unavailable",
                )
                return None
            if version.status == DOCUMENT_VERSION_STATUS_PUBLISHED:
                job.status = INGESTION_JOB_STATUS_COMPLETED
                job.progress = 100
                job.completed_at = version.published_at or now
                job.lease_owner = None
                job.lease_expires_at = None
                await session.commit()
                return None

            job.status = INGESTION_JOB_STATUS_PROCESSING
            job.progress = max(job.progress, 5)
            job.started_at = job.started_at or now
            job.completed_at = None
            job.error_code = None
            job.error_message = None
            job.error_detail = None
            job.lease_owner = lease_owner
            job.lease_expires_at = now + timedelta(
                seconds=self._settings.ingestion_lease_seconds
            )
            version.status = DOCUMENT_VERSION_STATUS_PROCESSING
            version.error_code = None
            version.error_message = None
            await session.commit()
            return IngestionWork(
                job_id=job.id,
                document_id=document.id,
                document_version_id=version.id,
                knowledge_base_id=version.knowledge_base_id,
                source_object_key=version.source_object_key,
                source_content_hash=version.content_hash,
                mime_type=document.mime_type,
                embedding_provider=version.embedding_provider,
                embedding_model=version.embedding_model,
                embedding_dimensions=version.embedding_dimensions,
                lease_owner=lease_owner,
            )

    async def _fail_exhausted_claim(
        self,
        session: AsyncSession,
        job: IngestionJob,
        *,
        now: datetime,
        code: str = "ingestion_attempts_exhausted",
        message: str = "ingestion attempts were exhausted",
    ) -> None:
        version = await session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.id == job.document_version_id)
            .with_for_update()
        )
        job.status = INGESTION_JOB_STATUS_FAILED
        job.completed_at = now
        job.error_code = code
        job.error_message = message
        job.error_detail = {"retryable": False}
        job.lease_owner = None
        job.lease_expires_at = None
        if version is not None:
            version.status = DOCUMENT_VERSION_STATUS_FAILED
            version.completed_at = now
            version.error_code = code
            version.error_message = message
        await session.commit()

    async def _record_parsed(
        self,
        work: IngestionWork,
        *,
        parsed_object_key: str,
        parser_version: str,
    ) -> None:
        async with self._session_factory() as session:
            job = await self._owned_job(session, work)
            if job is None:
                raise RuntimeError("ingestion job lease was lost")
            version = await session.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.id == work.document_version_id)
                .with_for_update()
            )
            if version is None:
                raise RuntimeError("document version disappeared during ingestion")
            version.parsed_object_key = parsed_object_key
            version.parser_version = parser_version
            version.chunker_version = DETERMINISTIC_CHUNKER_VERSION
            job.progress = max(job.progress, 35)
            await session.commit()

    async def _vectors_for_chunks(
        self,
        work: IngestionWork,
        chunks: list[PreparedChunk],
    ) -> list[list[float]]:
        if (
            self._embedding_provider.provider_name != work.embedding_provider
            or self._embedding_provider.model_name != work.embedding_model
            or self._embedding_provider.dimensions != work.embedding_dimensions
        ):
            raise _PermanentPipelineError(
                PipelineFailure(
                    code="embedding_index_configuration_mismatch",
                    message="embedding provider does not match the document index",
                    retryable=False,
                )
            )
        reusable = await self._reusable_embeddings(work, chunks)
        missing_hashes: list[str] = []
        missing_texts: list[str] = []
        seen_missing: set[str] = set()
        for chunk in chunks:
            if chunk.content_hash not in reusable and chunk.content_hash not in seen_missing:
                seen_missing.add(chunk.content_hash)
                missing_hashes.append(chunk.content_hash)
                missing_texts.append(chunk.content)
        generated = await self._embedding_provider.embed(missing_texts)
        if len(generated) != len(missing_hashes):
            raise EmbeddingProviderFailure("embedding_response_invalid", retryable=True)
        reusable.update(zip(missing_hashes, generated, strict=True))
        vectors = [reusable[chunk.content_hash] for chunk in chunks]
        await self._update_progress(work, 75)
        return vectors

    async def _reusable_embeddings(
        self,
        work: IngestionWork,
        chunks: list[PreparedChunk],
    ) -> dict[str, list[float]]:
        hashes = {chunk.content_hash for chunk in chunks}
        async with self._session_factory() as session:
            statement = (
                select(DocumentChunk.content_hash, DocumentChunk.embedding)
                .join(
                    DocumentVersion,
                    DocumentVersion.id == DocumentChunk.document_version_id,
                )
                .where(
                    DocumentChunk.knowledge_base_id == work.knowledge_base_id,
                    DocumentChunk.content_hash.in_(hashes),
                    DocumentChunk.embedding.is_not(None),
                    DocumentVersion.embedding_provider == work.embedding_provider,
                    DocumentVersion.embedding_model == work.embedding_model,
                    DocumentVersion.embedding_dimensions == work.embedding_dimensions,
                    DocumentVersion.status.in_(
                        {
                            DOCUMENT_VERSION_STATUS_PUBLISHED,
                            DOCUMENT_VERSION_STATUS_SUPERSEDED,
                        }
                    ),
                )
                .order_by(DocumentVersion.published_at.desc().nullslast())
            )
            rows = (await session.execute(statement)).all()
        reusable: dict[str, list[float]] = {}
        for content_hash, raw_vector in rows:
            vector = [float(value) for value in raw_vector]
            if (
                content_hash not in reusable
                and len(vector) == work.embedding_dimensions
            ):
                reusable[content_hash] = vector
        return reusable

    async def _update_progress(self, work: IngestionWork, progress: int) -> None:
        async with self._session_factory() as session:
            job = await self._owned_job(session, work)
            if job is None:
                raise RuntimeError("ingestion job lease was lost")
            job.progress = max(job.progress, progress)
            await session.commit()

    async def _publish(
        self,
        work: IngestionWork,
        *,
        chunks: list[PreparedChunk],
        vectors: list[list[float]],
        parsed_object_key: str,
        parser_version: str,
    ) -> None:
        if len(chunks) != len(vectors):
            raise RuntimeError("chunk/vector cardinality mismatch")
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            job = await self._owned_job(session, work)
            if job is None:
                raise RuntimeError("ingestion job lease was lost")
            document = await session.scalar(
                select(Document)
                .where(Document.id == work.document_id)
                .with_for_update()
            )
            version = await session.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.id == work.document_version_id)
                .with_for_update()
            )
            if document is None or version is None:
                raise RuntimeError("document scope disappeared during publication")

            vector_store = PgVectorStoreProvider(session)
            await vector_store.delete_version_chunks(
                document_version_id=work.document_version_id
            )
            persisted_chunks: list[DocumentChunk] = []
            vector_chunks: list[VectorChunk] = []
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk_id = uuid5(
                    work.document_version_id,
                    f"{chunk.chunk_index}:{chunk.content_hash}",
                )
                persisted_chunks.append(
                    DocumentChunk(
                        id=chunk_id,
                        document_version_id=work.document_version_id,
                        knowledge_base_id=work.knowledge_base_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        content_hash=chunk.content_hash,
                        page_number=None,
                        section_path=chunk.section_path,
                        sheet_name=None,
                        row_start=None,
                        row_end=None,
                        char_start=chunk.char_start,
                        char_end=chunk.char_end,
                        metadata_json=chunk.metadata,
                        token_count=chunk.token_count,
                    )
                )
                vector_chunks.append(
                    VectorChunk(
                        chunk_id=chunk_id,
                        document_version_id=work.document_version_id,
                        knowledge_base_id=work.knowledge_base_id,
                        embedding=vector,
                    )
                )
            session.add_all(persisted_chunks)
            await session.flush()
            await vector_store.replace_version_chunks(
                document_version_id=work.document_version_id,
                chunks=vector_chunks,
            )

            if (
                document.current_published_version_id is not None
                and document.current_published_version_id != version.id
            ):
                previous = await session.scalar(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.id == document.current_published_version_id
                    )
                    .with_for_update()
                )
                if previous is not None:
                    previous.status = DOCUMENT_VERSION_STATUS_SUPERSEDED

            version.status = DOCUMENT_VERSION_STATUS_PUBLISHED
            version.parser_version = parser_version
            version.chunker_version = DETERMINISTIC_CHUNKER_VERSION
            version.parsed_object_key = parsed_object_key
            version.completed_at = now
            version.published_at = now
            version.error_code = None
            version.error_message = None
            document.current_published_version_id = version.id
            document.status = DOCUMENT_STATUS_PUBLISHED
            job.status = INGESTION_JOB_STATUS_COMPLETED
            job.progress = 100
            job.completed_at = now
            job.error_code = None
            job.error_message = None
            job.error_detail = None
            job.lease_owner = None
            job.lease_expires_at = None
            await session.commit()

    async def _record_failure(
        self,
        work: IngestionWork,
        failure: PipelineFailure,
    ) -> bool:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            job = await self._owned_job(session, work)
            if job is None:
                return False
            version = await session.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.id == work.document_version_id)
                .with_for_update()
            )
            should_retry = failure.retryable and job.retry_count < job.max_retries
            if should_retry:
                job.retry_count += 1
                job.status = INGESTION_JOB_STATUS_AWAITING_PIPELINE
                job.completed_at = None
                if version is not None:
                    version.status = DOCUMENT_VERSION_STATUS_AWAITING_PIPELINE
                    version.completed_at = None
            else:
                job.status = INGESTION_JOB_STATUS_FAILED
                job.completed_at = now
                if version is not None:
                    version.status = DOCUMENT_VERSION_STATUS_FAILED
                    version.completed_at = now
            job.error_code = failure.code
            job.error_message = failure.message
            job.error_detail = {"retryable": should_retry}
            job.lease_owner = None
            job.lease_expires_at = None
            if version is not None:
                version.error_code = failure.code
                version.error_message = failure.message
            await session.commit()
            return should_retry

    async def _owned_job(
        self,
        session: AsyncSession,
        work: IngestionWork,
    ) -> IngestionJob | None:
        return cast(
            IngestionJob | None,
            await session.scalar(
                select(IngestionJob)
                .where(
                    IngestionJob.id == work.job_id,
                    IngestionJob.status == INGESTION_JOB_STATUS_PROCESSING,
                    IngestionJob.lease_owner == work.lease_owner,
                )
                .with_for_update()
            )
        )


class _PermanentPipelineError(RuntimeError):
    def __init__(self, failure: PipelineFailure) -> None:
        super().__init__(failure.code)
        self.failure = failure
