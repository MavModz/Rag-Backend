"""Ingest parent-company PDF/DOCX shared across all tenants.

Usage:
    python -m scripts.ingest_platform_cli --product lms --file guides/course.pdf
    python -m scripts.ingest_platform_cli --product crm --file guides/meta-leads.pdf
"""
from __future__ import annotations

import argparse

from app.modules.knowledge import service as ingestion_service
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest platform-shared parent docs.")
    parser.add_argument("--product", required=True, choices=["lms", "crm"])
    parser.add_argument("--file", required=True, help="Path to .pdf or .docx")
    parser.add_argument("--kb-scope", default=DEFAULT_KB_SCOPE)
    parser.add_argument("--external-id", default=None, help="Stable id (default: filename stem)")
    parser.add_argument("--title", default=None)
    args = parser.parse_args()

    result = ingestion_service.ingest_platform_file(
        args.file,
        product=args.product,
        kb_scope=args.kb_scope,
        external_id=args.external_id,
        title=args.title,
    )
    print(
        f"Platform ingest product={result.product} external_id={result.external_id!r}: "
        f"{result.chunks_indexed} chunks (hash={result.content_hash[:12]}...)."
    )


if __name__ == "__main__":
    main()
