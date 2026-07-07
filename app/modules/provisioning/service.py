"""Cross-product provisioning: create or update users from LMS/CRM.

Shared by ``POST /provisioning/tenants`` and admin bulk onboarding.
"""
from __future__ import annotations

import hashlib
import re
import secrets

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.admin import schemas as admin_schemas
from app.modules.datasources import schemas as ds_schemas
from app.modules.datasources import service as ds_service
from app.modules.identity import repository as identity_repo
from app.modules.identity import service as identity_service
from app.modules.knowledge import repository as kb_repo
from app.platform.auth import rbac

_OBJECT_ID_RE = re.compile(r"^[a-f0-9]{24}$")


class ProvisioningError(Exception):
    def __init__(self, message: str, *, code: str = "PROVISIONING_ERROR") -> None:
        super().__init__(message)
        self.code = code


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    return re.sub(r"\s+", "", phone.strip())


def normalize_role(role: str) -> str:
    return role.strip()


def validate_object_id(value: str, field: str) -> str:
    cleaned = value.strip().lower()
    if not _OBJECT_ID_RE.match(cleaned):
        raise ProvisioningError(f"Invalid {field}: must be a 24-char hex ObjectId", code="VALIDATION_ERROR")
    return cleaned


def _has_platform_ids(row: admin_schemas.ProvisionRow) -> bool:
    return any(
        value is not None
        for value in (
            row.lms_user_id,
            row.lms_institute_id,
            row.crm_user_id,
            row.crm_company_id,
        )
    )


def is_cross_platform_row(row: admin_schemas.ProvisionRow) -> bool:
    return _has_platform_ids(row) or row.phone is not None or row.role is not None


def _company_name(row: admin_schemas.ProvisionRow) -> str:
    return (row.company_name or row.name).strip()


def _user_name(row: admin_schemas.ProvisionRow) -> str:
    return row.name.strip()


async def _advisory_lock(session: AsyncSession, email: str, phone: str, role: str) -> None:
    digest = hashlib.md5(f"{email}:{phone}:{role}".encode(), usedforsecurity=False).hexdigest()
    key = int(digest[:15], 16)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _merge_value(existing, new, *, field: str):
    if new is None:
        return existing
    if existing is None:
        return new
    if existing != new:
        raise ProvisioningError(
            f"{field} already bound to a different value",
            code="PROVISIONING_IDENTITY_CONFLICT",
        )
    return existing


async def _validate_platform_id_uniqueness(
    session: AsyncSession,
    row: admin_schemas.ProvisionRow,
    *,
    exclude_user_id=None,
    exclude_tenant_id=None,
) -> None:
    if row.lms_user_id is not None:
        other = await identity_repo.get_user_by_lms_user_id(session, row.lms_user_id)
        if other is not None and other.id != exclude_user_id:
            raise ProvisioningError(
                "lms_user_id already bound to another user",
                code="PROVISIONING_IDENTITY_CONFLICT",
            )
    if row.crm_user_id is not None:
        other = await identity_repo.get_user_by_crm_user_id(session, row.crm_user_id)
        if other is not None and other.id != exclude_user_id:
            raise ProvisioningError(
                "crm_user_id already bound to another user",
                code="PROVISIONING_IDENTITY_CONFLICT",
            )
    if row.lms_institute_id is not None:
        other = await identity_repo.get_tenant_by_lms_institute_id(session, row.lms_institute_id)
        if other is not None and other.id != exclude_tenant_id:
            raise ProvisioningError(
                "lms_institute_id already bound to another tenant",
                code="PROVISIONING_ORG_ID_CONFLICT",
            )
    if row.crm_company_id is not None:
        other = await identity_repo.get_tenant_by_crm_company_id(session, row.crm_company_id)
        if other is not None and other.id != exclude_tenant_id:
            raise ProvisioningError(
                "crm_company_id already bound to another tenant",
                code="PROVISIONING_ORG_ID_CONFLICT",
            )


async def _attach_data_source(
    session: AsyncSession, tenant_id, row: admin_schemas.ProvisionRow
) -> str | None:
    if not (row.ds_type and row.ds_conn):
        return None
    from app.modules.admin import service as admin_service

    ds = await ds_service.create(
        session,
        tenant_id,
        ds_schemas.DataSourceCreate(
            type=row.ds_type,
            name="primary",
            config=admin_service._build_ds_config(row),
            field_mapping=row.ds_field_mapping or {},
            enabled=True,
        ),
    )
    return str(ds.id)


def _resolve_provision_password(
    row: admin_schemas.ProvisionRow, *, require_platform_ids: bool
) -> tuple[str | None, str | None]:
    """Return ``(password, generated_password_for_response)``.

    Cross-platform users (``/provisioning/tenants``) never log into the AI
    platform — LMS/CRM backends call the API with the tenant API key and end
    users authenticate via product JWT. ``password_hash`` stays NULL by design.

    Legacy admin bulk rows (``require_platform_ids=False``) still auto-generate
    a password when ``admin_password`` is omitted so superadmin-created accounts
    can use ``/auth/login`` if needed.
    """
    if require_platform_ids:
        return None, None
    if row.admin_password is not None:
        return row.admin_password, None
    generated = secrets.token_urlsafe(9)
    return generated, generated


async def upsert_provisioned_user(
    session: AsyncSession,
    row: admin_schemas.ProvisionRow,
    *,
    require_platform_ids: bool = False,
) -> admin_schemas.ProvisionResult:
    """Create or update a provisioned user keyed by email + phone + role."""
    if require_platform_ids and not _has_platform_ids(row):
        raise ProvisioningError(
            "At least one platform identifier is required",
            code="PROVISIONING_NO_PLATFORM_IDS",
        )
    if row.phone is None or row.role is None:
        raise ProvisioningError("phone and role are required", code="VALIDATION_ERROR")

    email = normalize_email(str(row.admin_email))
    phone = normalize_phone(row.phone)
    role = normalize_role(row.role)
    if row.crm_user_id is not None:
        row.crm_user_id = validate_object_id(row.crm_user_id, "crm_user_id")
    if row.crm_company_id is not None:
        row.crm_company_id = validate_object_id(row.crm_company_id, "crm_company_id")

    await _advisory_lock(session, email, phone, role)

    user = await identity_repo.find_user_by_provisioning_identity(session, email, phone, role)
    if user is not None:
        tenant = await identity_repo.get_tenant(session, user.tenant_id)
        if tenant is None:
            raise ProvisioningError("Tenant not found for existing user", code="PROVISIONING_INTERNAL")

        await _validate_platform_id_uniqueness(
            session, row, exclude_user_id=user.id, exclude_tenant_id=tenant.id
        )

        if user.name is None and row.name:
            user.name = _user_name(row)
        user.lms_user_id = _merge_value(user.lms_user_id, row.lms_user_id, field="lms_user_id")
        user.crm_user_id = _merge_value(user.crm_user_id, row.crm_user_id, field="crm_user_id")
        tenant.lms_institute_id = _merge_value(
            tenant.lms_institute_id, row.lms_institute_id, field="lms_institute_id"
        )
        tenant.crm_company_id = _merge_value(
            tenant.crm_company_id, row.crm_company_id, field="crm_company_id"
        )
        if row.company_name and tenant.name != _company_name(row):
            # Preserve the original tenant name; company_name is informational on update.
            pass

        api_key = await identity_repo.get_default_api_key(session, tenant.id)
        data_source_id = await _attach_data_source(session, tenant.id, row)
        return admin_schemas.ProvisionResult(
            name=row.name,
            status="updated",
            tenant_id=str(tenant.id),
            admin_email=email,
            api_key=None,
            api_key_prefix=api_key.prefix if api_key else None,
            data_source_id=data_source_id,
        )

    await _validate_platform_id_uniqueness(session, row)

    slug = await identity_service._unique_slug(
        session, identity_service.slugify(row.slug or _company_name(row))
    )
    password, generated_password = _resolve_provision_password(
        row, require_platform_ids=require_platform_ids
    )

    tenant = await identity_service.create_tenant(
        session,
        name=_company_name(row),
        slug=slug,
        plan=row.plan or settings.default_signup_plan,
        lms_institute_id=row.lms_institute_id,
        crm_company_id=row.crm_company_id,
    )
    user = await identity_service.create_user(
        session,
        tenant_id=tenant.id,
        email=email,
        password=password,
        name=_user_name(row),
        phone=phone,
        role_names=["admin"],
        external_role_label=role,
        lms_user_id=row.lms_user_id,
        crm_user_id=row.crm_user_id,
    )
    record, full_key = await identity_service.create_api_key(
        session, tenant_id=tenant.id, name="default", scopes=list(rbac.DEFAULT_API_KEY_SCOPES)
    )
    await kb_repo.ensure_default_knowledge_bases(session, tenant.id)
    data_source_id = await _attach_data_source(session, tenant.id, row)

    return admin_schemas.ProvisionResult(
        name=row.name,
        status="created",
        tenant_id=str(tenant.id),
        admin_email=email,
        admin_password=generated_password,
        api_key=full_key,
        api_key_prefix=record.prefix,
        data_source_id=data_source_id,
    )
