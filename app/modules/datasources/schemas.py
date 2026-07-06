"""Data-source request/response models.

`config` shape by type:
  mongo: {"uri": "...", "db": "...", "collections": ["c1","c2"]}
  sql:   {"dsn": "postgresql+asyncpg://...", "table": "messages"}  (or "query": "...")
The connection secret (`uri`/`dsn`) is encrypted at rest and redacted on read.
`field_mapping` adapts the connector to the client's schema (see the connector docs).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

SourceType = str  # "mongo" | "sql" | "mysql" | "postgres" | "postgresql"


class DataSourceCreate(BaseModel):
    type: SourceType
    name: str = Field(..., max_length=128)
    config: dict
    field_mapping: dict = Field(default_factory=dict)
    enabled: bool = True


class DataSourceUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    field_mapping: dict | None = None
    enabled: bool | None = None


class DataSourceOut(BaseModel):
    id: str
    type: str
    name: str
    config: dict          # connection secret redacted
    field_mapping: dict
    enabled: bool
    created_at: datetime


class TestRequest(BaseModel):
    type: SourceType
    config: dict
    field_mapping: dict = Field(default_factory=dict)


class TestResult(BaseModel):
    ok: bool
    error: str | None = None


class DiscoverRequest(BaseModel):
    type: SourceType
    config: dict                 # {uri/dsn, db?}
    target: str | None = None    # a collection/table to sample its fields


class DiscoverResult(BaseModel):
    databases: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
