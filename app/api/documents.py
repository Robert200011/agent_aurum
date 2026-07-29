"""Administrator knowledge-document management endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Query, Response, UploadFile, status

from app.api.dependencies import (
    AdminContextDependency,
    ObjectStorageDependency,
    RagAdminServiceDependency,
    SettingsDependency,
)
from app.api.schemas.rag import (
    DocumentDownloadUrlResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
    DocumentVersionListResponse,
    DocumentVersionResponse,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionRetryResponse,
    OutboxEventResponse,
)
from app.errors import BusinessRuleError
from app.rag.upload_validation import validate_document_upload

router = APIRouter(prefix="/admin", tags=["admin-documents"])


def _metadata(value: str | None) -> dict[str, str]:
    if value is None:
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise BusinessRuleError("document metadata must be a JSON object") from exc
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in decoded.items()
    ):
        raise BusinessRuleError("document metadata must contain string keys and values")
    return decoded


async def _read_upload(file: UploadFile, max_size: int) -> bytes:
    content = await file.read(max_size + 1)
    await file.close()
    return content


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_document(
    knowledge_base_id: UUID,
    service: RagAdminServiceDependency,
    storage: ObjectStorageDependency,
    settings: SettingsDependency,
    _admin: AdminContextDependency,
    file: UploadFile = File(...),
    metadata: str | None = Form(default=None),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
) -> DocumentUploadResponse:
    upload = validate_document_upload(
        filename=file.filename,
        content=await _read_upload(file, settings.document_max_size_bytes),
        metadata=_metadata(metadata),
        settings=settings,
    )
    document, version, job = await service.create_document_upload(
        knowledge_base_id=knowledge_base_id,
        upload=upload,
        idempotency_key=idempotency_key,
        storage=storage,
    )
    return DocumentUploadResponse(
        document=DocumentResponse.model_validate(document),
        version=DocumentVersionResponse.model_validate(version),
        ingestion_job=IngestionJobResponse.model_validate(job),
    )


@router.post(
    "/documents/{document_id}/versions",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_document_version(
    document_id: UUID,
    service: RagAdminServiceDependency,
    storage: ObjectStorageDependency,
    settings: SettingsDependency,
    _admin: AdminContextDependency,
    file: UploadFile = File(...),
    metadata: str | None = Form(default=None),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
) -> DocumentUploadResponse:
    upload = validate_document_upload(
        filename=file.filename,
        content=await _read_upload(file, settings.document_max_size_bytes),
        metadata=_metadata(metadata),
        settings=settings,
    )
    document, version, job = await service.create_document_version_upload(
        document_id=document_id,
        upload=upload,
        idempotency_key=idempotency_key,
        storage=storage,
    )
    return DocumentUploadResponse(
        document=DocumentResponse.model_validate(document),
        version=DocumentVersionResponse.model_validate(version),
        ingestion_job=IngestionJobResponse.model_validate(job),
    )


@router.get("/knowledge-bases/{knowledge_base_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    knowledge_base_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> DocumentListResponse:
    result = await service.list_documents(
        knowledge_base_id=knowledge_base_id, page=page, page_size=page_size
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> DocumentResponse:
    return DocumentResponse.model_validate(await service.get_document(document_id))


@router.get("/documents/{document_id}/versions", response_model=DocumentVersionListResponse)
async def list_document_versions(
    document_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> DocumentVersionListResponse:
    versions = await service.list_document_versions(document_id)
    return DocumentVersionListResponse(
        items=[DocumentVersionResponse.model_validate(item) for item in versions]
    )


@router.get("/document-versions/{document_version_id}", response_model=DocumentVersionResponse)
async def get_document_version(
    document_version_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> DocumentVersionResponse:
    return DocumentVersionResponse.model_validate(
        await service.get_document_version(document_version_id)
    )


@router.get(
    "/document-versions/{document_version_id}/download-url",
    response_model=DocumentDownloadUrlResponse,
)
async def create_document_version_download_url(
    document_version_id: UUID,
    service: RagAdminServiceDependency,
    storage: ObjectStorageDependency,
    settings: SettingsDependency,
    _admin: AdminContextDependency,
) -> DocumentDownloadUrlResponse:
    version = await service.get_document_version(document_version_id)
    await storage.head(version.source_object_key)
    expires_in = timedelta(seconds=settings.object_storage_download_url_ttl_seconds)
    return DocumentDownloadUrlResponse(
        url=await storage.create_presigned_download_url(
            version.source_object_key,
            expires_in=expires_in,
        ),
        expires_at=datetime.now(UTC) + expires_in,
    )


@router.get("/ingestion-jobs/{job_id}", response_model=IngestionJobResponse)
async def get_ingestion_job(
    job_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> IngestionJobResponse:
    return IngestionJobResponse.model_validate(await service.get_ingestion_job(job_id))


@router.get(
    "/documents/{document_id}/ingestion-jobs",
    response_model=IngestionJobListResponse,
)
async def list_ingestion_jobs(
    document_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> IngestionJobListResponse:
    jobs = await service.list_ingestion_jobs(document_id)
    return IngestionJobListResponse(
        items=[IngestionJobResponse.model_validate(job) for job in jobs]
    )


@router.post(
    "/ingestion-jobs/{job_id}/retry",
    response_model=IngestionRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_ingestion_job(
    job_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> IngestionRetryResponse:
    job, event = await service.retry_ingestion_job(job_id)
    return IngestionRetryResponse(
        ingestion_job=IngestionJobResponse.model_validate(job),
        dispatch_event=OutboxEventResponse.model_validate(event),
    )


@router.post(
    "/ingestion-jobs/{job_id}/retry-dispatch",
    response_model=OutboxEventResponse,
)
async def retry_ingestion_dispatch(
    job_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> OutboxEventResponse:
    return OutboxEventResponse.model_validate(await service.retry_ingestion_dispatch(job_id))


@router.post("/documents/{document_id}/disable", response_model=DocumentResponse)
async def disable_document(
    document_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> DocumentResponse:
    return DocumentResponse.model_validate(await service.disable_document(document_id))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> Response:
    await service.delete_document(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
