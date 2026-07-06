"""Sync parent-company content from external KB APIs into platform docs."""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.modules.knowledge import platform_repository as platform_repo
from app.modules.knowledge import service as ingestion_service
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE, SOURCE_TYPE_API
from app.modules.knowledge.html_text import format_image_reference, html_to_plain_text
from app.modules.knowledge.nrich_kb_client import NrichKbError, fetch_open_blog_by_slug, fetch_open_blogs
from app.platform.db.postgres import get_sessionmaker
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ArticleSyncResult:
    external_id: str
    title: str
    status: str  # synced | skipped | failed
    chunks_indexed: int = 0
    error: str | None = None


@dataclass
class OpenBlogsSyncReport:
    product: str
    kb_scope: str
    total: int = 0
    synced: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[ArticleSyncResult] = field(default_factory=list)


def _image_record_line(record: dict | None, *, label: str) -> str:
    if not isinstance(record, dict):
        return ""
    url = (
        str(record.get("url") or record.get("src") or record.get("path") or "")
    ).strip()
    if not url:
        return ""
    alt = str(record.get("alt") or record.get("caption") or record.get("title") or label).strip()
    return format_image_reference(url, alt)


def article_to_plain_text(article: dict) -> str:
    """Build searchable plain text from a KB article record."""
    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()
    body = html_to_plain_text(article.get("body"))
    category = article.get("category") or {}
    category_name = (category.get("name") or "").strip() if isinstance(category, dict) else ""
    tags = article.get("tags") or []
    tag_line = ", ".join(str(t) for t in tags if t)
    featured = _image_record_line(article.get("featuredImage"), label="Featured image")
    og = _image_record_line(article.get("ogImage"), label="Cover image")

    parts = [f"# {title}" if title else ""]
    if description:
        parts.append(description)
    if featured:
        parts.append(featured)
    if og and og != featured:
        parts.append(og)
    if category_name:
        parts.append(f"Category: {category_name}")
    if tag_line:
        parts.append(f"Tags: {tag_line}")
    if body:
        parts.append(body)
    return "\n\n".join(p for p in parts if p).strip()


def _is_publishable(article: dict) -> bool:
    return article.get("status") == "published" and article.get("visibility") == "public"


async def sync_open_blogs(
    *,
    product: str = "lms",
    kb_scope: str = DEFAULT_KB_SCOPE,
    force: bool = False,
) -> OpenBlogsSyncReport:
    """Pull NRICH open-blogs and index into platform-shared Qdrant + Postgres."""
    report = OpenBlogsSyncReport(product=product, kb_scope=kb_scope)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            articles = await fetch_open_blogs(client=client)
    except NrichKbError as exc:
        logger.warning("open-blogs sync failed to list: %s", exc)
        report.failed = 1
        report.results.append(
            ArticleSyncResult(external_id="", title="", status="failed", error=str(exc))
        )
        return report

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        for article in articles:
            if not _is_publishable(article):
                continue
            report.total += 1
            external_id = str(article.get("id") or "").strip()
            slug = str(article.get("slug") or external_id).strip()
            title = str(article.get("title") or slug).strip()
            if not external_id:
                report.failed += 1
                report.results.append(
                    ArticleSyncResult(external_id="", title=title, status="failed", error="missing id")
                )
                continue

            if not (article.get("body") or "").strip():
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        article = await fetch_open_blog_by_slug(slug, client=client)
                except NrichKbError as exc:
                    report.failed += 1
                    report.results.append(
                        ArticleSyncResult(
                            external_id=external_id, title=title, status="failed", error=str(exc)
                        )
                    )
                    continue

            plain = article_to_plain_text(article)
            if not plain:
                report.skipped += 1
                report.results.append(
                    ArticleSyncResult(external_id=external_id, title=title, status="skipped")
                )
                continue

            digest = ingestion_service.content_hash(plain)
            if not force:
                existing = await platform_repo.get_by_external_id(session, product, external_id)
                if existing is not None and existing.content_hash == digest:
                    report.skipped += 1
                    report.results.append(
                        ArticleSyncResult(external_id=external_id, title=title, status="skipped")
                    )
                    continue

            try:
                result = ingestion_service.ingest_platform_text(
                    product=product,
                    text=plain,
                    title=title,
                    external_id=external_id,
                    kb_scope=kb_scope,
                    source_type=SOURCE_TYPE_API,
                    source=slug,
                )
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
                )
                await session.commit()
                if result.chunks_indexed > 0:
                    report.synced += 1
                    report.results.append(
                        ArticleSyncResult(
                            external_id=external_id,
                            title=title,
                            status="synced",
                            chunks_indexed=result.chunks_indexed,
                        )
                    )
                else:
                    report.skipped += 1
                    report.results.append(
                        ArticleSyncResult(external_id=external_id, title=title, status="skipped")
                    )
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                report.failed += 1
                report.results.append(
                    ArticleSyncResult(
                        external_id=external_id, title=title, status="failed", error=str(exc)
                    )
                )
                logger.warning("Failed to sync article %s: %s", external_id, exc)

    logger.info(
        "open-blogs sync product=%s total=%d synced=%d skipped=%d failed=%d",
        product, report.total, report.synced, report.skipped, report.failed,
    )
    return report
