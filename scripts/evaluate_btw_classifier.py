"""Reproduce R4 contract replay or opt-in live trials without executing any tools."""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime_bootstrap import initialize_runtime_bootstrap  # noqa: E402

initialize_runtime_bootstrap()

from astrbot.core.agent.btw.classifier import (  # noqa: E402
    FALLBACK_PROMPT,
    ROUTING_QUESTION,
    classify_request,
    routing_state,
)
from astrbot.core.agent.llm_types import LLMResponse  # noqa: E402
from astrbot.core.provider.provider import ClassifierProvider, Provider  # noqa: E402
from astrbot.core.typed_decision import ClassifierResult  # noqa: E402


def replay_providers(contract: dict):
    """Replay independently stored wire decisions, never infer intent from labels."""
    classifier = MagicMock(spec=ClassifierProvider)
    classifier.get_model.return_value = "fixture-only"
    choice = contract["jev"]
    if choice in ("error", "absent"):
        classifier.evaluate = AsyncMock(side_effect=RuntimeError("fixture failure"))
    else:
        result = ClassifierResult.model_validate(
            {
                "model": "fixture-only",
                "answers": {
                    "route": {
                        "type": "choice",
                        "choice": choice,
                        "confidence": contract["confidence"],
                        "probabilities": {
                            key: 1.0 if key == choice else 0.0
                            for key in ROUTING_QUESTION.criteria
                        },
                    }
                },
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        )
        classifier.evaluate = AsyncMock(return_value=result)
    fallback = None
    if contract["fallback"] is not None:
        fallback = MagicMock(spec=Provider)
        fallback.get_model.return_value = "fixture-only"
        fallback.text_chat = AsyncMock(
            return_value=LLMResponse(
                role="assistant", completion_text=json.dumps(contract["fallback"])
            )
        )
    return None if choice == "absent" else classifier, fallback


def evaluation_metrics(rows: list[dict], *, live: bool) -> dict:
    """Keep model quality and execution outcomes distinct from contract replay."""
    attempts = [attempt for row in rows for attempt in row["attempts"]]
    expected_work = sum(row["expected"] == "work" for row in rows)
    missed = sum(
        row["expected"] == "work" and row["decision"] != "work" for row in rows
    )
    decisions: dict[str, set[str]] = {}
    for row in rows:
        decisions.setdefault(row["case"], set()).add(row["decision"])
    return {
        "rows": len(rows),
        "contract_failures": None
        if live
        else sum(not row["matches_expected"] for row in rows),
        "accuracy": mean(row["matches_expected"] for row in rows) if live else None,
        "false_handoffs": sum(
            row["expected"] != "work" and row["decision"] == "work" for row in rows
        )
        if live
        else None,
        "missed_handoffs": missed if live else None,
        "missed_handoff_rate": missed / expected_work
        if live and expected_work
        else None,
        "cases_with_decision_variation": sum(
            len(values) > 1 for values in decisions.values()
        )
        if live
        else None,
        "mean_routing_latency_ms": mean(
            sum(a["latency_ms"] for a in row["attempts"]) for row in rows
        ),
        "provider_calls": len(attempts),
        "successful_model_calls": sum(
            a["status"] in ("ok", "low_confidence") for a in attempts
        )
        if live
        else 0,
        "input_tokens": sum(
            a.get("usage", {}).get("input_tokens", 0) for a in attempts
        ),
        "output_tokens": sum(
            a.get("usage", {}).get("output_tokens", 0) for a in attempts
        ),
        "task_completion": None,
        "clarification_quality": None,
        "duplicate_side_effects": None,
        "execution_note": "Routing only; tools are never executed. Execution outcomes require separate supervised trials.",
    }


async def evaluate(args) -> dict:
    data_bytes = args.dataset.read_bytes()
    dataset = json.loads(data_bytes)
    cases = {case["id"]: case for case in dataset["cases"]}
    contracts = (
        json.loads(args.contracts.read_text()) if args.mode == "contract" else []
    )
    classifier = fallback = None
    if args.mode == "live":
        from astrbot.core.provider.sources.jev_systemone_source import (
            JevSystemOneProvider,
        )

        key = os.getenv("TYPESAFE_API_KEY")
        if not key:
            raise ValueError("Live trials require TYPESAFE_API_KEY in the environment")
        classifier = JevSystemOneProvider({"key": [key], "model": args.model}, {})
    rows = []
    try:
        if args.mode == "live" and args.fallback_model:
            from astrbot.core.provider.sources.openai_chat_completions_source import (
                ProviderOpenAIChatCompletions,
            )

            key = os.getenv("BTW_FALLBACK_API_KEY")
            if not key or not args.fallback_api_base:
                raise ValueError(
                    "A live fallback requires BTW_FALLBACK_API_KEY and --fallback-api-base"
                )
            fallback = ProviderOpenAIChatCompletions(
                {
                    "id": "evaluation-fallback",
                    "type": "openai_chat_completions",
                    "key": [key],
                    "model": args.fallback_model,
                    "api_base": args.fallback_api_base,
                    "timeout": 20,
                },
                {},
            )
        entries = (
            [(cases[item["case"]], item) for item in contracts]
            if contracts
            else [(case, None) for case in cases.values()]
        )
        for repeat in range(args.repeats):
            for case, contract in entries:
                state = routing_state(
                    case["message"],
                    dataset["capability_fixtures"][case["capability_fixture"]],
                )
                providers = (
                    replay_providers(contract) if contract else (classifier, fallback)
                )
                if case["message"].startswith("/work "):
                    result = {
                        "decision": "work",
                        "source": "explicit",
                        "confidence": 1.0,
                        "attempts": [],
                    }
                else:
                    result = asdict(
                        await classify_request(
                            state, *providers, confidence_threshold=args.threshold
                        )
                    )
                expected = contract["expected"] if contract else case["expected"]
                rows.append(
                    {
                        "case": case["id"],
                        "repeat": repeat,
                        "expected": expected,
                        "control_decision": "work"
                        if case["message"].startswith("/work ")
                        else "conversation",
                        **result,
                        "matches_expected": result["decision"] == expected,
                    }
                )
    finally:
        if classifier is not None:
            await classifier.terminate()
        if fallback is not None:
            await fallback.terminate()
    metrics = evaluation_metrics(rows, live=args.mode == "live")
    metrics["jev_token_cost_usd"] = None
    if (
        args.input_price is not None
        and args.output_price is not None
        and args.mode == "live"
    ):
        usage = [
            a.get("usage", {})
            for row in rows
            for a in row["attempts"]
            if a["source"] == "classifier"
        ]
        metrics["jev_token_cost_usd"] = (
            sum(
                u.get("input_tokens", 0) * args.input_price
                + u.get("output_tokens", 0) * args.output_price
                for u in usage
            )
            / 1_000_000
        )
    return {
        "mode": args.mode,
        "measured_at": datetime.now(UTC).isoformat(),
        "baseline_commit": dataset["baseline_commit"],
        "implementation_commit": (
            await asyncio.to_thread(
                subprocess.check_output,
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                text=True,
            )
        ).strip(),
        "working_tree_dirty": bool(
            await asyncio.to_thread(
                subprocess.check_output,
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                text=True,
            )
        ),
        "dataset_sha256": hashlib.sha256(data_bytes).hexdigest(),
        "contracts_sha256": hashlib.sha256(args.contracts.read_bytes()).hexdigest()
        if contracts
        else None,
        "model_requested": args.model if args.mode == "live" else "fixture-only",
        "prompt": ROUTING_QUESTION.model_dump(),
        "fallback_prompt": FALLBACK_PROMPT,
        "parameters": {
            "threshold": args.threshold,
            "repeats": args.repeats,
            "fallback_temperature": 0,
            "fallback_model": args.fallback_model,
        },
        "acceptance_thresholds": dataset["acceptance_thresholds"],
        "metrics": metrics,
        "cases": rows,
        "limitations": "Contract replay does not measure model accuracy. Latency excludes tool execution. Missing/failed response usage and retry billing are unknown; fallback pricing is not included. The shared corpus and thresholds await parent comparison approval.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("contract", "live"), default="contract")
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "tests/fixtures/btw_routing/v1.json"
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        default=ROOT / "tests/fixtures/btw_routing/contracts.json",
    )
    parser.add_argument("--model", default="jev-1.13.0")
    parser.add_argument("--fallback-model")
    parser.add_argument("--fallback-api-base")
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--input-price", type=float, help="JEV USD per million input tokens"
    )
    parser.add_argument(
        "--output-price", type=float, help="JEV USD per million output tokens"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1 or not 0 <= args.threshold <= 1:
        parser.error("repeats must be positive and threshold must be in [0,1]")
    report = asyncio.run(evaluate(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False))
    if report["metrics"]["contract_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
