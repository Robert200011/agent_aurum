"""Encrypted PostgreSQL backup and isolated restore command."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from io import BufferedWriter
from pathlib import Path
from typing import Any, BinaryIO, cast

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.operations.backup import (
    BACKUP_FORMAT_VERSION,
    BackupValidationError,
    create_archive,
    decode_backup_key,
    decrypt_file,
    encrypt_file,
    extract_archive,
    read_json,
    retention_candidates,
    sha256_file,
    validate_manifest,
    write_json,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env"
SAFE_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{2,62}$")
COUNT_TABLES = (
    "identity.users",
    "identity.user_profiles",
    "identity.user_preferences",
    "identity.personal_financial_profiles",
    "identity.user_memory_settings",
    "identity.user_memories",
    "identity.user_memory_confirmations",
    "identity.refresh_tokens",
    "audit.audit_logs",
    "finance.financial_accounts",
    "finance.financial_transactions",
    "finance.budgets",
    "finance.investment_holdings",
    "finance.investment_transactions",
    "finance.market_price_snapshots",
    "finance.exchange_rate_snapshots",
    "chat.conversations",
    "chat.messages",
    "chat.agent_runs",
    "chat.agent_run_memories",
    "chat.agent_tool_calls",
    "chat.message_evidence",
    "agent.checkpoints",
)
CONFIG_ALLOWLIST = (
    "AURUM_ENVIRONMENT",
    "AURUM_CHAT_MODEL",
    "AURUM_EMBEDDING_MODEL",
    "AURUM_APP_DATABASE_ROLE",
)


def _load_env(path: Path) -> dict[str, str]:
    values = dict(os.environ)
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def _require(values: dict[str, str], name: str) -> str:
    value = values.get(name, "")
    if not value:
        raise BackupValidationError(f"required environment variable is missing: {name}")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _run(command: list[str], *, stdin: Path | None = None, stdout: Path | None = None) -> None:
    input_handle = stdin.open("rb") if stdin else None
    output_handle: BinaryIO | int = stdout.open("wb") if stdout else subprocess.DEVNULL
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, never a shell
            command,
            cwd=ROOT,
            stdin=input_handle,
            stdout=output_handle,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        if input_handle:
            input_handle.close()
        if isinstance(output_handle, BufferedWriter):
            output_handle.close()
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[-1000:]
        raise RuntimeError(f"operational command failed ({completed.returncode}): {detail}")


def _psycopg_url(url: str, database: str | None = None) -> str:
    parsed = make_url(url)
    if database:
        parsed = parsed.set(database=database)
    parsed = parsed.set(drivername="postgresql")
    if parsed.host == "localhost":
        parsed = parsed.set(host="127.0.0.1")
    parsed = parsed.update_query_dict({"connect_timeout": "10"})
    return parsed.render_as_string(hide_password=False)


def _one(cursor: psycopg.Cursor[Any]) -> tuple[Any, ...]:
    row = cursor.fetchone()
    if row is None:
        raise BackupValidationError("required database query returned no row")
    return cast(tuple[Any, ...], row)


def _database_snapshot(url: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    with psycopg.connect(_psycopg_url(url)) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT clock_timestamp(), current_database()")
        snapshot_at, database_name = _one(cursor)
        cursor.execute("SELECT version_num FROM alembic_version")
        alembic_version = _one(cursor)[0]
        for qualified in COUNT_TABLES:
            schema_name, table_name = qualified.split(".", 1)
            cursor.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(schema_name), sql.Identifier(table_name)
                )
            )
            counts[qualified] = _one(cursor)[0]
        cursor.execute(
            """
            SELECT n.nspname || '.' || c.relname, c.relrowsecurity,
                   count(p.policyname)::int
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_policies p
              ON p.schemaname = n.nspname AND p.tablename = c.relname
            WHERE n.nspname IN ('identity','finance','chat','audit','agent')
              AND c.relkind = 'r'
            GROUP BY n.nspname, c.relname, c.relrowsecurity
            ORDER BY 1
            """
        )
        rls = {
            name: {"enabled": enabled, "policy_count": policy_count}
            for name, enabled, policy_count in cursor.fetchall()
        }
        cursor.execute(
            """
            SELECT
              coalesce(sum(balance), 0)::text,
              (SELECT count(*) FROM finance.financial_transactions),
              (SELECT count(*) FROM finance.investment_holdings),
              (SELECT count(*) FROM finance.investment_transactions)
            FROM finance.financial_accounts
            """
        )
        finance = dict(
            zip(
                ("account_balance_sum", "transaction_count", "holding_count", "trade_count"),
                _one(cursor),
                strict=True,
            )
        )
    return {
        "name": database_name,
        "snapshot_at": snapshot_at.isoformat(),
        "alembic_version": alembic_version,
        "counts": counts,
        "rls": rls,
        "finance_summary": finance,
    }


def _safe_configuration(values: dict[str, str]) -> dict[str, Any]:
    return {
        "values": {key: values[key] for key in CONFIG_ALLOWLIST if values.get(key)},
        "key_ids": {
            "backup": values.get("AURUM_BACKUP_KEY_ID", "unrecorded"),
            "langgraph": values.get("AURUM_LANGGRAPH_KEY_ID", "unrecorded"),
            "jwt": values.get("AURUM_JWT_KEY_ID", "unrecorded"),
        },
    }


def command_backup(args: argparse.Namespace) -> dict[str, Any]:
    started = _utc_now()
    values = _load_env(args.env_file)
    key = decode_backup_key(_require(values, "AURUM_BACKUP_ENCRYPTION_KEY"))
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    backup_id = started.strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(4).hex()
    destination = output_dir / f"aurum-{backup_id}.aurum-backup"
    with tempfile.TemporaryDirectory(prefix="aurum-backup-") as temp_name:
        temp = Path(temp_name)
        dump_path = temp / "postgres.dump"
        _run(
            [
                "docker", "compose", "--env-file", str(args.compose_env_file),
                "-f", str(args.compose_file), "exec", "-T", args.postgres_service,
                "pg_dump", "--username", args.postgres_user, "--dbname", args.database,
                "--format=custom", "--compress=6", "--no-owner", "--no-acl",
            ],
            stdout=dump_path,
        )
        database = _database_snapshot(_require(values, "AURUM_MIGRATION_DATABASE_URL"))
        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "backup_id": backup_id,
            "created_at": started.isoformat(),
            "completed_at": _utc_now().isoformat(),
            "database": {**database, "dump_sha256": sha256_file(dump_path)},
            "configuration": _safe_configuration(values),
            "recovery_objectives": {"rpo_hours": 24, "rto_hours": 4},
        }
        write_json(temp / "manifest.json", manifest)
        archive = temp / "backup.tar.gz"
        create_archive(temp, archive)
        encrypt_file(archive, destination, key)
    sidecar = destination.with_suffix(destination.suffix + ".sha256.json")
    evidence = {
        "format_version": BACKUP_FORMAT_VERSION,
        "backup_id": backup_id,
        "created_at": started.isoformat(),
        "completed_at": _utc_now().isoformat(),
        "ciphertext_sha256": sha256_file(destination),
        "size_bytes": destination.stat().st_size,
        "key_id": values.get("AURUM_BACKUP_KEY_ID", "unrecorded"),
    }
    replica_dir_value = args.replica_directory or values.get("AURUM_BACKUP_REPLICA_DIRECTORY")
    if replica_dir_value:
        replica_dir = Path(replica_dir_value).resolve()
        if replica_dir == output_dir:
            raise BackupValidationError("replica directory must differ from primary output")
        replica_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination, replica_dir / destination.name)
        evidence["replicated"] = True
    expired = retention_candidates(
        output_dir.iterdir(), now=_utc_now(), retention_days=args.retention_days
    )
    for path in expired:
        path.unlink()
    evidence["expired_artifacts_removed"] = len(expired)
    write_json(sidecar, evidence)
    if replica_dir_value:
        shutil.copy2(sidecar, Path(replica_dir_value).resolve() / sidecar.name)
    metrics_file = (args.metrics_file or output_dir / "aurum_backup.prom").resolve()
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    metrics_file.write_text(
        "# HELP aurum_backup_last_success_timestamp_seconds Last successful backup time.\n"
        "# TYPE aurum_backup_last_success_timestamp_seconds gauge\n"
        f"aurum_backup_last_success_timestamp_seconds {int(_utc_now().timestamp())}\n",
        encoding="utf-8",
    )
    return {"accepted": True, "backup": str(destination), "evidence": str(sidecar), **evidence}


def _verify_sidecar(backup: Path) -> dict[str, Any]:
    evidence = read_json(backup.with_suffix(backup.suffix + ".sha256.json"))
    if evidence.get("ciphertext_sha256") != sha256_file(backup):
        raise BackupValidationError("backup ciphertext checksum does not match sidecar")
    return evidence


def _database_exists(url: str, database: str) -> bool:
    with (
        psycopg.connect(_psycopg_url(url, "postgres")) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
        return cursor.fetchone() is not None


def _verify_restore(
    values: dict[str, str], manifest: dict[str, Any], database: str, started: datetime
) -> dict[str, Any]:
    restored = _database_snapshot(
        _psycopg_url(_require(values, "AURUM_MIGRATION_DATABASE_URL"), database)
    )
    expected = manifest["database"]
    checks: dict[str, bool] = {
        "alembic_head": restored["alembic_version"] == expected["alembic_version"],
        "table_counts": restored["counts"] == expected["counts"],
        "rls": restored["rls"] == expected["rls"],
        "finance_summary": restored["finance_summary"] == expected["finance_summary"],
    }
    finished = _utc_now()
    backup_time = datetime.fromisoformat(manifest["database"]["snapshot_at"])
    return {
        "accepted": all(checks.values()),
        "checks": checks,
        "rpo_seconds_at_drill": max(0.0, (started - backup_time).total_seconds()),
        "rto_seconds": (finished - started).total_seconds(),
        "finished_at": finished.isoformat(),
    }


def command_restore(args: argparse.Namespace) -> dict[str, Any]:
    started = _utc_now()
    if not args.confirm_new_targets:
        raise BackupValidationError("restore requires --confirm-new-targets")
    if not SAFE_NAME.fullmatch(args.destination_database):
        raise BackupValidationError("destination database name must use safe alphanumeric syntax")
    values = _load_env(args.env_file)
    source_database = make_url(_require(values, "AURUM_MIGRATION_DATABASE_URL")).database
    if args.destination_database == source_database:
        raise BackupValidationError("restore target must be isolated from the source database")
    if _database_exists(
        _require(values, "AURUM_MIGRATION_DATABASE_URL"), args.destination_database
    ):
        raise BackupValidationError("destination database already exists; overwrite is forbidden")
    backup = args.backup.resolve()
    _verify_sidecar(backup)
    key = decode_backup_key(_require(values, "AURUM_BACKUP_ENCRYPTION_KEY"))
    with tempfile.TemporaryDirectory(prefix="aurum-restore-") as temp_name:
        temp = Path(temp_name)
        archive = temp / "backup.tar.gz"
        decrypt_file(backup, archive, key)
        extracted = temp / "extracted"
        extracted.mkdir()
        extract_archive(archive, extracted)
        manifest = read_json(extracted / "manifest.json")
        validate_manifest(manifest)
        if sha256_file(extracted / "postgres.dump") != manifest["database"]["dump_sha256"]:
            raise BackupValidationError("database dump checksum mismatch")
        base = [
            "docker", "compose", "--env-file", str(args.compose_env_file),
            "-f", str(args.compose_file), "exec", "-T", args.postgres_service,
        ]
        _run([*base, "createdb", "--username", args.postgres_user, args.destination_database])
        _run(
            [
                *base, "pg_restore", "--username", args.postgres_user,
                "--dbname", args.destination_database, "--no-owner", "--no-acl",
                "--exit-on-error",
            ],
            stdin=extracted / "postgres.dump",
        )
        report = _verify_restore(values, manifest, args.destination_database, started)
    report.update(
        {
            "backup_id": manifest["backup_id"],
            "started_at": started.isoformat(),
            "destination_database": args.destination_database,
            "rpo_target_seconds": 86400,
            "rto_target_seconds": 14400,
        }
    )
    report["objectives_met"] = (
        report["rpo_seconds_at_drill"] <= report["rpo_target_seconds"]
        and report["rto_seconds"] <= report["rto_target_seconds"]
    )
    report["accepted"] = report["accepted"] and report["objectives_met"]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--compose-file", type=Path, default=ROOT / "compose.yaml")
    parser.add_argument("--compose-env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--postgres-service", default="postgres")
    parser.add_argument("--postgres-user", default="aurum")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup")
    backup.add_argument("--output-dir", type=Path, required=True)
    backup.add_argument("--replica-directory", type=str)
    backup.add_argument("--metrics-file", type=Path)
    backup.add_argument("--retention-days", type=int, default=30)
    backup.add_argument("--database", default="aurum")
    backup.set_defaults(handler=command_backup)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--destination-database", required=True)
    restore.add_argument("--report", type=Path, required=True)
    restore.add_argument("--confirm-new-targets", action="store_true")
    restore.set_defaults(handler=command_restore)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = args.handler(args)
    except (BackupValidationError, OSError, RuntimeError, psycopg.Error) as exc:
        print(json.dumps({"accepted": False, "error": type(exc).__name__, "detail": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
