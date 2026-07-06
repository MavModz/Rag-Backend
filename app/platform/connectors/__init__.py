"""Connector / data-source layer.

The AI platform owns AI workflows; business systems own their data. Connectors
let the platform READ business data from any connected external system (Mongo,
MySQL, other Postgres, ...) behind a provider-agnostic interface. The existing
MongoDB WhatsApp history is the first connector.
"""
