"""运行无需模型和数据库的阶段五确定性回归评测。"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.agents.capabilities import (
    KNOWLEDGE_SEARCH_CAPABILITY,
    CapabilityRegistry,
    SemanticRangeInput,
    resolve_time_range,
)
from app.agents.policies.investment_risk import investment_risk_policy

DEFAULT_DATASET = Path(__file__).parents[1] / "evals" / "phase5-finance-agent.json"


def evaluate(dataset: dict[str, Any]) -> dict[str, Any]:
    """执行能力目录、服务端日期语义和拒绝用例，并返回机器可读结果。"""

    failures: list[dict[str, str]] = []
    passed = 0
    total = 0
    registry = CapabilityRegistry.read_only_default(
        finance_enabled=True,
        knowledge_enabled=True,
    )
    definitions = {item.name for item in registry.definitions()}

    for case in dataset["route_cases"]:
        total += 1
        expected_tools = set(case["tools"])
        knowledge_available = (
            not case["needs_knowledge"] or KNOWLEDGE_SEARCH_CAPABILITY in definitions
        )
        risk_policy_matches = (
            investment_risk_policy(case["question"]) == case["risk_policy"]
        )
        if expected_tools.issubset(definitions) and knowledge_available and risk_policy_matches:
            passed += 1
        else:
            failures.append(
                {
                    "id": case["id"],
                    "expected": str(sorted(expected_tools)),
                    "actual": str(sorted(definitions)),
                }
            )

    for case in dataset["time_cases"]:
        total += 1
        semantic_input = SemanticRangeInput.model_validate(case["input"])
        start, end = resolve_time_range(
            semantic_input,
            today=date.fromisoformat(case["today"]),
        )
        actual_range = (start.isoformat(), end.isoformat())
        expected_range = (case["start_date"], case["end_date"])
        if actual_range == expected_range:
            passed += 1
        else:
            failures.append(
                {
                    "id": case["id"],
                    "expected": str(expected_range),
                    "actual": str(actual_range),
                }
            )

    for case in dataset["rejection_cases"]:
        total += 1
        try:
            payload = case["payload"]
            registry.validate(payload["name"], payload["arguments"])
        except (ValidationError, ValueError):
            passed += 1
        else:
            failures.append(
                {"id": case["id"], "expected": "rejected", "actual": "accepted"}
            )

    pass_rate = passed / total if total else 0.0
    threshold = float(dataset["thresholds"]["deterministic_pass_rate"])
    return {
        "dataset_version": dataset["version"],
        "passed": passed,
        "total": total,
        "pass_rate": pass_rate,
        "threshold": threshold,
        "accepted": not failures and pass_rate >= threshold,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    result = evaluate(dataset)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
