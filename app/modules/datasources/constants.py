"""Default data-source templates for admin UI."""
from __future__ import annotations

WHATSAPP_MONGO_COLLECTIONS = ("active_chats", "history_chats")

WHATSAPP_MONGO_FIELD_MAPPING: dict = {
    "company_field": "company_id",
    "company_is_object_id": True,
    "user_fields": ["from", "to"],
    "content_field": "body",
    "role_field": "sender_type",
    "role_user_value": "customer",
    "timestamp_field": "created_at",
}

WHATSAPP_MONGO_CONFIG_TEMPLATE: dict = {
    "uri": "",
    "db": "",
    "collections": list(WHATSAPP_MONGO_COLLECTIONS),
}
