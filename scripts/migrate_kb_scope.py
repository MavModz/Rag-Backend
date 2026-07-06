"""One-shot: backfill ``kb_scope=support`` on existing Qdrant KB points.

Before agent-scoped knowledge bases, points had no kb_scope payload field.
Search treats missing kb_scope as support during the transition; run this once
to set the field explicitly on all legacy points.

Local Qdrant is single-process: stop the FastAPI server before running.

Usage:
    python -m scripts.migrate_kb_scope --yes
"""
from __future__ import annotations

import argparse

from qdrant_client.http import models as qmodels

from app.config import settings
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE
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
                must=[
                    qmodels.IsEmptyCondition(is_empty=qmodels.PayloadField(key="kb_scope")),
                ],
            ),
            with_payload=True,
            limit=256,
            offset=offset,
        )
        if not points:
            break
        for point in points:
            client.set_payload(
                collection_name=collection,
                payload={"kb_scope": DEFAULT_KB_SCOPE},
                points=[point.id],
            )
            migrated += 1
        if offset is None:
            break
    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill kb_scope=support on existing Qdrant KB points."
    )
    parser.add_argument("--yes", action="store_true", required=True, help="Confirm the backfill.")
    parser.parse_args()
    try:
        count = migrate()
    finally:
        vector_store.close()
    print(f"Migrated {count} point(s): kb_scope set to {DEFAULT_KB_SCOPE!r}.")


if __name__ == "__main__":
    main()
