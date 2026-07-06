"""CLI to ingest a document without going through the HTTP API.

Usage:
    python -m scripts.ingest_cli --file path/to/doc.pdf --company <company_id> [--kb-scope quiz]
"""
from __future__ import annotations

import argparse

from app.modules.knowledge import service as ingestion_service
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a PDF/DOCX into the KB.")
    parser.add_argument("--file", required=True, help="Path to a .pdf or .docx file")
    parser.add_argument("--company", required=True, help="Company id (tenant)")
    parser.add_argument(
        "--kb-scope",
        default=DEFAULT_KB_SCOPE,
        help="Agent knowledge base scope (support, quiz, meeting)",
    )
    args = parser.parse_args()

    result = ingestion_service.ingest_file(
        args.file, tenant_id=args.company, kb_scope=args.kb_scope
    )
    print(
        f"Ingested '{result.source}' into kb_scope={result.kb_scope}: "
        f"{result.chunks_indexed} chunks indexed."
    )


if __name__ == "__main__":
    main()
