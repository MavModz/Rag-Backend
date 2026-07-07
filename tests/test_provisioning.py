"""Unit tests for cross-platform provisioning validation and helpers."""
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.modules.admin.schemas import ProvisionRow
from app.modules.provisioning import service as provisioning_service
from app.modules.provisioning.schemas import ProvisionTenantRequest


def test_provision_tenant_request_requires_platform_id():
    with pytest.raises(ValidationError):
        ProvisionTenantRequest(
            name="Jane",
            company_name="Acme",
            admin_email="jane@acme.com",
            phone="+15551234567",
            role="teacher",
        )


def test_provision_tenant_request_accepts_lms_only():
    payload = ProvisionTenantRequest(
        name="Jane",
        company_name="Acme",
        admin_email="jane@acme.com",
        phone="+15551234567",
        role="teacher",
        lms_user_id=10,
        lms_institute_id=5,
    )
    assert payload.lms_user_id == 10


def test_provision_tenant_request_rejects_bad_object_id():
    with pytest.raises(ValidationError):
        ProvisionTenantRequest(
            name="Jane",
            company_name="Acme",
            admin_email="jane@acme.com",
            phone="+15551234567",
            role="manager",
            crm_user_id="not-an-object-id",
            crm_company_id="507f1f77bcf86cd799439011",
        )


def test_is_cross_platform_row_detects_phone():
    row = ProvisionRow(name="Acme", admin_email="a@b.com", phone="+1")
    assert provisioning_service.is_cross_platform_row(row) is True


def test_is_cross_platform_row_legacy():
    row = ProvisionRow(name="Acme", admin_email="a@b.com")
    assert provisioning_service.is_cross_platform_row(row) is False


def test_merge_value_fills_null():
    assert provisioning_service._merge_value(None, 5, field="lms_user_id") == 5


def test_merge_value_rejects_conflict():
    with pytest.raises(provisioning_service.ProvisioningError):
        provisioning_service._merge_value(5, 9, field="lms_user_id")


@pytest.mark.asyncio
async def test_upsert_passes_regenerated_password_to_create_user():
    row = ProvisionRow(
        name="Jane",
        company_name="Acme",
        admin_email="jane@acme.com",
        phone="+15551234567",
        role="teacher",
        lms_user_id=10,
        lms_institute_id=5,
    )
    session = AsyncMock()
    captured: dict = {}

    async def fake_create_user(session, **kwargs):
        captured.update(kwargs)
        return AsyncMock(id="user-id")

    with (
        patch.object(provisioning_service.identity_repo, "find_user_by_provisioning_identity", AsyncMock(return_value=None)),
        patch.object(provisioning_service, "_advisory_lock", AsyncMock()),
        patch.object(provisioning_service, "_validate_platform_id_uniqueness", AsyncMock()),
        patch.object(provisioning_service.identity_service, "_unique_slug", AsyncMock(return_value="acme")),
        patch.object(provisioning_service.identity_service, "create_tenant", AsyncMock(return_value=AsyncMock(id="tenant-id"))),
        patch.object(provisioning_service.identity_service, "create_user", fake_create_user),
        patch.object(provisioning_service.identity_service, "create_api_key", AsyncMock(return_value=(AsyncMock(prefix="sk_abc"), "sk_secret"))),
        patch.object(provisioning_service.kb_repo, "ensure_default_knowledge_bases", AsyncMock()),
    ):
        result = await provisioning_service.upsert_provisioned_user(
            session, row, require_platform_ids=False
        )

    assert result.status == "created"
    assert captured["password"] is not None
    assert captured["password"] == result.admin_password


@pytest.mark.asyncio
async def test_cross_platform_provision_omits_password_by_design():
    row = ProvisionRow(
        name="Jane",
        company_name="Acme",
        admin_email="jane@acme.com",
        phone="+15551234567",
        role="teacher",
        admin_password="should-be-ignored",
        lms_user_id=10,
        lms_institute_id=5,
    )
    session = AsyncMock()
    captured: dict = {}

    async def fake_create_user(session, **kwargs):
        captured.update(kwargs)
        return AsyncMock(id="user-id")

    with (
        patch.object(provisioning_service.identity_repo, "find_user_by_provisioning_identity", AsyncMock(return_value=None)),
        patch.object(provisioning_service, "_advisory_lock", AsyncMock()),
        patch.object(provisioning_service, "_validate_platform_id_uniqueness", AsyncMock()),
        patch.object(provisioning_service.identity_service, "_unique_slug", AsyncMock(return_value="acme")),
        patch.object(provisioning_service.identity_service, "create_tenant", AsyncMock(return_value=AsyncMock(id="tenant-id"))),
        patch.object(provisioning_service.identity_service, "create_user", fake_create_user),
        patch.object(provisioning_service.identity_service, "create_api_key", AsyncMock(return_value=(AsyncMock(prefix="sk_abc"), "sk_secret"))),
        patch.object(provisioning_service.kb_repo, "ensure_default_knowledge_bases", AsyncMock()),
    ):
        result = await provisioning_service.upsert_provisioned_user(
            session, row, require_platform_ids=True
        )

    assert result.status == "created"
    assert captured["password"] is None
    assert result.admin_password is None
