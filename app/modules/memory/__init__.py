"""Memory Service: distilled learnings from past chats for richer RAG context.

Summaries are embedded into a tenant-scoped Qdrant collection and retrieved
alongside KB chunks on future /chat requests. See README.md.
"""
