"""P6.5 release manifest, canary observation, cutover, and rollback primitives."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.policies.rag_prompt import SYSTEM_PROMPT
from app.operations.backup import BackupValidationError, read_json, sha256_file, write_json

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "p6.5-release-v1"
SLOTS = {"blue", "green"}
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _git(*arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise BackupValidationError("git executable was not found")
    completed = subprocess.run(  # noqa: S603,S607 - fixed read-only Git invocation
        [executable, *arguments], cwd=ROOT, text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()


def _immutable_image(image: str, revision: str) -> bool:
    if image.endswith(":latest") or ":latest@" in image:
        return False
    return "@sha256:" in image or revision in image


def create_manifest(
    *,
    release_id: str,
    mode: str,
    operator: str,
    candidate_slot: str,
    api_image: str,
    web_image: str,
    migration_revision: str,
    backup_evidence: str | None,
) -> dict[str, Any]:
    if candidate_slot not in SLOTS:
        raise BackupValidationError("candidate slot must be blue or green")
    revision = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    if mode == "production":
        if dirty:
            raise BackupValidationError("production release requires a clean Git worktree")
        if not SHA_PATTERN.fullmatch(revision):
            raise BackupValidationError("production release requires a full Git revision")
        if not _immutable_image(api_image, revision) or not _immutable_image(web_image, revision):
            raise BackupValidationError("production images must use the Git SHA tag or digest")
        if backup_evidence is None:
            raise BackupValidationError("production release requires verified backup evidence")
    elif mode != "rehearsal":
        raise BackupValidationError("release mode must be rehearsal or production")
    datasets = {}
    for name in (
        "phase5-finance-agent.json",
        "phase6-rag-regression.json",
        "phase6-prompt-injection.json",
        "phase6-fault-scenarios.json",
        "memory-release-gate.json",
    ):
        path = ROOT / "evals" / name
        datasets[name] = sha256_file(path)
    return {
        "schema_version": SCHEMA_VERSION,
        "release_id": release_id,
        "created_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "operator": operator,
        "candidate_slot": candidate_slot,
        "git_revision": revision,
        "worktree_dirty": dirty,
        "images": {"api": api_image, "web": web_image},
        "migration_revision": migration_revision,
        "graph_version": "finance-agent-p6.3-v1",
        "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "dataset_sha256": datasets,
        "configuration_sha256": sha256_file(ROOT / "deploy/compose.production.yaml"),
        "backup_evidence": backup_evidence,
    }


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise BackupValidationError("unsupported release manifest schema")
    if manifest.get("candidate_slot") not in SLOTS:
        raise BackupValidationError("release manifest candidate slot is invalid")
    if not isinstance(manifest.get("images"), dict):
        raise BackupValidationError("release manifest images are missing")
    if manifest.get("mode") == "production":
        revision = manifest.get("git_revision")
        if not isinstance(revision, str) or not SHA_PATTERN.fullmatch(revision):
            raise BackupValidationError("production manifest Git revision is invalid")
        if manifest.get("worktree_dirty") is not False:
            raise BackupValidationError("production manifest records a dirty worktree")
        for image in manifest["images"].values():
            if not isinstance(image, str) or not _immutable_image(image, revision):
                raise BackupValidationError("production manifest contains a mutable image")
        evidence_path = manifest.get("backup_evidence")
        if not isinstance(evidence_path, str) or not evidence_path:
            raise BackupValidationError("production manifest lacks backup evidence")


def render_upstream(slot: str) -> str:
    if slot not in SLOTS:
        raise BackupValidationError("release slot must be blue or green")
    return (
        "@api path /api/*\n"
        "handle @api {\n"
        f"\theader X-Aurum-Release-Slot {slot}\n"
        f"\treverse_proxy api-{slot}:8010 {{\n"
        "\t\tflush_interval -1\n"
        "\t}\n"
        "}\n\n"
        "handle {\n"
        f"\theader X-Aurum-Release-Slot {slot}\n"
        f"\treverse_proxy web-{slot}:8080\n"
        "}\n"
    )


def activate_slot(state_directory: Path, slot: str, release_id: str) -> dict[str, Any]:
    state_directory.mkdir(parents=True, exist_ok=True)
    state_path = state_directory / "release-state.json"
    previous_state = read_json(state_path) if state_path.exists() else {}
    previous_slot = previous_state.get("active_slot")
    if previous_slot not in SLOTS:
        previous_slot = "green" if slot == "blue" else "blue"
    upstream = state_directory / "active-upstream.caddy"
    temporary = upstream.with_suffix(".tmp")
    temporary.write_text(render_upstream(slot), encoding="utf-8")
    temporary.replace(upstream)
    state = {
        "schema_version": SCHEMA_VERSION,
        "release_id": release_id,
        "active_slot": slot,
        "previous_slot": previous_slot,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    write_json(state_path, state)
    return state


def rollback_slot(state_directory: Path, release_id: str) -> dict[str, Any]:
    state = read_json(state_directory / "release-state.json")
    target = state.get("previous_slot")
    if target not in SLOTS:
        raise BackupValidationError("release state has no valid rollback slot")
    return activate_slot(state_directory, target, release_id)


def observe(url: str, *, expected_slot: str, requests: int, timeout: float) -> dict[str, Any]:
    if expected_slot not in SLOTS or requests < 1:
        raise BackupValidationError("observation arguments are invalid")
    latencies: list[float] = []
    failures = 0
    wrong_slot = 0
    statuses: dict[str, int] = {}
    for _ in range(requests):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
                status = response.status
                slot = response.headers.get("X-Aurum-Release-Slot")
                response.read(1024)
        except (OSError, urllib.error.HTTPError):
            status = 0
            slot = None
        latencies.append((time.perf_counter() - started) * 1000)
        statuses[str(status)] = statuses.get(str(status), 0) + 1
        if not 200 <= status < 300:
            failures += 1
        if slot != expected_slot:
            wrong_slot += 1
    ordered = sorted(latencies)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    error_rate = failures / requests
    p95_ms = ordered[p95_index]
    return {
        "schema_version": SCHEMA_VERSION,
        "url": url,
        "expected_slot": expected_slot,
        "requests": requests,
        "accepted": error_rate < 0.01 and wrong_slot == 0 and p95_ms <= 1000,
        "error_rate": error_rate,
        "wrong_slot_count": wrong_slot,
        "p50_ms": statistics.median(ordered),
        "p95_ms": p95_ms,
        "statuses": statuses,
    }


def _prometheus_value(base_url: str, expression: str) -> float:
    query = urllib.parse.urlencode({"query": expression})
    url = f"{base_url.rstrip('/')}/api/v1/query?{query}"
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
        payload = json.load(response)
    results = payload.get("data", {}).get("result", [])
    if not results:
        return 0.0
    return float(results[0]["value"][1])


def collect_metrics(prometheus_url: str) -> dict[str, float]:
    return {
        "api_5xx_rate": _prometheus_value(
            prometheus_url,
            'sum(rate(aurum_api_requests_total{status=~"5.."}[5m])) '
            "/ clamp_min(sum(rate(aurum_api_requests_total[5m])), 0.001)",
        ),
        "model_error_rate": _prometheus_value(
            prometheus_url,
            'sum(rate(aurum_model_requests_total{outcome="error"}[5m]))',
        ),
        "queue_depth": _prometheus_value(prometheus_url, "max(aurum_ingestion_queue_depth)"),
        "database_pool_ratio": _prometheus_value(
            prometheus_url,
            'max(aurum_database_pool_connections{state="checked_out"}) '
            '/ clamp_min(max(aurum_database_pool_connections{state="size"}), 1)',
        ),
        "memory_embedding_error_rate": _prometheus_value(
            prometheus_url,
            'sum(rate(aurum_memory_embeddings_total{outcome="error"}[5m])) '
            "/ clamp_min(sum(rate(aurum_memory_embeddings_total[5m])), 0.001)",
        ),
        "memory_retrieval_p95_seconds": _prometheus_value(
            prometheus_url,
            "histogram_quantile(0.95, sum by (le) "
            '(rate(aurum_memory_retrieval_duration_seconds_bucket{mode=~"dense|text"}[5m])))',
        ),
    }


def decide(observation: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    thresholds = {
        "error_rate": 0.01,
        "p95_ms": 1000.0,
        "api_5xx_rate": 0.01,
        "model_error_rate": 0.01,
        "queue_depth": 20.0,
        "database_pool_ratio": 0.9,
        "memory_embedding_error_rate": 0.05,
        "memory_retrieval_p95_seconds": 1.0,
    }
    checks = {
        "http_error_rate": float(observation.get("error_rate", 1)) < thresholds["error_rate"],
        "slot_routing": int(observation.get("wrong_slot_count", 1)) == 0,
        "p95": float(observation.get("p95_ms", float("inf"))) <= thresholds["p95_ms"],
        "api_5xx": float(metrics.get("api_5xx_rate", float("inf"))) < thresholds["api_5xx_rate"],
        "model_errors": float(metrics.get("model_error_rate", float("inf")))
        < thresholds["model_error_rate"],
        "queue": float(metrics.get("queue_depth", float("inf"))) <= thresholds["queue_depth"],
        "database_pool": float(metrics.get("database_pool_ratio", float("inf")))
        < thresholds["database_pool_ratio"],
        "memory_embeddings": float(
            metrics.get("memory_embedding_error_rate", float("inf"))
        )
        < thresholds["memory_embedding_error_rate"],
        "memory_retrieval_p95": float(
            metrics.get("memory_retrieval_p95_seconds", float("inf"))
        )
        <= thresholds["memory_retrieval_p95_seconds"],
    }
    return {"accepted": all(checks.values()), "checks": checks, "thresholds": thresholds}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    manifest = subparsers.add_parser("manifest")
    manifest.add_argument("--release-id", required=True)
    manifest.add_argument("--mode", choices=["rehearsal", "production"], required=True)
    manifest.add_argument("--operator", required=True)
    manifest.add_argument("--candidate-slot", choices=sorted(SLOTS), required=True)
    manifest.add_argument("--api-image", required=True)
    manifest.add_argument("--web-image", required=True)
    manifest.add_argument("--migration-revision", required=True)
    manifest.add_argument("--backup-evidence")
    manifest.add_argument("--output", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--manifest", type=Path, required=True)
    activate = subparsers.add_parser("activate")
    activate.add_argument("--state-directory", type=Path, required=True)
    activate.add_argument("--slot", choices=sorted(SLOTS), required=True)
    activate.add_argument("--release-id", required=True)
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("--state-directory", type=Path, required=True)
    rollback.add_argument("--release-id", required=True)
    observation = subparsers.add_parser("observe")
    observation.add_argument("--url", required=True)
    observation.add_argument("--expected-slot", choices=sorted(SLOTS), required=True)
    observation.add_argument("--requests", type=int, default=20)
    observation.add_argument("--timeout", type=float, default=5)
    observation.add_argument("--output", type=Path, required=True)
    metrics = subparsers.add_parser("metrics")
    metrics.add_argument("--prometheus-url", required=True)
    metrics.add_argument("--output", type=Path, required=True)
    decision = subparsers.add_parser("decide")
    decision.add_argument("--observation", type=Path, required=True)
    decision.add_argument("--metrics", type=Path, required=True)
    decision.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "manifest":
            result = create_manifest(
                release_id=args.release_id,
                mode=args.mode,
                operator=args.operator,
                candidate_slot=args.candidate_slot,
                api_image=args.api_image,
                web_image=args.web_image,
                migration_revision=args.migration_revision,
                backup_evidence=args.backup_evidence,
            )
            write_json(args.output, result)
        elif args.command == "validate":
            result = read_json(args.manifest)
            validate_manifest(result)
        elif args.command == "activate":
            result = activate_slot(args.state_directory, args.slot, args.release_id)
        elif args.command == "rollback":
            result = rollback_slot(args.state_directory, args.release_id)
        elif args.command == "observe":
            result = observe(
                args.url,
                expected_slot=args.expected_slot,
                requests=args.requests,
                timeout=args.timeout,
            )
            write_json(args.output, result)
        elif args.command == "metrics":
            result = collect_metrics(args.prometheus_url)
            write_json(args.output, result)
        else:
            result = decide(read_json(args.observation), read_json(args.metrics))
            write_json(args.output, result)
    except (BackupValidationError, OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(json.dumps({"accepted": False, "error": type(exc).__name__, "detail": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("accepted", True) else 1


if __name__ == "__main__":
    sys.exit(main())
