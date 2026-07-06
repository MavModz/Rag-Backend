"""Event/worker seam.

An ``EventBus`` abstraction decouples 'something happened' from 'how it runs'.
M1 ships an ``InProcessBus`` (runs handlers inline / as asyncio tasks) so no
broker is required; when ``celery_broker_url`` is set, the same events can be
dispatched to the Celery worker instead. Long-running work is tracked as ``jobs``
rows regardless of backend.
"""
