"""Knowledge Service router: ingest and agent-scoped knowledge base management."""
from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.config import settings
from app.modules.knowledge import repository as kb_repo
from app.modules.knowledge import service as ingestion_service
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE
from app.modules.knowledge.rag import vector_store
from app.modules.knowledge.rag.loaders import UnsupportedFileType
from app.modules.knowledge.schemas import (
    DeleteDocumentResponse,
    DocumentList,
    DocumentOut,
    IngestResponse,
    KnowledgeBaseList,
    KnowledgeBaseOut,
)
from app.platform.auth.dependencies import require_permission
from app.platform.auth.rbac import Permission
from app.platform.db.postgres import get_sessionmaker
from app.platform.observability.logging import get_logger
from app.platform.ratelimit.limiter import limiter
from app.platform.security.sanitize import InvalidInput, sanitize_identifier
from app.platform.storage import get_object_store
from app.platform.tenancy.context import TenantContext

logger = get_logger(__name__)

router = APIRouter(tags=["knowledge"])

_ALLOWED_SUFFIXES = {".pdf", ".docx", ".doc"}


def _parse_kb_scope(raw: str | None) -> str:
    try:
        return kb_repo.normalize_kb_scope(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/knowledge/bases", response_model=KnowledgeBaseList)
async def list_bases(
    ctx: TenantContext = Depends(require_permission(Permission.KB_READ)),
) -> KnowledgeBaseList:
    tenant_id = ctx.tenant_uuid()
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Knowledge bases require a UUID tenant")
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = await kb_repo.list_knowledge_bases(session, tenant_id)
        await session.commit()
    return KnowledgeBaseList(
        bases=[
            KnowledgeBaseOut(
                id=str(row.id),
                scope=row.scope,
                name=row.name,
                description=row.description,
            )
            for row in rows
        ]
    )


@router.get("/knowledge/bases/{scope}/documents", response_model=DocumentList)
async def list_documents(
    scope: str,
    ctx: TenantContext = Depends(require_permission(Permission.KB_READ)),
) -> DocumentList:
    tenant_id = ctx.tenant_uuid()
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Knowledge bases require a UUID tenant")
    kb_scope = _parse_kb_scope(scope)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        docs = await kb_repo.list_documents_for_scope(session, tenant_id, kb_scope)
        await session.commit()
    return DocumentList(
        scope=kb_scope,
        documents=[
            DocumentOut(
                id=str(doc.id),
                source=doc.source,
                filename=doc.filename,
                mime=doc.mime,
                chunk_count=doc.chunk_count,
                kb_scope=kb_scope,
            )
            for doc in docs
        ],
    )


@router.delete(
    "/knowledge/bases/{scope}/documents/{document_id}",
    response_model=DeleteDocumentResponse,
)
async def delete_document(
    scope: str,
    document_id: str,
    ctx: TenantContext = Depends(require_permission(Permission.KB_WRITE)),
) -> DeleteDocumentResponse:
    tenant_id = ctx.tenant_uuid()
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Knowledge bases require a UUID tenant")
    kb_scope = _parse_kb_scope(scope)
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid document_id") from exc

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        doc = await kb_repo.get_document(session, tenant_id, doc_uuid)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        kb = await kb_repo.get_knowledge_base_by_scope(session, tenant_id, kb_scope)
        if kb is None or doc.knowledge_base_id != kb.id:
            raise HTTPException(status_code=404, detail="Document not in this knowledge base")
        vector_ids = await kb_repo.delete_document(session, tenant_id, doc_uuid)
        await session.commit()

    await asyncio.to_thread(vector_store.delete_points, vector_ids)
    return DeleteDocumentResponse(document_id=document_id)


@router.post("/ingest", response_model=IngestResponse)
@limiter.limit(settings.rate_limit_ingest)
async def ingest(
    request: Request,
    company_id: str | None = Form(None),
    kb_scope: str | None = Form(DEFAULT_KB_SCOPE),
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(require_permission(Permission.KB_WRITE)),
) -> IngestResponse:
    scope = _parse_kb_scope(kb_scope)
    try:
        company_id = sanitize_identifier(company_id or ctx.tenant_id, "company_id")
    except InvalidInput as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=422, detail="Only .pdf/.docx files are supported")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / filename
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    storage_uri: str | None = None
    try:
        store = get_object_store()
        storage_uri = store.put(f"{ctx.tenant_id}/{filename}", dest.read_bytes(), file.content_type)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Object storage staging failed for %s: %s", filename, exc)

    try:
        result = await asyncio.to_thread(
            ingestion_service.ingest_file, dest, company_id, scope
        )
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await _persist_metadata(ctx, result, filename, file.content_type, storage_uri, scope)
    return IngestResponse(
        source=result.source, chunks_indexed=result.chunks_indexed, kb_scope=scope
    )


async def _persist_metadata(
    ctx: TenantContext,
    result: ingestion_service.IngestionResult,
    filename: str,
    mime: str | None,
    storage_uri: str | None,
    kb_scope: str,
) -> None:
    """Mirror document + chunk metadata into Postgres for a real tenant (best-effort)."""
    tenant_id = ctx.tenant_uuid()
    if tenant_id is None or result.chunks_indexed == 0:
        return
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            kb = await kb_repo.get_or_create_knowledge_base(session, tenant_id, kb_scope)
            doc = await kb_repo.create_document(
                session,
                tenant_id=tenant_id,
                knowledge_base_id=kb.id,
                source=result.source,
                filename=filename,
                mime=mime,
                storage_uri=storage_uri,
                chunk_count=result.chunks_indexed,
            )
            await kb_repo.add_chunks(
                session,
                tenant_id=tenant_id,
                document_id=doc.id,
                vector_ids=result.vector_ids,
                previews=result.chunk_previews,
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist document metadata for %s: %s", filename, exc)
