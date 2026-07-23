"""Grant least-privilege application access after owner-run migrations."""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.db.base import (
    AGENT_SCHEMA,
    AUDIT_SCHEMA,
    CHAT_SCHEMA,
    FINANCE_SCHEMA,
    IDENTITY_SCHEMA,
    RAG_SCHEMA,
)

DATABASE_ROLE_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
APPLICATION_SCHEMAS = (
    IDENTITY_SCHEMA,
    FINANCE_SCHEMA,
    RAG_SCHEMA,
    CHAT_SCHEMA,
    AUDIT_SCHEMA,
    AGENT_SCHEMA,
)


def validate_database_role(role: str) -> str:
    """Validate before using a role as a quoted SQL identifier."""

    if not DATABASE_ROLE_PATTERN.fullmatch(role):
        raise ValueError("invalid application database role")
    return role


async def grant_application_privileges(settings: Settings) -> None:
    """Grant table access without giving schema ownership or BYPASSRLS."""

    role = validate_database_role(settings.app_database_role)
    quoted_role = f'"{role}"'
    engine = create_async_engine(settings.migration_database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
                {"role": role},
            )
            if exists != 1:
                raise RuntimeError(
                    f"database role {role!r} does not exist; initialize PostgreSQL first"
                )

            for schema in APPLICATION_SCHEMAS:
                quoted_schema = f'"{schema}"'
                await connection.execute(
                    text(f"GRANT USAGE ON SCHEMA {quoted_schema} TO {quoted_role}")
                )
                await connection.execute(
                    text(
                        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                        f"IN SCHEMA {quoted_schema} TO {quoted_role}"
                    )
                )
                await connection.execute(
                    text(
                        "GRANT USAGE, SELECT ON ALL SEQUENCES "
                        f"IN SCHEMA {quoted_schema} TO {quoted_role}"
                    )
                )
                await connection.execute(
                    text(
                        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quoted_schema} "
                        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES "
                        f"TO {quoted_role}"
                    )
                )
                await connection.execute(
                    text(
                        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quoted_schema} "
                        f"GRANT USAGE, SELECT ON SEQUENCES TO {quoted_role}"
                    )
                )
    finally:
        await engine.dispose()
