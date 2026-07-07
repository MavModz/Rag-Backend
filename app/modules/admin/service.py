"""Admin service: bulk onboarding / provisioning.

Bulk-creates tenants (+ admin user + starter API key + optional data source) from
a JSON list or an uploaded CSV. Cross-platform rows upsert on email + phone +
role; legacy rows without those fields remain idempotent by admin email only.
Each row is committed independently so one bad row doesn't roll back the rest.
"""
from __future__ import annotations

import csv
import io
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.admin import schemas
from app.modules.datasources import schemas as ds_schemas
from app.modules.datasources import service as ds_service
from app.modules.identity import repository as identity_repo
from app.modules.identity import service as identity_service
from app.modules.provisioning import service as provisioning_service
from app.platform.auth import rbac

_CSV_FIELDS = [
    "name", "company_name", "slug", "plan", "admin_email", "admin_password",
    "phone", "role", "lms_user_id", "lms_institute_id", "crm_user_id", "crm_company_id",
    "ds_type", "ds_conn", "ds_db", "ds_collections", "ds_table",
]


def parse_csv(content: bytes) -> list[schemas.ProvisionRow]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[schemas.ProvisionRow] = []
    for raw in reader:
        clean = {k: (v.strip() if isinstance(v, str) else v) or None for k, v in raw.items() if k}
        payload = {k: clean.get(k) for k in _CSV_FIELDS if k in clean}
        for int_field in ("lms_user_id", "lms_institute_id"):
            if payload.get(int_field) is not None:
                payload[int_field] = int(payload[int_field])
        rows.append(schemas.ProvisionRow(**payload))
    return rows


def _build_ds_config(row: schemas.ProvisionRow) -> dict:
    if row.ds_type == "mongo":
        collections = [c.strip() for c in (row.ds_collections or "").split(",") if c.strip()]
        return {"uri": row.ds_conn, "db": row.ds_db or "", "collections": collections}
    return {"dsn": row.ds_conn, "table": row.ds_table or ""}


async def _provision_legacy(session: AsyncSession, row: schemas.ProvisionRow) -> schemas.ProvisionResult:
    if await identity_repo.get_user_by_email_any_tenant(session, str(row.admin_email)) is not None:
        return schemas.ProvisionResult(name=row.name, status="skipped", error="admin_email already exists")

    slug = await identity_service._unique_slug(
        session, identity_service.slugify(row.slug or row.name)
    )
    generated = row.admin_password is None
    password = row.admin_password or secrets.token_urlsafe(9)

    tenant = await identity_service.create_tenant(
        session, name=row.name, slug=slug, plan=row.plan or settings.default_signup_plan
    )
    await identity_service.create_user(
        session,
        tenant_id=tenant.id,
        email=str(row.admin_email),
        password=password,
        name=row.name,
        phone=None,
        role_names=["admin"],
    )
    record, full_key = await identity_service.create_api_key(
        session, tenant_id=tenant.id, name="default", scopes=list(rbac.DEFAULT_API_KEY_SCOPES)
    )

    data_source_id = None
    if row.ds_type and row.ds_conn:
        ds = await ds_service.create(
            session,
            tenant.id,
            ds_schemas.DataSourceCreate(
                type=row.ds_type,
                name="primary",
                config=_build_ds_config(row),
                field_mapping=row.ds_field_mapping or {},
                enabled=True,
            ),
        )
        data_source_id = str(ds.id)

    return schemas.ProvisionResult(
        name=row.name,
        status="created",
        tenant_id=str(tenant.id),
        admin_email=str(row.admin_email),
        admin_password=password if generated else None,
        api_key=full_key,
        api_key_prefix=record.prefix,
        data_source_id=data_source_id,
    )


async def provision_one(session: AsyncSession, row: schemas.ProvisionRow) -> schemas.ProvisionResult:
    if provisioning_service.is_cross_platform_row(row):
        return await provisioning_service.upsert_provisioned_user(
            session, row, require_platform_ids=False
        )
    return await _provision_legacy(session, row)


async def provision_bulk(
    session: AsyncSession, rows: list[schemas.ProvisionRow]
) -> schemas.BulkProvisionResponse:
    results: list[schemas.ProvisionResult] = []
    for row in rows:
        try:
            result = await provision_one(session, row)
            await session.commit()
        except provisioning_service.ProvisioningError as exc:
            await session.rollback()
            result = schemas.ProvisionResult(name=row.name, status="error", error=str(exc))
        except Exception as exc:  # noqa: BLE001 - one bad row must not fail the batch
            await session.rollback()
            result = schemas.ProvisionResult(name=row.name, status="error", error=str(exc))
        results.append(result)

    return schemas.BulkProvisionResponse(
        created=sum(r.status == "created" for r in results),
        updated=sum(r.status == "updated" for r in results),
        skipped=sum(r.status == "skipped" for r in results),
        errors=sum(r.status == "error" for r in results),
        results=results,
    )
