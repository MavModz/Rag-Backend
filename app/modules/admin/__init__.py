"""Admin Service: cross-tenant management surface for the superadmin console.

Distinct from the self-service ``/auth/*`` routes: these endpoints operate on any
tenant by id and require admin permissions. They back the Next.js superadmin app
(separate repo). V1 covers tenants, users, and API keys.
"""
