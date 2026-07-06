"""Celery application (optional).

Constructed unconditionally so tasks can be declared, but only usable when
``celery_broker_url`` is configured and a worker is running. With no broker, the
platform uses the in-process bus and runs work inline.
"""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "ai_platform",
    broker=settings.celery_broker_url or None,
    backend=settings.celery_result_backend or None,
)
celery_app.conf.task_default_queue = "ai_platform"
# Discover tasks defined under app.jobs.
celery_app.autodiscover_tasks(["app.jobs"])
