"""统一运行阶段五、P6.3 RAG、安全与故障场景回归门禁。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.graph import RAG_GRAPH_VERSION
from app.agents.policies.rag_prompt import SYSTEM_PROMPT
from app.evaluation.phase6 import (
    evaluate_fault_dataset,
    evaluate_rag_dataset,
    evaluate_security_dataset,
)

if __package__:
    from scripts.run_phase5_evaluation import evaluate as evaluate_phase5
else:
    from run_phase5_evaluation import evaluate as evaluate_phase5

ROOT = Path(__file__).parents[1]
DEFAULT_PHASE5 = ROOT / "evals" / "phase5-finance-agent.json"
DEFAULT_RAG = ROOT / "evals" / "phase6-rag-regression.json"
DEFAULT_SECURITY = ROOT / "evals" / "phase6-prompt-injection.json"
DEFAULT_FAULTS = ROOT / "evals" / "phase6-fault-scenarios.json"
_CANDIDATE_FIELDS = {
    "environment",
    "chat_provider",
    "chat_model",
    "embedding_provider",
    "embedding_model",
    "reranker_provider",
    "reranker_model",
    "provider_smoke_passed",
    "memory_smoke_passed",
}


def run_gate(
    *,
    phase5_path: Path,
    rag_path: Path,
    security_path: Path,
    faults_path: Path,
    mode: str,
    candidate_evidence_path: Path | None,
    verify_fault_checks: bool,
) -> dict[str, Any]:
    """运行所有确定性套件，并生成不包含数据集正文的机器报告。"""

    phase5 = _load_json(phase5_path)
    rag = _load_json(rag_path)
    security = _load_json(security_path)
    faults = _load_json(faults_path)
    suites = {
        "phase5_finance_agent": evaluate_phase5(phase5),
        "phase6_rag_regression": evaluate_rag_dataset(rag),
        "phase6_prompt_injection": evaluate_security_dataset(security),
        "phase6_fault_scenarios": evaluate_fault_dataset(faults),
    }
    fault_pytest = (
        _run_fault_checks(faults)
        if verify_fault_checks
        else {"accepted": True, "skipped": True, "reason": "disabled by caller"}
    )
    candidate_evidence = _candidate_evidence(mode, candidate_evidence_path)
    accepted = all(bool(result["accepted"]) for result in suites.values())
    accepted = accepted and bool(fault_pytest["accepted"])
    if mode == "candidate":
        accepted = (
            accepted
            and bool(candidate_evidence["provider_smoke_passed"])
            and bool(candidate_evidence["memory_smoke_passed"])
        )
    paths = (phase5_path, rag_path, security_path, faults_path)
    return {
        "schema_version": "p6.3-gate-report-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "accepted": accepted,
        "git_revision": _git_revision(),
        "implementation": {
            "rag_graph_version": RAG_GRAPH_VERSION,
            "system_prompt_sha256": hashlib.sha256(
                SYSTEM_PROMPT.encode("utf-8")
            ).hexdigest(),
        },
        "datasets": {
            path.name: {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "version": _load_json(path)["version"],
            }
            for path in paths
        },
        "candidate_evidence": candidate_evidence,
        "suites": suites,
        "fault_pytest": fault_pytest,
    }


def _run_fault_checks(dataset: dict[str, Any]) -> dict[str, Any]:
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        raise ValueError("fault cases must be an array")
    node_ids = [case["automated_check"] for case in cases if isinstance(case, dict)]
    if not all(isinstance(node_id, str) for node_id in node_ids):
        raise ValueError("fault automated_check values must be strings")
    completed = subprocess.run(  # noqa: S603 - node IDs are passed as argv, never a shell.
        [sys.executable, "-m", "pytest", *node_ids, "-q"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout + completed.stderr).strip()
    return {
        "accepted": completed.returncode == 0,
        "exit_code": completed.returncode,
        "check_count": len(node_ids),
        "output_tail": output[-2_000:],
    }


def _candidate_evidence(mode: str, path: Path | None) -> dict[str, Any]:
    if mode == "pr":
        return {
            "required": False,
            "provider_smoke_passed": False,
            "memory_smoke_passed": False,
        }
    if path is None:
        raise ValueError("candidate mode requires --candidate-evidence")
    evidence = _load_json(path)
    missing = sorted(_CANDIDATE_FIELDS - evidence.keys())
    unknown = sorted(evidence.keys() - _CANDIDATE_FIELDS)
    if missing or unknown:
        raise ValueError(
            f"candidate evidence fields invalid; missing={missing}, unknown={unknown}"
        )
    boolean_fields = {"provider_smoke_passed", "memory_smoke_passed"}
    if any(not isinstance(evidence[field], bool) for field in boolean_fields):
        raise ValueError("candidate smoke fields must be boolean")
    if any(
        not isinstance(value, str) or not value.strip()
        for key, value in evidence.items()
        if key not in boolean_fields
    ):
        raise ValueError("candidate model metadata must be non-empty strings")
    return evidence


def _load_json(path: Path) -> dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return decoded


def _git_revision() -> str | None:
    completed = subprocess.run(  # noqa: S603 - fixed read-only Git command.
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    revision = completed.stdout.strip()
    return revision if completed.returncode == 0 and revision else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase5-dataset", type=Path, default=DEFAULT_PHASE5)
    parser.add_argument("--rag-dataset", type=Path, default=DEFAULT_RAG)
    parser.add_argument("--security-dataset", type=Path, default=DEFAULT_SECURITY)
    parser.add_argument("--fault-dataset", type=Path, default=DEFAULT_FAULTS)
    parser.add_argument("--mode", choices=("pr", "candidate"), default="pr")
    parser.add_argument("--candidate-evidence", type=Path)
    parser.add_argument("--skip-fault-pytest", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run_gate(
            phase5_path=args.phase5_dataset,
            rag_path=args.rag_dataset,
            security_path=args.security_dataset,
            faults_path=args.fault_dataset,
            mode=args.mode,
            candidate_evidence_path=args.candidate_evidence,
            verify_fault_checks=not args.skip_fault_pytest,
        )
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
