"""NRICH open-blogs sync helpers."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.knowledge import kb_sync_service
from app.modules.knowledge import service as ingestion_service
from app.modules.knowledge.html_text import format_image_reference, html_to_plain_text
from app.modules.knowledge.kb_sync_service import article_to_plain_text


SAMPLE_ARTICLE = {
    "id": "3d6d7e34-a21b-412e-8c0c-32f25dbbbbff",
    "title": "Diagnosing Slow Load Times",
    "slug": "diagnosing-slow-load-times",
    "status": "published",
    "visibility": "public",
    "description": "Checklist before raising a ticket.",
    "body": "<h2>Slow loads</h2><p>Clear your browser cache.</p>",
    "category": {"name": "Troubleshooting"},
    "tags": ["performance"],
}


def test_html_to_plain_text_strips_tags():
    html = "<h2>Title</h2><p>Hello <strong>world</strong>.</p>"
    text = html_to_plain_text(html)
    assert "Title" in text
    assert "Hello world" in text
    assert "<" not in text


def test_html_to_plain_text_preserves_inline_images():
  body = (
      '<p>Head over to the <strong>Assist</strong> section</p>'
      '<img src="https://help.nrichlearning.com/wp-content/uploads/2025/10/image-1.gif" alt="">'
      '<h3>Step 1: Complete Your Profile</h3>'
      '<img src="https://help.nrichlearning.com/wp-content/uploads/2025/10/image-34.png" alt="">'
  )
  text = html_to_plain_text(body)
  assert "Assist" in text
  assert "Step 1: Complete Your Profile" in text
  assert "[Image (animated GIF): https://help.nrichlearning.com/wp-content/uploads/2025/10/image-1.gif]" in text
  assert "[Image (PNG): https://help.nrichlearning.com/wp-content/uploads/2025/10/image-34.png]" in text


def test_format_image_reference_with_alt():
    line = format_image_reference(
        "https://cdn.example.com/step.png",
        "Billing tab highlighted",
    )
    assert line == "[Image (PNG): Billing tab highlighted — https://cdn.example.com/step.png]"


def test_article_to_plain_text_includes_featured_image():
    article = {
        "title": "Guide",
        "description": "A walkthrough.",
        "body": "<p>Click Start.</p>",
        "featuredImage": {"url": "https://cdn.example.com/hero.jpg", "alt": "Dashboard"},
        "category": None,
        "tags": [],
    }
    text = article_to_plain_text(article)
    assert "[Image (JPEG): Dashboard — https://cdn.example.com/hero.jpg]" in text


def test_article_to_plain_text_includes_metadata():
    article = {
        "title": "Slow loads",
        "description": "A checklist for speed issues.",
        "body": "<p>Restart your router.</p>",
        "category": {"name": "Troubleshooting"},
        "tags": ["performance"],
    }
    text = article_to_plain_text(article)
    assert "Slow loads" in text
    assert "checklist" in text
    assert "Troubleshooting" in text
    assert "performance" in text
    assert "Restart your router" in text


@pytest.mark.asyncio
async def test_sync_open_blogs_indexes_publishable(monkeypatch):
    async def _fake_fetch(**_kwargs):
        return [SAMPLE_ARTICLE]

    fake_result = ingestion_service.PlatformIngestionResult(
        product="lms",
        external_id=SAMPLE_ARTICLE["id"],
        source=SAMPLE_ARTICLE["slug"],
        title=SAMPLE_ARTICLE["title"],
        source_type="api",
        chunks_indexed=2,
        content_hash="abc",
    )
    monkeypatch.setattr(kb_sync_service, "fetch_open_blogs", _fake_fetch)
    monkeypatch.setattr(
        ingestion_service, "ingest_platform_text", lambda **kwargs: fake_result
    )

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(kb_sync_service, "get_sessionmaker", lambda: lambda: mock_cm)
    monkeypatch.setattr(
        kb_sync_service.platform_repo, "get_by_external_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        kb_sync_service.platform_repo, "upsert_platform_document", AsyncMock()
    )

    report = await kb_sync_service.sync_open_blogs(product="lms")
    assert report.total == 1
    assert report.synced == 1
    assert report.failed == 0
