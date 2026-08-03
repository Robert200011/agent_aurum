"""Preview or apply the audited database portion of the P6.4 retention policy."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.operations.backup import BackupValidationError, read_json

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_TARGETS = {
    "expired_refresh_tokens": ("identity", "refresh_tokens", "expires_at"),
    "retrieval_logs": ("rag", "retrieval_logs", "created_at"),
}


def _load_env(path: Path) -> dict[str, str]:
    values = dict(os.environ)
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def _database_url(value: str) -> str:
    parsed = make_url(value).set(drivername="postgresql")
    if parsed.host == "localhost":
        parsed = parsed.set(host="127.0.0.1")
    parsed = parsed.update_query_dict({"connect_timeout": "10"})
    return parsed.render_as_string(hide_password=False)


def execute_retention(
    *, policy: dict[str, Any], database_url: str, apply: bool, operator: str
) -> dict[str, Any]:
    version = policy.get("version")
    if not isinstance(version, str) or not version:
        raise BackupValidationError("retention policy version is missing")
    configured = {item.get("name"): item for item in policy.get("targets", [])}
    results: list[dict[str, Any]] = []
    with psycopg.connect(_database_url(database_url)) as connection, connection.cursor() as cursor:
        for name, (schema_name, table_name, timestamp_column) in ALLOWED_TARGETS.items():
            item = configured.get(name)
            if not isinstance(item, dict):
                raise BackupValidationError(f"required retention target is missing: {name}")
            if item.get("table") != f"{schema_name}.{table_name}":
                raise BackupValidationError(f"retention target table is not approved: {name}")
            days = item.get("retention_days")
            if not isinstance(days, int) or days < 1:
                raise BackupValidationError(f"invalid retention period: {name}")
            predicate = sql.SQL("{} < clock_timestamp() - (%s * interval '1 day')").format(
                sql.Identifier(timestamp_column)
            )
            if apply:
                statement = sql.SQL("DELETE FROM {}.{} WHERE {}").format(
                    sql.Identifier(schema_name), sql.Identifier(table_name), predicate
                )
                cursor.execute(statement, (days,))
                affected = cursor.rowcount
            else:
                statement = sql.SQL("SELECT count(*) FROM {}.{} WHERE {}").format(
                    sql.Identifier(schema_name), sql.Identifier(table_name), predicate
                )
                cursor.execute(statement, (days,))
                row = cursor.fetchone()
                affected = int(row[0]) if row is not None else 0
            results.append(
                {"target": name, "retention_days": days, "candidate_rows": affected}
            )
        if apply:
            cursor.execute(
                """
                INSERT INTO audit.audit_logs
                  (id, action, resource_type, resource_id, user_agent, detail, created_at)
                VALUES (%s, 'operations.retention_applied', 'retention_policy', %s,
                        'phase6-retention-runner', %s::jsonb, clock_timestamp())
                """,
                (
                    uuid4(),
                    version,
                    json.dumps({"operator": operator, "results": results}),
                ),
            )
        connection.commit()
    return {"accepted": True, "mode": "apply" if apply else "preview", "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=ROOT / "deploy/retention-policy.json")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--operator", default=os.environ.get("USERNAME", "unknown"))
    args = parser.parse_args()
    try:
        values = _load_env(args.env_file)
        database_url = values.get("AURUM_MIGRATION_DATABASE_URL", "")
        if not database_url:
            raise BackupValidationError("AURUM_MIGRATION_DATABASE_URL is required")
        result = execute_retention(
            policy=read_json(args.policy),
            database_url=database_url,
            apply=args.apply,
            operator=args.operator,
        )
    except (BackupValidationError, OSError, psycopg.Error) as exc:
        print(json.dumps({"accepted": False, "error": type(exc).__name__, "detail": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
