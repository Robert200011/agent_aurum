"""运行版本化 P6.3 HTTP/SSE 负载配置并按锁定阈值判定。"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

ROOT = Path(__file__).parents[1]
DEFAULT_PROFILE = ROOT / "evals" / "load" / "local-smoke.json"
_ENV_PATTERN = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


@dataclass(frozen=True, slots=True)
class RequestSample:
    status_code: int | None
    duration_ms: float
    first_byte_ms: float | None
    server_error: bool
    network_error: bool
    leaked_marker: bool


async def run_profile(profile_path: Path, *, base_url: str | None) -> dict[str, Any]:
    profile = _load_json(profile_path)
    baseline_path = (profile_path.parent / _text(profile, "baseline_file")).resolve()
    baseline = _load_json(baseline_path)
    target = base_url or _resolve_required_environment(_text(profile, "base_url"))
    scenario_reports: dict[str, Any] = {}
    failures: list[dict[str, str]] = []
    started = perf_counter()
    timeout = httpx.Timeout(float(profile.get("request_timeout_seconds", 30)))
    async with httpx.AsyncClient(base_url=target, timeout=timeout) as client:
        metrics_before = await _metrics_snapshot(client, profile)
        for scenario in _list_of_dicts(profile, "scenarios"):
            scenario_id = _text(scenario, "id")
            resolved, missing = _resolve_scenario(scenario)
            if missing:
                required = bool(scenario.get("required", True))
                scenario_reports[scenario_id] = {
                    "skipped": True,
                    "required": required,
                    "missing_environment": sorted(missing),
                }
                if required:
                    failures.append(
                        {"id": scenario_id, "reason": f"missing environment: {sorted(missing)}"}
                    )
                continue
            scenario_started = perf_counter()
            samples = await _run_scenario(client, resolved)
            report = _scenario_report(
                samples,
                elapsed_seconds=perf_counter() - scenario_started,
            )
            scenario_reports[scenario_id] = report
            failures.extend(
                _scenario_failures(
                    scenario_id,
                    report,
                    thresholds=_mapping(profile, "thresholds"),
                    baseline=_mapping(baseline, "p95_ms"),
                )
            )
        metrics_after = await _metrics_snapshot(client, profile)
    resource_report, resource_failures = _resource_report(
        metrics_before,
        metrics_after,
        limits=_mapping(profile, "maximum_resource_growth"),
    )
    failures.extend(resource_failures)
    total_elapsed = max(0.000001, perf_counter() - started)
    total_requests = sum(
        int(report.get("request_count", 0)) for report in scenario_reports.values()
    )
    return {
        "schema_version": "p6.3-load-report-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": _text(profile, "name"),
        "profile_version": _text(profile, "version"),
        "baseline_version": _text(baseline, "version"),
        "target": target,
        "accepted": not failures,
        "elapsed_seconds": total_elapsed,
        "throughput_rps": total_requests / total_elapsed,
        "scenarios": scenario_reports,
        "resources": resource_report,
        "failures": failures,
    }


async def _metrics_snapshot(
    client: httpx.AsyncClient,
    profile: dict[str, Any],
) -> dict[str, float]:
    path = _text(profile, "metrics_path")
    response = await client.get(path)
    response.raise_for_status()
    prefixes = _string_list(profile, "observed_metric_prefixes")
    snapshot: dict[str, float] = {}
    for line in response.text.splitlines():
        if not line or line.startswith("#"):
            continue
        try:
            series, raw_value = line.rsplit(maxsplit=1)
            value = float(raw_value)
        except ValueError:
            continue
        if any(series.startswith(prefix) for prefix in prefixes):
            snapshot[series] = value
    return snapshot


def _resource_report(
    before: dict[str, float],
    after: dict[str, float],
    *,
    limits: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    changes: dict[str, dict[str, float]] = {}
    failures: list[dict[str, str]] = []
    for selector, raw_limit in limits.items():
        initial = _selected_metric_value(before, selector)
        final = _selected_metric_value(after, selector)
        growth = final - initial
        limit = float(raw_limit)
        changes[selector] = {"before": initial, "after": final, "growth": growth}
        if growth > limit:
            failures.append(
                {
                    "id": selector,
                    "reason": f"resource growth: {growth:.2f} > {limit:.2f}",
                }
            )
    return {
        "before": before,
        "after": after,
        "growth": changes,
    }, failures


def _selected_metric_value(snapshot: dict[str, float], selector: str) -> float:
    if selector in snapshot:
        return snapshot[selector]
    return sum(value for series, value in snapshot.items() if series.startswith(selector))


async def _run_scenario(
    client: httpx.AsyncClient, scenario: dict[str, Any]
) -> list[RequestSample]:
    request_count = int(scenario["requests"])
    concurrency = int(scenario["concurrency"])
    if request_count < 1 or concurrency < 1:
        raise ValueError("scenario requests and concurrency must be positive")
    semaphore = asyncio.Semaphore(concurrency)

    async def execute() -> RequestSample:
        async with semaphore:
            return await _request_once(client, scenario)

    return await asyncio.gather(*(execute() for _ in range(request_count)))


async def _request_once(
    client: httpx.AsyncClient, scenario: dict[str, Any]
) -> RequestSample:
    started = perf_counter()
    first_byte_ms: float | None = None
    status_code: int | None = None
    leaked = False
    try:
        request_kwargs: dict[str, Any] = {
            "headers": scenario.get("headers", {}),
        }
        if "json" in scenario:
            request_kwargs["json"] = scenario["json"]
        if "upload" in scenario:
            upload = _mapping(scenario, "upload")
            content_path = Path(_text(upload, "path"))
            content = await asyncio.to_thread(content_path.read_bytes)
            request_kwargs["files"] = {
                _text(upload, "field"): (
                    content_path.name,
                    content,
                    _text(upload, "content_type"),
                )
            }
            request_kwargs["data"] = upload.get("form", {})
        body_parts: list[bytes] = []
        async with client.stream(
            _text(scenario, "method"),
            _text(scenario, "path"),
            **request_kwargs,
        ) as response:
            status_code = response.status_code
            async for chunk in response.aiter_bytes():
                if first_byte_ms is None:
                    first_byte_ms = (perf_counter() - started) * 1000
                if sum(map(len, body_parts)) < 64_000:
                    body_parts.append(chunk)
        bounded_body = b"".join(body_parts).decode("utf-8", errors="replace")
        leaked = any(
            marker and marker in bounded_body
            for marker in _string_list(scenario, "forbidden_response_markers")
        )
        expected_statuses = [int(value) for value in scenario.get("expected_statuses", [200])]
        server_error = status_code >= 500 or status_code not in expected_statuses
        return RequestSample(
            status_code=status_code,
            duration_ms=(perf_counter() - started) * 1000,
            first_byte_ms=first_byte_ms,
            server_error=server_error,
            network_error=False,
            leaked_marker=leaked,
        )
    except (httpx.HTTPError, OSError):
        return RequestSample(
            status_code=status_code,
            duration_ms=(perf_counter() - started) * 1000,
            first_byte_ms=first_byte_ms,
            server_error=False,
            network_error=True,
            leaked_marker=False,
        )


def _scenario_report(samples: list[RequestSample], *, elapsed_seconds: float) -> dict[str, Any]:
    durations = sorted(sample.duration_ms for sample in samples)
    first_bytes = sorted(
        sample.first_byte_ms for sample in samples if sample.first_byte_ms is not None
    )
    count = len(samples)
    return {
        "request_count": count,
        "throughput_rps": count / max(0.000001, elapsed_seconds),
        "p50_ms": _percentile(durations, 0.50),
        "p95_ms": _percentile(durations, 0.95),
        "p99_ms": _percentile(durations, 0.99),
        "first_byte_p95_ms": _percentile(first_bytes, 0.95) if first_bytes else None,
        "server_error_rate": sum(sample.server_error for sample in samples) / count,
        "network_error_count": sum(sample.network_error for sample in samples),
        "cross_user_leak_count": sum(sample.leaked_marker for sample in samples),
        "statuses": _status_counts(samples),
    }


def _scenario_failures(
    scenario_id: str,
    report: dict[str, Any],
    *,
    thresholds: dict[str, Any],
    baseline: dict[str, Any],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if float(report["server_error_rate"]) >= float(thresholds["maximum_server_error_rate"]):
        failures.append({"id": scenario_id, "reason": "server error rate exceeded"})
    if int(report["network_error_count"]) > int(thresholds["maximum_network_errors"]):
        failures.append({"id": scenario_id, "reason": "network error limit exceeded"})
    if int(report["cross_user_leak_count"]) > int(
        thresholds["maximum_cross_user_leak_count"]
    ):
        failures.append({"id": scenario_id, "reason": "cross-user marker leaked"})
    baseline_p95 = baseline.get(scenario_id)
    if isinstance(baseline_p95, (int, float)):
        maximum = float(baseline_p95) * float(thresholds["maximum_p95_regression_ratio"])
        if float(report["p95_ms"]) > maximum:
            failures.append(
                {
                    "id": scenario_id,
                    "reason": f"p95 regression: {report['p95_ms']:.2f}ms > {maximum:.2f}ms",
                }
            )
    return failures


def _resolve_scenario(scenario: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    missing: set[str] = set()

    def resolve(value: Any) -> Any:
        if isinstance(value, str):
            def replace(match: re.Match[str]) -> str:
                name = match.group(1)
                resolved = os.environ.get(name)
                if resolved is None:
                    missing.add(name)
                    return match.group(0)
                return resolved

            return _ENV_PATTERN.sub(replace, value)
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        return value

    return resolve(scenario), missing


def _resolve_required_environment(value: str) -> str:
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = os.environ.get(name)
        if resolved is None:
            missing.add(name)
            return match.group(0)
        return resolved

    result = _ENV_PATTERN.sub(replace, value)
    if missing:
        raise ValueError(f"missing environment: {sorted(missing)}")
    return result


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = max(0, math.ceil(len(values) * quantile) - 1)
    return values[index]


def _status_counts(samples: list[RequestSample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        key = str(sample.status_code) if sample.status_code is not None else "network_error"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _load_json(path: Path) -> dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"{path} must contain an object")
    return decoded


def _mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise ValueError(f"{key} must be an object")
    return result


def _list_of_dicts(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
    result = value.get(key)
    if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
        raise ValueError(f"{key} must be an array of objects")
    return result


def _text(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str):
        raise ValueError(f"{key} must be a string")
    return result


def _string_list(value: dict[str, Any], key: str) -> list[str]:
    result = value.get(key, [])
    if not isinstance(result, list) or not all(isinstance(item, str) for item in result):
        raise ValueError(f"{key} must be an array of strings")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--base-url")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = asyncio.run(run_profile(args.profile, base_url=args.base_url))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
