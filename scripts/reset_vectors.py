"""CLI to drop and recreate the Qdrant collection for the current embedding model.

Wipes ALL tenants' chunks. Use this when the embedding model's vector dimension
changes (e.g. 4096 -> 1024), since a Qdrant collection's vector size is immutable
and a re-ingest alone cannot fix the mismatch. After resetting, re-ingest your
documents with `scripts.ingest_cli`.

Local Qdrant is single-process: stop the FastAPI server before running this.

Usage:
    python -m scripts.reset_vectors --yes
"""
from __future__ import annotations

import argparse

from app.config import settings
from app.modules.knowledge.rag import vector_store


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drop and recreate the Qdrant collection (wipes ALL chunks)."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        required=True,
        help="Confirm the destructive wipe of all embedded chunks.",
    )
    parser.parse_args()

    try:
        dim = vector_store.reset_collection()
    finally:
        vector_store.close()
    print(
        f"Reset '{settings.qdrant_collection}' (dim={dim}, hybrid={settings.retrieval_hybrid}). "
        f"Re-ingest: python -m scripts.sync_open_blogs --force"
    )


if __name__ == "__main__":
    main()
