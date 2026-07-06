"""Background jobs: the ``Job`` table and the (optional) Celery worker entrypoint.

Long-running work (ingestion, transcription, workflows) is tracked as ``Job``
rows regardless of whether a real broker is configured. With no broker, the
in-process event bus runs the work inline; with one, the Celery worker picks it
up. See ``app.platform.events``.
"""
