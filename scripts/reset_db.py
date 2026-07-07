"""CLI to wipe Postgres and re-apply all Alembic migrations.

Use when you need a clean schema (e.g. after provisioning model changes).
Wipes ALL tenant, user, and API key data.

Usage:
    python -m scripts.reset_db --yes
    python -m scripts.reset_db --yes --seed
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys

from sqlalchemy import text

from app.platform.db.postgres import get_engine


async def _wipe_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))


def _run_migrations() -> None:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)


def _run_seed() -> None:
    subprocess.run([sys.executable, "-m", "scripts.seed"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drop all Postgres tables and re-apply Alembic migrations."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        required=True,
        help="Confirm the destructive wipe of all database data.",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Run scripts.seed after migrations (admin user + default tenant + API key).",
    )
    args = parser.parse_args()

    print("Wiping public schema…")
    asyncio.run(_wipe_schema())

    print("Applying Alembic migrations…")
    _run_migrations()

    if args.seed:
        print("Seeding baseline data…")
        _run_seed()

    print("Database reset complete.")
    if not args.seed:
        print("Optional: python -m scripts.seed")


if __name__ == "__main__":
    main()
