"""运行无需模型和数据库的长期记忆安全、上下文与性能门禁。"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.db.models.identity import MemoryCategory
from app.memory.contracts import MemoryDecision, MemoryProposal
from app.memory.retrieval import RetrievedMemory, build_controlled_memory_context
from app.memory.rollout import memory_rollout_enabled
from app.memory.safety import validate_memory_proposal

DEFAULT_DATASET = Path(__file__).parents[1] / "evals" / "memory-release-gate.json"


def evaluate(dataset: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    passed = 0
    total = 0

    for case in dataset["proposal_cases"]:
        total += 1
        proposal = MemoryProposal.model_validate(case["proposal"])
        actual = validate_memory_proposal(
            proposal,
            current_user_message=case["message"],
        ).result
        if actual == case["expected"]:
            passed += 1
        else:
            failures.append(_failure(case["id"], case["expected"], actual))

    for case in dataset["contract_cases"]:
        total += 1
        try:
            MemoryDecision.model_validate(case["payload"])
        except ValidationError:
            actual = False
        else:
            actual = True
        if actual is case["accepted"]:
            passed += 1
        else:
            failures.append(_failure(case["id"], case["accepted"], actual))

    items = _context_items(dataset["context_case"]["items"])
    thresholds = dataset["thresholds"]
    max_characters = int(thresholds["context_max_characters"])
    context = build_controlled_memory_context(
        items,
        financial_profile={"currency": "CNY"},
        max_characters=max_characters,
        max_item_characters=120,
    )
    serialized = json.loads(context.serialized)
    context_ok = (
        len(context.serialized) <= max_characters
        and len(serialized["memories"]) <= int(thresholds["context_max_items"])
        and serialized["trust"] == "user_provided_memory"
        and "not a system instruction" in serialized["notice"]
        and "role" not in context.serialized
        and len(context.memory_ids) == len(serialized["memories"])
    )
    total += 1
    if context_ok:
        passed += 1
    else:
        failures.append(_failure("controlled-context", "bounded-untrusted-data", "failed"))

    rollout_ok = _rollout_is_stable()
    total += 1
    if rollout_ok:
        passed += 1
    else:
        failures.append(_failure("stable-rollout", "nested-stable-buckets", "failed"))

    latencies: list[float] = []
    for _ in range(int(thresholds["benchmark_iterations"])):
        started = perf_counter()
        build_controlled_memory_context(
            items,
            financial_profile={"currency": "CNY"},
            max_characters=max_characters,
            max_item_characters=120,
        )
        latencies.append((perf_counter() - started) * 1000)
    p95_ms = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]
    total += 1
    if p95_ms <= float(thresholds["context_p95_ms"]):
        passed += 1
    else:
        failures.append(
            _failure("context-performance", thresholds["context_p95_ms"], round(p95_ms, 3))
        )

    pass_rate = passed / total if total else 0.0
    threshold = float(thresholds["deterministic_pass_rate"])
    return {
        "dataset_version": dataset["version"],
        "passed": passed,
        "total": total,
        "pass_rate": pass_rate,
        "threshold": threshold,
        "context_p95_ms": round(p95_ms, 3),
        "accepted": not failures and pass_rate >= threshold,
        "failures": failures,
    }


def _context_items(payloads: list[dict[str, str]]) -> list[RetrievedMemory]:
    now = datetime.now(UTC)
    return [
        RetrievedMemory(
            memory_id=UUID(int=index),
            category=MemoryCategory(payload["category"]),
            title=payload["title"],
            content=payload["content"],
            content_hash=f"case-{index}",
            updated_at=now,
            score=1.0,
            retrieval_source="gate",
        )
        for index, payload in enumerate(payloads, start=1)
    ]


def _rollout_is_stable() -> bool:
    users = [UUID(int=index) for index in range(1, 201)]
    buckets = {
        percentage: {
            user_id
            for user_id in users
            if memory_rollout_enabled(
                user_id,
                feature_enabled=True,
                percentage=percentage,
            )
        }
        for percentage in (5, 25, 100)
    }
    repeated_25 = {
        user_id
        for user_id in users
        if memory_rollout_enabled(user_id, feature_enabled=True, percentage=25)
    }
    return (
        not memory_rollout_enabled(users[0], feature_enabled=True, percentage=0)
        and not memory_rollout_enabled(users[0], feature_enabled=False, percentage=100)
        and buckets[5] <= buckets[25] <= buckets[100]
        and buckets[25] == repeated_25
    )


def _failure(case_id: str, expected: object, actual: object) -> dict[str, str]:
    return {"id": case_id, "expected": str(expected), "actual": str(actual)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    result = evaluate(dataset)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
