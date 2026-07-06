"""Admin data-source routes for superadmin console."""
from app.modules.datasources import service as ds_service
from app.modules.datasources.constants import (
    WHATSAPP_MONGO_COLLECTIONS,
    WHATSAPP_MONGO_FIELD_MAPPING,
)


def test_whatsapp_preset_shape():
    preset = ds_service.whatsapp_preset()
    assert preset.type == "mongo"
    assert preset.config["collections"] == list(WHATSAPP_MONGO_COLLECTIONS)
    assert preset.field_mapping["content_field"] == WHATSAPP_MONGO_FIELD_MAPPING["content_field"]
    assert preset.field_mapping["role_user_value"] == "customer"


def test_admin_data_source_routes_registered():
    from app.main import app

    paths = set(app.openapi()["paths"])
    for p in (
        "/admin/data-sources/whatsapp-preset",
        "/admin/tenants/{tenant_id}/data-sources",
        "/admin/tenants/{tenant_id}/data-sources/{source_id}",
    ):
        assert p in paths, f"missing admin data-source route: {p}"
