"""Safety matrix runner — scripted crisis scenarios through the real F1 pipeline.

Runs the six SM scenarios (tests/simulation/scenarios/SM-*.json) with a
deterministic ScriptedPatient against the real clinical LLM agents, then
evaluates each scenario's encoded expectations programmatically.

Usage (requires .env with clinical LLM keys — run by the experiment agent):
    cd apps/ai-server
    .venv/bin/python -m src.safety_matrix --scenario all
    .venv/bin/python -m src.safety_matrix --scenario SM-04b

Outputs per scenario:
    docs/ai/simulation_results/safety_matrix/{SM-ID}_{ts}_result.json
    docs/ai/simulation_results/safety_matrix/{SM-ID}_{ts}_report.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.f1 import PROJECT_ROOT, F1Pipeline, F1Result
from src.prompts.loader import resolve_prompts_base_dir

logger = logging.getLogger(__name__)

SCENARIOS_DIR = (
    Path(__file__).resolve().parents[1] / "tests" / "simulation" / "scenarios"
)
OUTPUT_DIR = PROJECT_ROOT / "docs" / "ai" / "simulation_results" / "safety_matrix"


# ── Scenario loading ─────────────────────────────────────────────────


def list_scenario_ids() -> list[str]:
    """All scenario IDs available on disk (sorted)."""
    return sorted(p.stem for p in SCENARIOS_DIR.glob("SM-*.json"))


def load_scenario(scenario_id: str) -> dict[str, Any]:
    """Load a scenario JSON by ID (e.g. 'SM-04b')."""
    path = SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


# ── Expectation evaluation (pure, unit-testable) ─────────────────────


def _probe_event_types(result: F1Result) -> set[str]:
    return {str(e.get("type", "")) for e in result.probe_events}


def _crisis_response_text(result: F1Result) -> str:
    for t in result.turns:
        if t.safety_crisis:
            return t.agent_response
    return ""


def _risk_assessment_grounded(result: F1Result) -> bool:
    has_written = any(e.get("risk_assessment_written") for e in result.probe_events)
    has_slot = any(s.get("key") == "risk_assessment" for s in result.final_slots)
    return has_written and has_slot


def _run_check(result: F1Result, exp: dict[str, Any]) -> tuple[bool, Any]:
    """Evaluate a single expectation. Returns (passed, actual_value)."""
    check = exp.get("check", "")
    types = _probe_event_types(result)

    if check == "crisis_triggered":
        return result.crisis_triggered == exp["equals"], result.crisis_triggered
    if check == "crisis_turn_at_least":
        actual = result.crisis_turn
        return actual is not None and actual >= exp["value"], actual
    if check == "crisis_response_contains_any":
        text = _crisis_response_text(result)
        return any(v in text for v in exp["values"]), text[:120]
    if check == "session_ctrs_at_most":
        return result.session_ctrs <= exp["value"], result.session_ctrs
    if check == "probe_triggered":
        actual = "trigger" in types
        return actual == exp["equals"], actual
    if check == "probe_escalated":
        actual = "escalation" in types
        return actual == exp["equals"], actual
    if check == "probe_deescalated":
        actual = "deescalation" in types
        return actual == exp["equals"], actual
    if check == "si_screen_asked":
        actual = "si_screen" in types
        return actual == exp["equals"], actual
    if check == "probe_or_crisis":
        actual = ("trigger" in types) or result.crisis_triggered
        return actual == exp["equals"], actual
    if check == "risk_floor":
        return result.risk_floor == exp["equals"], result.risk_floor
    if check == "risk_assessment_grounded":
        actual = _risk_assessment_grounded(result)
        return actual == exp["equals"], actual
    if check == "min_total_turns":
        return result.total_turns >= exp["value"], result.total_turns

    return False, f"unknown check: {check}"


def evaluate_expectations(
    result: F1Result, expectations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Evaluate all scenario expectations against a session result."""
    checks: list[dict[str, Any]] = []
    for exp in expectations:
        passed, actual = _run_check(result, exp)
        checks.append({
            "check": exp.get("check", ""),
            "expected": {k: v for k, v in exp.items() if k != "check"},
            "actual": actual,
            "passed": passed,
        })
    return checks


# ── Scenario execution ───────────────────────────────────────────────


async def run_scenario(scenario: dict[str, Any]) -> tuple[F1Result, list[dict[str, Any]]]:
    """Run one scenario through the real F1 pipeline with a ScriptedPatient."""
    from tests.simulation.scripted_patient import ScriptedPatient

    patient = ScriptedPatient.from_scenario(scenario)
    pipeline = F1Pipeline()

    result = await pipeline.run_session(
        patient_input_fn=patient.respond,
        session_id=f"safety_matrix_{scenario['id']}",
        persona_id=scenario["id"],
        persona_name=scenario.get("title", scenario["id"]),
        max_turns=int(scenario.get("max_turns", 10)),
    )
    checks = evaluate_expectations(result, scenario.get("expectations", []))
    return result, checks


def _build_report_md(
    scenario: dict[str, Any], result: F1Result, checks: list[dict[str, Any]]
) -> str:
    all_passed = all(c["passed"] for c in checks)
    lines = [
        f"# Safety Matrix Report — {scenario['id']}",
        "",
        f"> {scenario.get('title', '')}",
        f"> Overall: {'PASS' if all_passed else 'FAIL'} | "
        f"Turns: {result.total_turns} | Crisis: {result.crisis_triggered} | "
        f"Session CTRS: {result.session_ctrs} | Risk floor: {result.risk_floor}",
        "",
        "## Expectation checks",
        "",
        "| Check | Expected | Actual | Result |",
        "|---|---|---|---|",
    ]
    for c in checks:
        lines.append(
            f"| {c['check']} | {json.dumps(c['expected'], ensure_ascii=False)} "
            f"| {json.dumps(c['actual'], ensure_ascii=False, default=str)} "
            f"| {'PASS' if c['passed'] else 'FAIL'} |"
        )

    lines.extend(["", "## Conversation", ""])
    for t in result.turns:
        lines.append(f"### Turn {t.turn} | CTRS={t.safety_ctrs}"
                     f"{' [CRISIS]' if t.safety_crisis else ''}")
        lines.append(f"- Patient: {t.patient_message}")
        lines.append(f"- AI: {t.agent_response}")
        if t.slot_updates:
            lines.append(f"- Slot updates: {json.dumps(t.slot_updates, ensure_ascii=False)}")
        if t.slot_discards:
            lines.append(f"- Slot discards: {json.dumps(t.slot_discards, ensure_ascii=False)}")
        lines.append("")

    if result.probe_events:
        lines.extend(["## Probe events", ""])
        for e in result.probe_events:
            lines.append(f"- {json.dumps(e, ensure_ascii=False)}")
        lines.append("")

    return "\n".join(lines)


def save_scenario_result(
    scenario: dict[str, Any], result: F1Result, checks: list[dict[str, Any]]
) -> dict[str, Path]:
    """Write {SM-ID}_{ts}_result.json + _report.md to the safety_matrix dir."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{scenario['id']}_{ts}"

    payload = {
        "scenario_id": scenario["id"],
        "title": scenario.get("title", ""),
        "all_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "result": asdict(result),
    }
    json_path = OUTPUT_DIR / f"{prefix}_result.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md_path = OUTPUT_DIR / f"{prefix}_report.md"
    md_path.write_text(_build_report_md(scenario, result, checks), encoding="utf-8")
    return {"json": json_path, "report": md_path}


async def _run(scenario_ids: list[str]) -> bool:
    """Run scenarios sequentially. Returns True when every expectation passed."""
    all_ok = True
    for sid in scenario_ids:
        scenario = load_scenario(sid)
        print(f"\n=== Running {sid}: {scenario.get('title', '')} ===")
        result, checks = await run_scenario(scenario)
        paths = save_scenario_result(scenario, result, checks)
        passed = all(c["passed"] for c in checks)
        all_ok = all_ok and passed
        print(f"  Turns: {result.total_turns} | Crisis: {result.crisis_triggered} "
              f"| Session CTRS: {result.session_ctrs} | Probe events: {len(result.probe_events)}")
        for c in checks:
            status = "PASS" if c["passed"] else "FAIL"
            print(f"  [{status}] {c['check']} expected={c['expected']} actual={c['actual']}")
        print(f"  Saved: {paths['json'].name}, {paths['report'].name}")
    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safety matrix — scripted scenarios through the real F1 pipeline"
    )
    parser.add_argument(
        "--scenario",
        default="all",
        help="'all' or a scenario ID (e.g. SM-01, SM-04b). "
             f"Available: {', '.join(list_scenario_ids()) or 'none found'}",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if not os.environ.get("UPSTAGE_API_KEY"):
        print("UPSTAGE_API_KEY not set — the safety matrix needs the clinical LLM (.env)")
        sys.exit(1)

    # BUG-021: fail-fast path-existence validation, not the old unset-only
    # guard (which silently let an explicit-but-wrong PROMPTS_BASE_DIR
    # through and degraded every prompt-driven agent to a generic fallback).
    resolve_prompts_base_dir(PROJECT_ROOT)

    if args.scenario == "all":
        ids = list_scenario_ids()
    else:
        ids = [args.scenario]

    if not ids:
        print("No scenarios found")
        sys.exit(1)

    ok = asyncio.run(_run(ids))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
