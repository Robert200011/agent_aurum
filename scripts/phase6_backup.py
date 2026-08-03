"""P6.4 encrypted PostgreSQL/MinIO backup and isolated restore command."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from io import BufferedWriter
from pathlib import Path
from typing import Any, BinaryIO, cast
from urllib.parse import urlsplit, urlunsplit

import boto3  # type: ignore[import-untyped]
import psycopg
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from psycopg import sql
from sqlalchemy.engine import make_url

from app.agents.checkpoints import checkpoint_connection_url, encrypted_checkpoint_serializer
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
    "identity.refresh_tokens",
    "audit.audit_logs",
    "finance.financial_accounts",
    "finance.financial_transactions",
    "finance.budgets",
    "finance.investment_holdings",
    "finance.investment_transactions",
    "finance.market_price_snapshots",
    "finance.exchange_rate_snapshots",
    "rag.agent_projects",
    "rag.knowledge_bases",
    "rag.documents",
    "rag.document_versions",
    "rag.document_chunks",
    "rag.ingestion_jobs",
    "rag.retrieval_logs",
    "chat.conversations",
    "chat.messages",
    "chat.message_citations",
    "chat.agent_runs",
    "chat.agent_tool_calls",
    "chat.message_evidence",
    "agent.checkpoints",
)
CONFIG_ALLOWLIST = (
    "AURUM_ENVIRONMENT",
    "AURUM_CHAT_MODEL",
    "AURUM_EMBEDDING_MODEL",
    "AURUM_RERANKER_MODEL",
    "AURUM_OBJECT_STORAGE_BUCKET",
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
    values.setdefault(
        "AURUM_OBJECT_STORAGE_ENDPOINT",
        f"http://127.0.0.1:{values.get('MINIO_PORT', '9000')}",
    )
    values.setdefault("AURUM_OBJECT_STORAGE_BUCKET", "aurum-knowledge")
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
        completed = subprocess.run(  # noqa: S603 - argv is explicit and never invokes a shell
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
            WHERE n.nspname IN ('identity','finance','chat','rag','audit','agent')
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
            SELECT version.source_object_key, version.content_hash, version.parsed_object_key
            FROM rag.document_versions version
            JOIN rag.documents document
              ON document.current_published_version_id = version.id
            JOIN rag.knowledge_bases knowledge_base
              ON knowledge_base.id = document.knowledge_base_id
            WHERE document.deleted_at IS NULL
              AND document.is_enabled
              AND knowledge_base.status = 'published'
            ORDER BY version.source_object_key
            """
        )
        document_objects = [
            {"source_object_key": row[0], "content_hash": row[1], "parsed_object_key": row[2]}
            for row in cursor.fetchall()
        ]
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
        "document_objects": document_objects,
        "finance_summary": finance,
    }


def _s3_client(values: dict[str, str]) -> Any:
    endpoint = _require(values, "AURUM_OBJECT_STORAGE_ENDPOINT")
    access_key = values.get("AURUM_BACKUP_OBJECT_STORAGE_ACCESS_KEY") or _require(
        values, "MINIO_ROOT_USER"
    )
    secret_key = values.get("AURUM_BACKUP_OBJECT_STORAGE_SECRET_KEY") or _require(
        values, "MINIO_ROOT_PASSWORD"
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=values.get("AURUM_OBJECT_STORAGE_REGION", "us-east-1"),
        use_ssl=endpoint.startswith("https://"),
    )


def _backup_objects(client: Any, bucket: str, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    versioning = client.get_bucket_versioning(Bucket=bucket).get("Status", "Disabled")
    records: list[dict[str, Any]] = []
    paginator = client.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket):
        events = [
            (item, False) for item in page.get("Versions", [])
        ] + [(item, True) for item in page.get("DeleteMarkers", [])]
        for item, deleted in events:
            record: dict[str, Any] = {
                "key": item["Key"],
                "version_id": item.get("VersionId"),
                "is_latest": bool(item.get("IsLatest")),
                "last_modified": item["LastModified"].isoformat(),
                "delete_marker": deleted,
            }
            if not deleted:
                response = client.get_object(
                    Bucket=bucket, Key=item["Key"], VersionId=item.get("VersionId")
                )
                digest = hashlib.sha256()
                blob_path = directory / hashlib.sha256(
                    f"{item['Key']}\0{item.get('VersionId', '')}".encode()
                ).hexdigest()
                with blob_path.open("wb") as output:
                    while chunk := response["Body"].read(1024 * 1024):
                        digest.update(chunk)
                        output.write(chunk)
                record.update(
                    {
                        "size": blob_path.stat().st_size,
                        "sha256": digest.hexdigest(),
                        "blob": blob_path.name,
                    }
                )
            records.append(record)
    records.sort(
        key=lambda item: (
            item["last_modified"],
            item["key"],
            item.get("version_id") or "",
        )
    )
    return {"bucket": bucket, "versioning": versioning, "versions": records}


def _validate_database_object_references(
    database: dict[str, Any], storage: dict[str, Any], *, environment: str
) -> dict[str, Any]:
    latest = {
        item["key"]: item
        for item in storage["versions"]
        if item["is_latest"] and not item["delete_marker"]
    }
    failures: list[dict[str, str]] = []
    excluded_test_fixtures = 0
    missing_rebuildable_parsed_objects = 0
    checked = 0
    for reference in database["document_objects"]:
        source_key = reference["source_object_key"]
        if environment != "production" and source_key.startswith("integration/"):
            excluded_test_fixtures += 1
            continue
        checked += 1
        source = latest.get(source_key)
        if source is None:
            failures.append({"key": source_key, "reason": "source_missing"})
        elif source.get("sha256") != reference["content_hash"]:
            failures.append({"key": source_key, "reason": "source_hash_mismatch"})
        parsed_key = reference.get("parsed_object_key")
        if parsed_key and parsed_key not in latest:
            missing_rebuildable_parsed_objects += 1
    result = {
        "accepted": not failures,
        "checked_references": checked,
        "excluded_test_fixture_references": excluded_test_fixtures,
        "missing_rebuildable_parsed_objects": missing_rebuildable_parsed_objects,
        "failures": failures,
    }
    if failures:
        raise BackupValidationError("database object references failed hash/existence validation")
    return result


def _safe_configuration(values: dict[str, str]) -> dict[str, Any]:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("git executable was not found")
    return {
        "values": {name: values.get(name, "") for name in CONFIG_ALLOWLIST},
        "git_revision": subprocess.run(  # noqa: S603,S607 - fixed read-only Git command
            [git_executable, "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip(),
        "image_revision": values.get("AURUM_IMAGE_REVISION", "unrecorded"),
        "migration_revision": values.get("AURUM_MIGRATION_REVISION", "alembic-head"),
        "prompt_version": values.get("AURUM_PROMPT_VERSION", "finance-agent-p6.3-v1"),
        "key_identifiers": {
            "backup": values.get("AURUM_BACKUP_KEY_ID", "unrecorded"),
            "checkpoint": values.get("AURUM_LANGGRAPH_KEY_ID", "unrecorded"),
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
            ["docker", "compose", "--env-file", str(args.compose_env_file),
             "-f", str(args.compose_file), "exec", "-T", args.postgres_service,
             "pg_dump", "--username", args.postgres_user, "--dbname", args.database,
             "--format=custom", "--compress=6", "--no-owner", "--no-acl"],
            stdout=dump_path,
        )
        database = _database_snapshot(_require(values, "AURUM_MIGRATION_DATABASE_URL"))
        storage = _backup_objects(
            _s3_client(values), _require(values, "AURUM_OBJECT_STORAGE_BUCKET"), temp / "objects"
        )
        storage["database_reference_validation"] = _validate_database_object_references(
            database,
            storage,
            environment=values.get("AURUM_ENVIRONMENT", "development"),
        )
        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "backup_id": backup_id,
            "created_at": started.isoformat(),
            "completed_at": _utc_now().isoformat(),
            "database": {**database, "dump_sha256": sha256_file(dump_path)},
            "object_storage": storage,
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
    write_json(sidecar, evidence)
    replica_dir_value = args.replica_directory or values.get("AURUM_BACKUP_REPLICA_DIRECTORY")
    if replica_dir_value:
        replica_dir = Path(replica_dir_value).resolve()
        if replica_dir == output_dir:
            raise BackupValidationError("replica directory must differ from primary output")
        replica_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination, replica_dir / destination.name)
        shutil.copy2(sidecar, replica_dir / sidecar.name)
        evidence["replicated"] = True
    expired = retention_candidates(
        output_dir.iterdir(), now=_utc_now(), retention_days=args.retention_days
    )
    for path in expired:
        path.unlink()
    evidence["expired_artifacts_removed"] = len(expired)
    write_json(sidecar, evidence)
    metrics_file = (args.metrics_file or output_dir / "aurum_backup.prom").resolve()
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    metrics_temp = metrics_file.with_suffix(metrics_file.suffix + ".tmp")
    metrics_temp.write_text(
        "# HELP aurum_backup_last_success_timestamp_seconds Last successful backup time.\n"
        "# TYPE aurum_backup_last_success_timestamp_seconds gauge\n"
        f"aurum_backup_last_success_timestamp_seconds {int(_utc_now().timestamp())}\n",
        encoding="utf-8",
    )
    metrics_temp.replace(metrics_file)
    return {"accepted": True, "backup": str(destination), "evidence": str(sidecar), **evidence}


def _verify_sidecar(backup: Path) -> dict[str, Any]:
    sidecar = backup.with_suffix(backup.suffix + ".sha256.json")
    evidence = read_json(sidecar)
    if evidence.get("ciphertext_sha256") != sha256_file(backup):
        raise BackupValidationError("backup ciphertext checksum does not match sidecar")
    return evidence


def _database_exists(url: str, database: str) -> bool:
    postgres_url = _replace_database(url, "postgres")
    with psycopg.connect(_psycopg_url(postgres_url)) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
        return cursor.fetchone() is not None


def _replace_database(url: str, database: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database}", parsed.query, parsed.fragment))


def _restore_objects(client: Any, bucket: str, manifest: dict[str, Any], root: Path) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket"}:
            raise
    else:
        raise BackupValidationError("destination bucket already exists; overwrite is forbidden")
    client.create_bucket(Bucket=bucket)
    client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    for item in manifest["object_storage"]["versions"]:
        if item["delete_marker"]:
            client.delete_object(Bucket=bucket, Key=item["key"])
            continue
        blob = root / "objects" / item["blob"]
        if sha256_file(blob) != item["sha256"]:
            raise BackupValidationError("object blob checksum mismatch")
        with blob.open("rb") as handle:
            client.put_object(Bucket=bucket, Key=item["key"], Body=handle)


def _verify_restore(
    values: dict[str, str], manifest: dict[str, Any], database: str, bucket: str, started: datetime
) -> dict[str, Any]:
    target_url = _replace_database(_require(values, "AURUM_MIGRATION_DATABASE_URL"), database)
    restored = _database_snapshot(target_url)
    expected = manifest["database"]
    checks: dict[str, bool] = {
        "alembic_head": restored["alembic_version"] == expected["alembic_version"],
        "table_counts": restored["counts"] == expected["counts"],
        "rls": restored["rls"] == expected["rls"],
        "finance_summary": restored["finance_summary"] == expected["finance_summary"],
        "database_object_references": bool(
            manifest["object_storage"]["database_reference_validation"]["accepted"]
        ),
    }
    with (
        psycopg.connect(_psycopg_url(target_url)) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT count(*) FROM chat.message_citations citation
            LEFT JOIN chat.messages message ON message.id = citation.message_id
            LEFT JOIN rag.document_chunks chunk ON chunk.id = citation.chunk_id
            WHERE message.id IS NULL OR chunk.id IS NULL
            """
        )
        checks["citations_open"] = _one(cursor)[0] == 0
        cursor.execute(
            """
            SELECT count(*) FROM chat.messages message
            LEFT JOIN chat.conversations conversation
              ON conversation.id = message.conversation_id
             AND conversation.user_id = message.user_id
            WHERE conversation.id IS NULL
            """
        )
        checks["chat_integrity_smoke"] = _one(cursor)[0] == 0
        cursor.execute("SELECT thread_id::text FROM agent.checkpoints LIMIT 1")
        checkpoint = cursor.fetchone()
    if checkpoint is None:
        checks["checkpoint_decrypt"] = True
    else:
        configured_checkpoint_key = values.get("AURUM_LANGGRAPH_AES_KEY")
        checkpoint_key = (
            configured_checkpoint_key.encode()
            if configured_checkpoint_key
            else hmac.digest(
                _require(values, "AURUM_JWT_SECRET_KEY").encode(),
                b"aurum-agent/langgraph-checkpoint/v1",
                "sha256",
            )
        )
        serializer = encrypted_checkpoint_serializer(checkpoint_key)
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row

        checkpoint_url = checkpoint_connection_url(target_url)
        with psycopg.connect(
            checkpoint_url, autocommit=True, prepare_threshold=0, row_factory=dict_row
        ) as checkpoint_connection:
            saver = PostgresSaver(checkpoint_connection, serde=serializer)
            checks["checkpoint_decrypt"] = saver.get_tuple(
                {"configurable": {"thread_id": checkpoint[0], "checkpoint_ns": ""}}
            ) is not None
    client = _s3_client(values)
    expected_latest = {
        item["key"]: item
        for item in manifest["object_storage"]["versions"]
        if item["is_latest"] and not item["delete_marker"]
    }
    object_hashes_ok = True
    for key, item in expected_latest.items():
        response = client.get_object(Bucket=bucket, Key=key)
        digest = hashlib.sha256(response["Body"].read()).hexdigest()
        object_hashes_ok = object_hashes_ok and digest == item["sha256"]
    checks["object_hashes"] = object_hashes_ok
    finished = _utc_now()
    backup_time = datetime.fromisoformat(manifest["database"]["snapshot_at"])
    return {
        "accepted": all(checks.values()),
        "checks": checks,
        "rpo_seconds_at_drill": max(0.0, (started - backup_time).total_seconds()),
        "rto_seconds": (finished - started).total_seconds(),
        "object_count": len(expected_latest),
        "finished_at": finished.isoformat(),
    }


def command_restore(args: argparse.Namespace) -> dict[str, Any]:
    started = _utc_now()
    if not args.confirm_new_targets:
        raise BackupValidationError("restore requires --confirm-new-targets")
    if not SAFE_NAME.fullmatch(args.destination_database) or not SAFE_NAME.fullmatch(
        args.destination_bucket
    ):
        raise BackupValidationError("destination names must use safe alphanumeric syntax")
    values = _load_env(args.env_file)
    source_database = make_url(_require(values, "AURUM_MIGRATION_DATABASE_URL")).database
    source_bucket = _require(values, "AURUM_OBJECT_STORAGE_BUCKET")
    if args.destination_database == source_database or args.destination_bucket == source_bucket:
        raise BackupValidationError("restore targets must be isolated from source production names")
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
        _run(
            ["docker", "compose", "--env-file", str(args.compose_env_file),
             "-f", str(args.compose_file), "exec", "-T",
             args.postgres_service, "createdb", "--username", args.postgres_user,
             args.destination_database]
        )
        _run(
            ["docker", "compose", "--env-file", str(args.compose_env_file),
             "-f", str(args.compose_file), "exec", "-T",
             args.postgres_service, "pg_restore", "--username", args.postgres_user,
             "--dbname", args.destination_database, "--no-owner", "--no-acl", "--exit-on-error"],
            stdin=extracted / "postgres.dump",
        )
        _restore_objects(_s3_client(values), args.destination_bucket, manifest, extracted)
        report = _verify_restore(
            values, manifest, args.destination_database, args.destination_bucket, started
        )
    report.update(
        {
            "backup_id": manifest["backup_id"],
            "started_at": started.isoformat(),
            "destination_database": args.destination_database,
            "destination_bucket": args.destination_bucket,
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
    restore.add_argument("--destination-bucket", required=True)
    restore.add_argument("--report", type=Path, required=True)
    restore.add_argument("--confirm-new-targets", action="store_true")
    restore.set_defaults(handler=command_restore)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = args.handler(args)
    except (BackupValidationError, ClientError, OSError, RuntimeError, psycopg.Error) as exc:
        print(json.dumps({"accepted": False, "error": type(exc).__name__, "detail": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("accepted") else 1


if __name__ == "__main__":
    sys.exit(main())
