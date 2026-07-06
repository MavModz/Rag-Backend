"""Sync NRICH open-blogs API into platform-shared knowledge (all tenants).

Requires Ollama for embeddings. Stop the API server first on local on-disk Qdrant
if you hit lock errors.

Usage:
    python -m scripts.sync_open_blogs
    python -m scripts.sync_open_blogs --product lms --force
"""
from __future__ import annotations

import argparse
import asyncio

from app.modules.knowledge import kb_sync_service
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE


async def _run(product: str, kb_scope: str, force: bool) -> None:
    report = await kb_sync_service.sync_open_blogs(
        product=product, kb_scope=kb_scope, force=force
    )
    print(
        f"Sync complete: product={report.product} total={report.total} "
        f"synced={report.synced} skipped={report.skipped} failed={report.failed}"
    )
    for row in report.results:
        if row.status == "failed":
            print(f"  FAIL {row.title!r}: {row.error}")
        elif row.status == "synced":
            print(f"  OK   {row.title!r} ({row.chunks_indexed} chunks)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync NRICH open-blogs into platform KB.")
    parser.add_argument("--product", default="lms", choices=["lms", "crm"])
    parser.add_argument("--kb-scope", default=DEFAULT_KB_SCOPE)
    parser.add_argument("--force", action="store_true", help="Re-embed even if content hash unchanged.")
    args = parser.parse_args()
    asyncio.run(_run(args.product, args.kb_scope, args.force))


if __name__ == "__main__":
    main()
