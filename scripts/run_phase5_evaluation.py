"""运行无需模型和数据库的阶段五确定性回归评测。"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.agents.policies.finance_planner import plan_agent_question
from app.agents.tools.finance import FinanceToolRequest
from app.finance.time_ranges import parse_date_range

DEFAULT_DATASET = Path(__file__).parents[1] / "evals" / "phase5-finance-agent.json"


def evaluate(dataset: dict[str, Any]) -> dict[str, Any]:
    """执行路由、日期和契约拒绝用例，并返回机器可读结果。"""

    failures: list[dict[str, str]] = []
    passed = 0
    total = 0
    reference_date = date.fromisoformat(dataset["reference_date"])

    for case in dataset["route_cases"]:
        total += 1
        plan = plan_agent_question(case["question"], today=reference_date)
        actual = {
            "intent": plan.intent,
            "needs_knowledge": plan.needs_knowledge,
            "risk_policy": plan.risk_policy,
            "tools": [request.name.value for request in plan.finance_calls],
            "requires_clarification": plan.clarification is not None,
        }
        expected = {
            "intent": case["intent"],
            "needs_knowledge": case["needs_knowledge"],
            "risk_policy": case["risk_policy"],
            "tools": case["tools"],
            "requires_clarification": case.get("requires_clarification", False),
        }
        if actual == expected:
            passed += 1
        else:
            failures.append(
                {"id": case["id"], "expected": str(expected), "actual": str(actual)}
            )

    for case in dataset["time_cases"]:
        total += 1
        parsed = parse_date_range(case["question"], today=date.fromisoformat(case["today"]))
        actual_range = (
            (parsed.start_date.isoformat(), parsed.end_date.isoformat())
            if parsed is not None
            else None
        )
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

    adapter: TypeAdapter[FinanceToolRequest] = TypeAdapter(FinanceToolRequest)
    for case in dataset["rejection_cases"]:
        total += 1
        try:
            adapter.validate_python(case["payload"])
        except ValidationError:
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
