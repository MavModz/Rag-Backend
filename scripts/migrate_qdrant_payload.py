"""One-shot: backfill ``tenant_id`` onto existing Qdrant points from ``company_id``.

Before the rename, points were keyed by a ``company_id`` payload. New writes use
``tenant_id``; search dual-reads both during the transition. Run this once to copy
``company_id`` -> ``tenant_id`` on every legacy point (no re-embedding), after which
the dual-read filter can be narrowed to ``tenant_id`` only.

Local Qdrant is single-process: stop the FastAPI server before running.

Usage:
    python -m scripts.migrate_qdrant_payload --yes
"""
from __future__ import annotations

import argparse

from qdrant_client.http import models as qmodels

from app.config import settings
from app.modules.knowledge.rag import vector_store


def migrate() -> int:
    client = vector_store._get_client()
    collection = settings.qdrant_collection
    if not client.collection_exists(collection):
        print(f"Collection '{collection}' does not exist; nothing to migrate.")
        return 0

    migrated = 0
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=qmodels.Filter(
                must=[qmodels.IsEmptyCondition(is_empty=qmodels.PayloadField(key="tenant_id"))],
            ),
            with_payload=True,
            limit=256,
            offset=offset,
        )
        if not points:
            break
        for point in points:
            company_id = (point.payload or {}).get("company_id")
            if not company_id:
                continue
            client.set_payload(
                collection_name=collection,
                payload={"tenant_id": company_id},
                points=[point.id],
            )
            migrated += 1
        if offset is None:
            break
    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill tenant_id from company_id on existing Qdrant points."
    )
    parser.add_argument("--yes", action="store_true", required=True, help="Confirm the backfill.")
    parser.parse_args()
    try:
        count = migrate()
    finally:
        vector_store.close()
    print(f"Migrated {count} point(s): tenant_id set from company_id.")


if __name__ == "__main__":
    main()
