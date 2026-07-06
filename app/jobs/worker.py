"""Celery worker entrypoint + the one real M1 task: reindex_document.

Start a worker with:  celery -A app.jobs.worker.celery_app worker -Q ai_platform

The task is a thin sync shell that drives the async ingestion + job-status
updates via ``asyncio.run`` (each Celery task gets its own event loop). With no
broker configured, callers instead run the same work inline through the
in-process event bus.
"""
from __future__ import annotations

import asyncio
import uuid

from app.platform.events.tasks import celery_app
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)


async def _reindex(job_id: str, tenant_id: str, file_path: str) -> None:
    from app.jobs import repository as jobs_repo
    from app.modules.knowledge import service as ingestion_service
    from app.platform.db.postgres import get_sessionmaker

    sessionmaker = get_sessionmaker()
    jid = uuid.UUID(job_id)
    async with sessionmaker() as session:
        await jobs_repo.mark(session, jid, "running")
        await session.commit()
    try:
        result = await asyncio.to_thread(ingestion_service.ingest_file, file_path, tenant_id)
        async with sessionmaker() as session:
            await jobs_repo.mark(
                session, jid, "completed", result={"chunks_indexed": result.chunks_indexed}
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("reindex_document job %s failed: %s", job_id, exc)
        async with sessionmaker() as session:
            await jobs_repo.mark(session, jid, "failed", error=str(exc))
            await session.commit()


@celery_app.task(name="jobs.reindex_document")
def reindex_document(job_id: str, tenant_id: str, file_path: str) -> None:
    asyncio.run(_reindex(job_id, tenant_id, file_path))
