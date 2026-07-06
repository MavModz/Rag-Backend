"""Provisioning: machine-to-machine tenant creation for purchase/billing systems.

Secured by a shared secret (X-Provisioning-Key), NOT a user login — so an external
checkout/billing webhook can create a tenant + admin + API key when a customer
purchases the platform. Disabled when PROVISIONING_API_KEY is empty.
"""
