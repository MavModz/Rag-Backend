"""Request/response models for the Knowledge Service."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.modules.knowledge.constants import DEFAULT_KB_SCOPE


class IngestResponse(BaseModel):
    source: str
    chunks_indexed: int
    kb_scope: str


class KnowledgeBaseOut(BaseModel):
    id: str
    scope: str
    name: str
    description: str | None = None


class KnowledgeBaseList(BaseModel):
    bases: list[KnowledgeBaseOut]


class DocumentOut(BaseModel):
    id: str
    source: str
    filename: str
    mime: str | None = None
    chunk_count: int
    kb_scope: str


class DocumentList(BaseModel):
    scope: str
    documents: list[DocumentOut]


class DeleteDocumentResponse(BaseModel):
    status: str = "deleted"
    document_id: str


class PlatformIngestResponse(BaseModel):
    product: str
    external_id: str
    source: str
    chunks_indexed: int
    kb_scope: str
    content_hash: str


class PlatformDocumentOut(BaseModel):
    id: str
    product: str
    kb_scope: str
    source_type: str
    external_id: str
    title: str
    source: str
    chunk_count: int
    content_hash: str | None = None


class PlatformDocumentList(BaseModel):
    documents: list[PlatformDocumentOut]


class PlatformTextIngestRequest(BaseModel):
    product: str
    external_id: str
    title: str
    text: str
    kb_scope: str = DEFAULT_KB_SCOPE
    source_type: str | None = None
    source: str | None = None


class ArticleSyncResultOut(BaseModel):
    external_id: str
    title: str
    status: str
    chunks_indexed: int = 0
    error: str | None = None


class OpenBlogsSyncResponse(BaseModel):
    product: str
    kb_scope: str
    total: int
    synced: int
    skipped: int
    failed: int
    results: list[ArticleSyncResultOut]
