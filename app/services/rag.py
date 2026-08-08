"""User-owned personal knowledge-base and document use cases."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.rag import (
    Document,
    DocumentUploadRequest,
    DocumentVersion,
    IngestionJob,
    KnowledgeBase,
    OutboxEvent,
)
from app.db.repositories.identity import AuditRepository
from app.db.repositories.rag import RagRepository
from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.providers.object_storage import ObjectStorageProvider
from app.rag.constants import (
    DOCUMENT_STATUS_DELETED,
    DOCUMENT_STATUS_DISABLED,
    DOCUMENT_STATUS_UPLOADED,
    DOCUMENT_VERSION_STATUS_AWAITING_PIPELINE,
    DOCUMENT_VERSION_STATUS_FAILED,
    DOCUMENT_VERSION_STATUS_UPLOADING,
    INGESTION_JOB_STATUS_AWAITING_PIPELINE,
    INGESTION_JOB_STATUS_FAILED,
    OUTBOX_DEFAULT_MAX_ATTEMPTS,
    OUTBOX_EVENT_INGESTION_REQUESTED,
    OUTBOX_STATUS_FAILED,
    OUTBOX_STATUS_PENDING,
    UPLOAD_REQUEST_STATUS_ACTIVATED,
    UPLOAD_REQUEST_STATUS_FAILED,
    UPLOAD_REQUEST_STATUS_RESERVED,
    UPLOAD_REQUEST_STATUS_STORED,
    UPLOAD_REQUEST_TARGET_DOCUMENT,
    UPLOAD_REQUEST_TARGET_KNOWLEDGE_BASE,
)
from app.rag.upload_validation import ValidatedDocumentUpload


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    items: list[T]
    total: int
    page: int
    page_size: int


class PersonalKnowledgeService:
    """Keep personal knowledge changes owner-scoped, atomic, and auditable."""

    def __init__(
        self,
        session: AsyncSession,
        actor_user_id: UUID,
        *,
        ingestion_max_retries: int = 3,
        ingestion_manual_retry_limit: int = 5,
    ) -> None:
        self._session = session
        self._actor_user_id = actor_user_id
        self._ingestion_max_retries = ingestion_max_retries
        self._ingestion_manual_retry_limit = ingestion_manual_retry_limit
        self._repository = RagRepository(session)
        self._audit = AuditRepository(session)

    async def _commit(self, conflict_message: str) -> None:
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(conflict_message) from exc

    def _audit_event(
        self,
        action: str,
        resource_type: str,
        resource_id: UUID,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._audit.add(
            action=action,
            actor_user_id=self._actor_user_id,
            resource_type=resource_type,
            resource_id=str(resource_id),
            ip=None,
            user_agent=None,
            detail=detail,
        )

    async def _knowledge_base(
        self,
        knowledge_base_id: UUID,
        *,
        for_update: bool = False,
    ) -> KnowledgeBase:
        knowledge_base = await self._repository.get_knowledge_base(
            knowledge_base_id,
            owner_user_id=self._actor_user_id,
            for_update=for_update,
        )
        if knowledge_base is None:
            raise NotFoundError("knowledge base was not found")
        return knowledge_base

    async def create_knowledge_base(
        self,
        *,
        name: str,
        description: str | None,
    ) -> KnowledgeBase:
        knowledge_base = await self._repository.add(
            KnowledgeBase(
                name=name,
                description=description,
                owner_user_id=self._actor_user_id,
                status="active",
                search_enabled=True,
            )
        )
        self._audit_event(
            "rag.knowledge_base.created",
            "knowledge_base",
            knowledge_base.id,
            detail={"name": name},
        )
        await self._commit("a knowledge base with this name already exists")
        return knowledge_base

    async def list_knowledge_bases(self, *, page: int, page_size: int) -> PageResult[KnowledgeBase]:
        items, total = await self._repository.list_knowledge_bases(
            owner_user_id=self._actor_user_id,
            page=page,
            page_size=page_size,
        )
        return PageResult(items=items, total=total, page=page, page_size=page_size)

    async def get_knowledge_base(self, knowledge_base_id: UUID) -> KnowledgeBase:
        return await self._knowledge_base(knowledge_base_id)

    async def update_knowledge_base(
        self,
        knowledge_base_id: UUID,
        *,
        name: str | None,
        description: str | None,
        status: str | None,
        search_enabled: bool | None,
        fields_set: set[str],
    ) -> KnowledgeBase:
        knowledge_base = await self._knowledge_base(knowledge_base_id)
        if "name" in fields_set:
            knowledge_base.name = name or knowledge_base.name
        if "description" in fields_set:
            knowledge_base.description = description
        if "status" in fields_set and status is not None:
            knowledge_base.status = status
        if "search_enabled" in fields_set and search_enabled is not None:
            knowledge_base.search_enabled = search_enabled
        await self._session.flush()
        self._audit_event("rag.knowledge_base.updated", "knowledge_base", knowledge_base.id)
        await self._commit("a knowledge base with this name already exists")
        return knowledge_base

    async def disable_knowledge_base(self, knowledge_base_id: UUID) -> KnowledgeBase:
        knowledge_base = await self._knowledge_base(knowledge_base_id)
        knowledge_base.status = "disabled"
        await self._session.flush()
        self._audit_event("rag.knowledge_base.disabled", "knowledge_base", knowledge_base.id)
        await self._commit("unable to disable knowledge base")
        return knowledge_base

    async def delete_knowledge_base(self, knowledge_base_id: UUID) -> None:
        knowledge_base = await self._knowledge_base(knowledge_base_id)
        knowledge_base.status = "disabled"
        knowledge_base.deleted_at = datetime.now(UTC)
        await self._session.flush()
        self._audit_event("rag.knowledge_base.deleted", "knowledge_base", knowledge_base.id)
        await self._commit("unable to delete knowledge base")

    async def _document(self, document_id: UUID) -> Document:
        document = await self._repository.get_document(
            document_id, owner_user_id=self._actor_user_id
        )
        if document is None:
            raise NotFoundError("document was not found")
        return document

    async def _active_knowledge_base(self, knowledge_base_id: UUID) -> KnowledgeBase:
        knowledge_base = await self._knowledge_base(knowledge_base_id)
        if knowledge_base.status != "active":
            raise BusinessRuleError("disabled knowledge bases cannot receive documents")
        return knowledge_base

    async def create_document_upload(
        self,
        *,
        knowledge_base_id: UUID,
        upload: ValidatedDocumentUpload,
        idempotency_key: str,
        storage: ObjectStorageProvider,
    ) -> tuple[Document, DocumentVersion, IngestionJob]:
        replay = await self._repository.get_upload_request(idempotency_key)
        if replay is not None:
            return await self._resume_upload_request(
                request=replay,
                expected_target_type=UPLOAD_REQUEST_TARGET_KNOWLEDGE_BASE,
                expected_target_id=knowledge_base_id,
                upload=upload,
                storage=storage,
            )
        knowledge_base = await self._active_knowledge_base(knowledge_base_id)

        document_id = uuid4()
        version_id = uuid4()
        object_key = self._object_key(
            self._actor_user_id, knowledge_base.id, document_id, version_id
        )
        document = Document(
            id=document_id,
            knowledge_base_id=knowledge_base.id,
            name=upload.filename,
            object_key=object_key,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            content_hash=upload.content_hash,
            status=DOCUMENT_STATUS_UPLOADED,
            uploaded_by=self._actor_user_id,
        )
        version = self._new_version(
            document=document,
            version_id=version_id,
            version_number=1,
            object_key=object_key,
            upload=upload,
            knowledge_base=knowledge_base,
        )
        request = self._new_upload_request(
            idempotency_key=idempotency_key,
            target_type=UPLOAD_REQUEST_TARGET_KNOWLEDGE_BASE,
            target_id=knowledge_base.id,
            document=document,
            version=version,
            upload=upload,
        )
        try:
            await self._repository.add(document)
            await self._repository.add(version)
            await self._repository.add(request)
            self._audit_event(
                "rag.document.upload_reserved",
                "document",
                document.id,
                detail={"knowledge_base_id": str(knowledge_base.id), "version": version.version},
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            winner = await self._repository.get_upload_request(idempotency_key)
            if winner is None:
                raise ConflictError("unable to reserve document upload") from exc
            return await self._resume_upload_request(
                request=winner,
                expected_target_type=UPLOAD_REQUEST_TARGET_KNOWLEDGE_BASE,
                expected_target_id=knowledge_base_id,
                upload=upload,
                storage=storage,
            )
        return await self._resume_upload_request(
            request=request,
            expected_target_type=UPLOAD_REQUEST_TARGET_KNOWLEDGE_BASE,
            expected_target_id=knowledge_base_id,
            upload=upload,
            storage=storage,
        )

    async def create_document_version_upload(
        self,
        *,
        document_id: UUID,
        upload: ValidatedDocumentUpload,
        idempotency_key: str,
        storage: ObjectStorageProvider,
    ) -> tuple[Document, DocumentVersion, IngestionJob]:
        replay = await self._repository.get_upload_request(idempotency_key)
        if replay is not None:
            return await self._resume_upload_request(
                request=replay,
                expected_target_type=UPLOAD_REQUEST_TARGET_DOCUMENT,
                expected_target_id=document_id,
                upload=upload,
                storage=storage,
            )

        document = await self._repository.get_document(
            document_id, owner_user_id=self._actor_user_id, for_update=True
        )
        if document is None or document.is_enabled is False:
            raise NotFoundError("document was not found")
        replay = await self._repository.get_upload_request(idempotency_key)
        if replay is not None:
            return await self._resume_upload_request(
                request=replay,
                expected_target_type=UPLOAD_REQUEST_TARGET_DOCUMENT,
                expected_target_id=document_id,
                upload=upload,
                storage=storage,
            )
        knowledge_base = await self._active_knowledge_base(document.knowledge_base_id)
        if await self._repository.get_version_by_hash(
            document_id=document.id, content_hash=upload.content_hash
        ):
            raise ConflictError("an identical document version already exists")
        versions = await self._repository.list_document_versions(document_id=document.id)
        version_number = max((item.version for item in versions), default=0) + 1
        version_id = uuid4()
        version = self._new_version(
            document=document,
            version_id=version_id,
            version_number=version_number,
            object_key=self._object_key(
                self._actor_user_id, knowledge_base.id, document.id, version_id
            ),
            upload=upload,
            knowledge_base=knowledge_base,
        )
        request = self._new_upload_request(
            idempotency_key=idempotency_key,
            target_type=UPLOAD_REQUEST_TARGET_DOCUMENT,
            target_id=document.id,
            document=document,
            version=version,
            upload=upload,
        )
        try:
            await self._repository.add(version)
            await self._repository.add(request)
            self._audit_event(
                "rag.document.version_reserved",
                "document",
                document.id,
                detail={"version": version.version},
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            winner = await self._repository.get_upload_request(idempotency_key)
            if winner is None:
                raise ConflictError("unable to reserve document version upload") from exc
            return await self._resume_upload_request(
                request=winner,
                expected_target_type=UPLOAD_REQUEST_TARGET_DOCUMENT,
                expected_target_id=document_id,
                upload=upload,
                storage=storage,
            )
        return await self._resume_upload_request(
            request=request,
            expected_target_type=UPLOAD_REQUEST_TARGET_DOCUMENT,
            expected_target_id=document_id,
            upload=upload,
            storage=storage,
        )

    def _new_version(
        self,
        *,
        document: Document,
        version_id: UUID,
        version_number: int,
        object_key: str,
        upload: ValidatedDocumentUpload,
        knowledge_base: KnowledgeBase,
    ) -> DocumentVersion:
        return DocumentVersion(
            id=version_id,
            document_id=document.id,
            knowledge_base_id=knowledge_base.id,
            version=version_number,
            source_object_key=object_key,
            content_hash=upload.content_hash,
            pipeline_version=knowledge_base.pipeline_version,
            embedding_provider=knowledge_base.embedding_provider,
            embedding_model=knowledge_base.embedding_model,
            embedding_dimensions=knowledge_base.embedding_dimensions,
            status=DOCUMENT_VERSION_STATUS_UPLOADING,
            metadata_json=upload.metadata,
        )

    def _new_upload_request(
        self,
        *,
        idempotency_key: str,
        target_type: str,
        target_id: UUID,
        document: Document,
        version: DocumentVersion,
        upload: ValidatedDocumentUpload,
    ) -> DocumentUploadRequest:
        return DocumentUploadRequest(
            idempotency_key=idempotency_key,
            target_type=target_type,
            target_id=target_id,
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
            document_version_id=version.id,
            filename=upload.filename,
            mime_type=upload.mime_type,
            content_hash=upload.content_hash,
            metadata_hash=self._metadata_hash(upload.metadata),
            status=UPLOAD_REQUEST_STATUS_RESERVED,
            created_by=self._actor_user_id,
        )

    @staticmethod
    def _metadata_hash(metadata: dict[str, str]) -> str:
        canonical = json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _validate_upload_replay(
        self,
        *,
        request: DocumentUploadRequest,
        expected_target_type: str,
        expected_target_id: UUID,
        upload: ValidatedDocumentUpload,
    ) -> None:
        if (
            request.created_by != self._actor_user_id
            or request.target_type != expected_target_type
            or request.target_id != expected_target_id
            or request.filename != upload.filename
            or request.mime_type != upload.mime_type
            or request.content_hash != upload.content_hash
            or request.metadata_hash != self._metadata_hash(upload.metadata)
        ):
            raise ConflictError("idempotency key was already used for another upload")

    async def _resume_upload_request(
        self,
        *,
        request: DocumentUploadRequest,
        expected_target_type: str,
        expected_target_id: UUID,
        upload: ValidatedDocumentUpload,
        storage: ObjectStorageProvider,
    ) -> tuple[Document, DocumentVersion, IngestionJob]:
        self._validate_upload_replay(
            request=request,
            expected_target_type=expected_target_type,
            expected_target_id=expected_target_id,
            upload=upload,
        )
        if request.status == UPLOAD_REQUEST_STATUS_ACTIVATED:
            return await self._load_upload_result(request)
        document = await self._repository.get_document(request.document_id)
        version = await self._repository.get_document_version(request.document_version_id)
        if document is None or version is None:
            raise ConflictError("idempotent upload reservation is no longer available")
        return await self._store_and_activate(
            request=request,
            document=document,
            version=version,
            upload=upload,
            storage=storage,
        )

    @staticmethod
    def _object_key(
        owner_user_id: UUID,
        knowledge_base_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> str:
        return (
            f"users/{owner_user_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/"
            f"versions/{version_id}/source"
        )

    async def _store_and_activate(
        self,
        *,
        request: DocumentUploadRequest,
        document: Document,
        version: DocumentVersion,
        upload: ValidatedDocumentUpload,
        storage: ObjectStorageProvider,
    ) -> tuple[Document, DocumentVersion, IngestionJob]:
        try:
            await storage.put(
                version.source_object_key,
                upload.content,
                upload.mime_type,
                metadata={"sha256": upload.content_hash},
                checksum_sha256=upload.content_hash,
            )
            stored = await storage.head(version.source_object_key)
            if (
                stored.content_length != upload.size_bytes
                or stored.content_type != upload.mime_type
                or stored.metadata.get("sha256") != upload.content_hash
            ):
                raise BusinessRuleError("stored document verification failed")
        except Exception as exc:
            await self._record_upload_failure(request.idempotency_key)
            if isinstance(exc, BusinessRuleError):
                raise
            raise BusinessRuleError("document object could not be stored") from exc

        persisted_request = await self._repository.get_upload_request(
            request.idempotency_key,
            for_update=True,
        )
        if persisted_request is None:
            raise ConflictError("document upload reservation was not found")
        if persisted_request.status == UPLOAD_REQUEST_STATUS_ACTIVATED:
            return await self._load_upload_result(persisted_request)
        persisted_version = await self._repository.get_document_version(
            persisted_request.document_version_id
        )
        persisted_document = await self._repository.get_document(persisted_request.document_id)
        if persisted_version is None or persisted_document is None:
            raise ConflictError("document upload reservation is no longer available")
        persisted_request.status = UPLOAD_REQUEST_STATUS_STORED
        persisted_request.error_code = None
        persisted_request.error_detail = None
        persisted_version.status = DOCUMENT_VERSION_STATUS_AWAITING_PIPELINE
        persisted_version.error_code = None
        persisted_version.error_message = None
        persisted_document.object_key = persisted_version.source_object_key
        persisted_document.name = upload.filename
        persisted_document.mime_type = upload.mime_type
        persisted_document.size_bytes = upload.size_bytes
        persisted_document.content_hash = upload.content_hash
        await self._session.commit()

        return await self._activate_upload_request(persisted_request.idempotency_key)

    async def _record_upload_failure(self, idempotency_key: str) -> None:
        request = await self._repository.get_upload_request(idempotency_key, for_update=True)
        if request is None or request.status in {
            UPLOAD_REQUEST_STATUS_STORED,
            UPLOAD_REQUEST_STATUS_ACTIVATED,
        }:
            await self._session.rollback()
            return
        version = await self._repository.get_document_version(request.document_version_id)
        request.status = UPLOAD_REQUEST_STATUS_FAILED
        request.error_code = "storage_verification_failed"
        request.error_detail = {"message": "document object could not be stored safely"}
        if version is not None:
            version.status = DOCUMENT_VERSION_STATUS_FAILED
            version.error_code = "storage_verification_failed"
            version.error_message = "document object could not be stored safely"
        self._audit_event("rag.document.upload_failed", "document", request.document_id)
        await self._session.commit()

    async def _activate_upload_request(
        self,
        idempotency_key: str,
    ) -> tuple[Document, DocumentVersion, IngestionJob]:
        request = await self._repository.get_upload_request(idempotency_key, for_update=True)
        if request is None:
            raise ConflictError("document upload reservation was not found")
        if request.status == UPLOAD_REQUEST_STATUS_ACTIVATED:
            return await self._load_upload_result(request)
        if request.status != UPLOAD_REQUEST_STATUS_STORED:
            raise ConflictError("document upload object is not ready for activation")
        document = await self._repository.get_document(request.document_id)
        version = await self._repository.get_document_version(request.document_version_id)
        if document is None or version is None:
            raise ConflictError("document upload reservation is no longer available")
        try:
            job = IngestionJob(
                document_id=document.id,
                document_version_id=version.id,
                idempotency_key=request.idempotency_key,
                status=INGESTION_JOB_STATUS_AWAITING_PIPELINE,
                max_retries=self._ingestion_max_retries,
            )
            await self._repository.add(job)
            await self._repository.add(
                OutboxEvent(
                    ingestion_job_id=job.id,
                    event_type=OUTBOX_EVENT_INGESTION_REQUESTED,
                    payload={"schema_version": 1, "ingestion_job_id": str(job.id)},
                    status=OUTBOX_STATUS_PENDING,
                    max_attempts=OUTBOX_DEFAULT_MAX_ATTEMPTS,
                )
            )
            request.ingestion_job_id = job.id
            request.status = UPLOAD_REQUEST_STATUS_ACTIVATED
            request.error_code = None
            request.error_detail = None
            self._audit_event(
                "rag.ingestion.requested",
                "ingestion_job",
                job.id,
                detail={"document_id": str(document.id), "document_version_id": str(version.id)},
            )
            await self._session.commit()
            return document, version, job
        except IntegrityError as exc:
            await self._session.rollback()
            winner = await self._repository.get_upload_request(idempotency_key)
            if winner is None or winner.status != UPLOAD_REQUEST_STATUS_ACTIVATED:
                raise ConflictError("unable to create document ingestion job") from exc
            return await self._load_upload_result(winner)

    async def _load_upload_result(
        self,
        request: DocumentUploadRequest,
    ) -> tuple[Document, DocumentVersion, IngestionJob]:
        document = await self._repository.get_document(request.document_id)
        version = await self._repository.get_document_version(request.document_version_id)
        job = (
            await self._repository.get_ingestion_job(request.ingestion_job_id)
            if request.ingestion_job_id is not None
            else None
        )
        if document is None or version is None or job is None:
            raise ConflictError("idempotent upload result is incomplete")
        return document, version, job

    async def list_documents(
        self, *, knowledge_base_id: UUID, page: int, page_size: int
    ) -> PageResult[Document]:
        await self._knowledge_base(knowledge_base_id)
        items, total = await self._repository.list_documents(
            knowledge_base_id=knowledge_base_id, page=page, page_size=page_size
        )
        return PageResult(items=items, total=total, page=page, page_size=page_size)

    async def get_document(self, document_id: UUID) -> Document:
        return await self._document(document_id)

    async def list_document_versions(self, document_id: UUID) -> list[DocumentVersion]:
        await self._document(document_id)
        return await self._repository.list_document_versions(document_id=document_id)

    async def get_document_version(self, document_version_id: UUID) -> DocumentVersion:
        version = await self._repository.get_document_version(
            document_version_id, owner_user_id=self._actor_user_id
        )
        if version is None:
            raise NotFoundError("document version was not found")
        await self._document(version.document_id)
        return version

    async def get_ingestion_job(self, job_id: UUID) -> IngestionJob:
        job = await self._repository.get_ingestion_job(
            job_id, owner_user_id=self._actor_user_id
        )
        if job is None:
            raise NotFoundError("ingestion job was not found")
        await self._document(job.document_id)
        return job

    async def list_ingestion_jobs(self, document_id: UUID) -> list[IngestionJob]:
        await self._document(document_id)
        return await self._repository.list_ingestion_jobs(document_id=document_id)

    async def retry_ingestion_job(
        self,
        job_id: UUID,
    ) -> tuple[IngestionJob, OutboxEvent]:
        job = await self._repository.get_ingestion_job(
            job_id, owner_user_id=self._actor_user_id, for_update=True
        )
        if job is None:
            raise NotFoundError("ingestion job was not found")
        document = await self._repository.get_document(
            job.document_id, owner_user_id=self._actor_user_id, for_update=True
        )
        version = await self._repository.get_document_version(
            job.document_version_id,
            owner_user_id=self._actor_user_id,
            for_update=True,
        )
        if document is None or version is None:
            raise NotFoundError("ingestion job source was not found")
        if not document.is_enabled:
            raise BusinessRuleError("disabled documents cannot be retried")
        await self._active_knowledge_base(document.knowledge_base_id)
        if job.status != INGESTION_JOB_STATUS_FAILED:
            raise BusinessRuleError("only failed ingestion jobs can be retried")
        if version.status != DOCUMENT_VERSION_STATUS_FAILED:
            raise BusinessRuleError("failed ingestion job version is not retryable")
        if job.manual_retry_count >= self._ingestion_manual_retry_limit:
            raise BusinessRuleError("ingestion job manual retry limit was reached")
        versions = await self._repository.list_document_versions(document_id=document.id)
        if any(candidate.version > version.version for candidate in versions):
            raise BusinessRuleError("only the latest document version can be retried")

        event = await self._repository.get_outbox_event(
            ingestion_job_id=job.id,
            event_type=OUTBOX_EVENT_INGESTION_REQUESTED,
        )
        if event is None:
            event = await self._repository.add(
                OutboxEvent(
                    ingestion_job_id=job.id,
                    event_type=OUTBOX_EVENT_INGESTION_REQUESTED,
                    payload={"schema_version": 1, "ingestion_job_id": str(job.id)},
                    status=OUTBOX_STATUS_PENDING,
                    max_attempts=OUTBOX_DEFAULT_MAX_ATTEMPTS,
                    manual_retry_count=1,
                )
            )
        else:
            locked_event = await self._repository.get_outbox_event_by_id(
                event.id,
                for_update=True,
            )
            if locked_event is None:
                raise NotFoundError("ingestion dispatch event was not found")
            event = locked_event
            event.status = OUTBOX_STATUS_PENDING
            event.attempt_count = 0
            event.manual_retry_count += 1
            event.available_at = datetime.now(UTC)
            event.last_error = None
            event.published_at = None
            event.failed_at = None
            event.lease_owner = None
            event.lease_expires_at = None

        job.status = INGESTION_JOB_STATUS_AWAITING_PIPELINE
        job.progress = 0
        job.retry_count = 0
        job.manual_retry_count += 1
        job.error_code = None
        job.error_message = None
        job.error_detail = None
        job.started_at = None
        job.completed_at = None
        job.lease_owner = None
        job.lease_expires_at = None
        version.status = DOCUMENT_VERSION_STATUS_AWAITING_PIPELINE
        version.error_code = None
        version.error_message = None
        version.warnings = None
        version.completed_at = None
        self._audit_event(
            "rag.ingestion.retried",
            "ingestion_job",
            job.id,
            detail={
                "manual_retry_count": job.manual_retry_count,
                "document_version_id": str(version.id),
            },
        )
        await self._commit("unable to retry ingestion job")
        return job, event

    async def retry_ingestion_dispatch(self, job_id: UUID) -> OutboxEvent:
        job = await self.get_ingestion_job(job_id)
        if job.status != INGESTION_JOB_STATUS_AWAITING_PIPELINE:
            raise BusinessRuleError(
                "dispatch can only be retried for an awaiting ingestion job"
            )
        event = await self._repository.get_outbox_event(
            ingestion_job_id=job.id,
            event_type=OUTBOX_EVENT_INGESTION_REQUESTED,
        )
        if event is None:
            raise NotFoundError("ingestion dispatch event was not found")
        event = await self._repository.get_outbox_event_by_id(event.id, for_update=True)
        if event is None:
            raise NotFoundError("ingestion dispatch event was not found")
        if event.status != OUTBOX_STATUS_FAILED:
            raise BusinessRuleError("only failed ingestion dispatch events can be retried")
        event.status = OUTBOX_STATUS_PENDING
        event.attempt_count = 0
        event.manual_retry_count += 1
        event.available_at = datetime.now(UTC)
        event.last_error = None
        event.failed_at = None
        event.lease_owner = None
        event.lease_expires_at = None
        self._audit_event(
            "rag.ingestion.dispatch_retried",
            "ingestion_job",
            job.id,
            detail={"manual_retry_count": event.manual_retry_count},
        )
        await self._commit("unable to retry ingestion dispatch")
        return event

    async def disable_document(self, document_id: UUID) -> Document:
        document = await self._document(document_id)
        document.is_enabled = False
        document.status = DOCUMENT_STATUS_DISABLED
        document.disabled_at = datetime.now(UTC)
        await self._session.flush()
        self._audit_event("rag.document.disabled", "document", document.id)
        await self._commit("unable to disable document")
        return document

    async def delete_document(self, document_id: UUID) -> None:
        document = await self._document(document_id)
        document.is_enabled = False
        document.status = DOCUMENT_STATUS_DELETED
        document.deleted_at = datetime.now(UTC)
        await self._session.flush()
        self._audit_event("rag.document.deleted", "document", document.id)
        await self._commit("unable to delete document")
