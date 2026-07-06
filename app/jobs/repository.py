"""Job status persistence helpers."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import Job


async def create_job(
    session: AsyncSession, *, tenant_id: uuid.UUID, type: str, payload: dict
) -> Job:
    job = Job(tenant_id=tenant_id, type=type, status="pending", payload=payload)
    session.add(job)
    await session.flush()
    return job


async def mark(
    session: AsyncSession,
    job_id: uuid.UUID,
    status: str,
    *,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    job = await session.get(Job, job_id)
    if job is None:
        return
    job.status = status
    if result is not None:
        job.result = result
    if error is not None:
        job.error = error
