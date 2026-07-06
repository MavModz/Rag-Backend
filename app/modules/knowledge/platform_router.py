"""Platform (parent-company) knowledge routes — shared docs for all tenants."""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from app.modules.knowledge import platform_repository as platform_repo
from app.modules.knowledge import service as ingestion_service
from app.modules.knowledge import kb_sync_service
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE, SOURCE_TYPE_API
from app.modules.knowledge.rag.loaders import UnsupportedFileType
from app.modules.knowledge.schemas import (
    OpenBlogsSyncResponse,
    PlatformDocumentList,
    PlatformDocumentOut,
    PlatformIngestResponse,
    PlatformTextIngestRequest,
    ArticleSyncResultOut,
)
from app.platform.auth.dependencies import verify_provisioning_key
from app.platform.db.postgres import get_sessionmaker
from app.platform.observability.logging import get_logger
from app.platform.storage import get_object_store

logger = get_logger(__name__)

router = APIRouter(prefix="/platform", tags=["platform-knowledge"])

_ALLOWED_SUFFIXES = {".pdf", ".docx", ".doc"}


def _parse_product(raw: str) -> str:
    try:
        return ingestion_service._normalize_product(raw)  # noqa: SLF001
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/documents", response_model=PlatformDocumentList)
async def list_platform_documents(
    product: str | None = None,
    _: None = Depends(verify_provisioning_key),
) -> PlatformDocumentList:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = await platform_repo.list_platform_documents(session, product=product)
        await session.commit()
    return PlatformDocumentList(
        documents=[
            PlatformDocumentOut(
                id=str(row.id),
                product=row.product,
                kb_scope=row.kb_scope,
                source_type=row.source_type,
                external_id=row.external_id,
                title=row.title,
                source=row.source,
                chunk_count=row.chunk_count,
                content_hash=row.content_hash,
            )
            for row in rows
        ]
    )


@router.post("/ingest", response_model=PlatformIngestResponse)
async def ingest_platform_file(
    product: str = Form(...),
    kb_scope: str = Form(DEFAULT_KB_SCOPE),
    external_id: str | None = Form(None),
    title: str | None = Form(None),
    file: UploadFile = File(...),
    _: None = Depends(verify_provisioning_key),
) -> PlatformIngestResponse:
    """Ingest a parent-company PDF/DOCX shared by all tenants on ``/chat``."""
    product_slug = _parse_product(product)
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=422, detail="Only .pdf/.docx files are supported")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"platform_{product_slug}_{filename}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    storage_uri: str | None = None
    try:
        store = get_object_store()
        storage_uri = store.put(
            f"platform/{product_slug}/{filename}", dest.read_bytes(), file.content_type
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Object storage staging failed for platform %s: %s", filename, exc)

    try:
        result = await asyncio.to_thread(
            ingestion_service.ingest_platform_file,
            dest,
            product=product_slug,
            kb_scope=kb_scope.strip().lower(),
            external_id=external_id,
            title=title,
        )
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await _persist_platform_metadata(result, storage_uri)
    return PlatformIngestResponse(
        product=result.product,
        external_id=result.external_id,
        source=result.source,
        chunks_indexed=result.chunks_indexed,
        kb_scope=result.kb_scope,
        content_hash=result.content_hash,
    )


@router.post("/ingest/text", response_model=PlatformIngestResponse)
async def ingest_platform_text(
    payload: PlatformTextIngestRequest,
    _: None = Depends(verify_provisioning_key),
) -> PlatformIngestResponse:
    """Ingest parent-company text (API articles/FAQs — HTML stripped by caller or plain text)."""
    try:
        result = await asyncio.to_thread(
            ingestion_service.ingest_platform_text,
            product=payload.product,
            text=payload.text,
            title=payload.title,
            external_id=payload.external_id,
            kb_scope=payload.kb_scope,
            source_type=payload.source_type or SOURCE_TYPE_API,
            source=payload.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await _persist_platform_metadata(result, storage_uri=None)
    return PlatformIngestResponse(
        product=result.product,
        external_id=result.external_id,
        source=result.source,
        chunks_indexed=result.chunks_indexed,
        kb_scope=result.kb_scope,
        content_hash=result.content_hash,
    )


@router.post("/sync/open-blogs", response_model=OpenBlogsSyncResponse)
async def sync_open_blogs(
    product: str = Form("lms"),
    kb_scope: str = Form(DEFAULT_KB_SCOPE),
    force: bool = Form(False),
    _: None = Depends(verify_provisioning_key),
) -> OpenBlogsSyncResponse:
    """Pull articles from NRICH open-blogs API into platform-shared KB (all tenants)."""
    product_slug = _parse_product(product)
    report = await kb_sync_service.sync_open_blogs(
        product=product_slug, kb_scope=kb_scope.strip().lower(), force=force
    )
    return OpenBlogsSyncResponse(
        product=report.product,
        kb_scope=report.kb_scope,
        total=report.total,
        synced=report.synced,
        skipped=report.skipped,
        failed=report.failed,
        results=[
            ArticleSyncResultOut(
                external_id=r.external_id,
                title=r.title,
                status=r.status,
                chunks_indexed=r.chunks_indexed,
                error=r.error,
            )
            for r in report.results
        ],
    )


async def _persist_platform_metadata(
    result: ingestion_service.PlatformIngestionResult, storage_uri: str | None
) -> None:
    if result.chunks_indexed == 0:
        return
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await platform_repo.upsert_platform_document(
                session,
                product=result.product,
                kb_scope=result.kb_scope,
                source_type=result.source_type,
                external_id=result.external_id,
                title=result.title,
                source=result.source,
                content_hash=result.content_hash,
                chunk_count=result.chunks_indexed,
                storage_uri=storage_uri,
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist platform document metadata: %s", exc)
