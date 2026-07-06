"""Platform shared kernel.

Cross-cutting infrastructure used by every business module: database engines,
auth, tenancy, the model gateway, external-system connectors, object storage,
caching, the event/worker bus, observability and security. Contains NO business
logic — modules under ``app.modules`` own that.
"""
