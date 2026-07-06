"""Data Sources: tenant self-service management of external DB connections.

Each tenant registers their own database (Mongo/SQL), picks collections/tables,
and maps their schema to the platform's fields — so the agents read that tenant's
own conversation history. Connection strings are encrypted at rest; this module
also tests connections and discovers collections/tables/fields for the UI.
"""
