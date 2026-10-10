"""Run one real simulation and report LLM calls, tokens and time per run (ticket B1).

Usage: uv run python scripts/measure_run.py [--model ilmu:ilmu-mini-v3.3 | gemini:gemini-3.5-flash] [--men 5] [--days 3]
"""
from __future__ import annotations

import argparse
import json
import time

from dotenv import load_dotenv

from garden import Twin, WorldConfig, run_world
from garden.concordia_twins import ConcordiaTwins
from garden.llm import make_model

# Placeholder personas until D1 builds twins from the speed-dating data.
PERSONAS = {
    "Mara": "I'm a nurse. I follow rules, but I'll bend them for people I love.\nI want a home and a family one day.",
    "Ren": "I'm an engineer. I own my mistakes, even when it costs me.\nFamily dinners matter to me.",
    "Jun": "I love travel and freedom. I keep my options open.",
    "Theo": "I'm kind and steady. I want to live out of a backpack, no kids.",
    "Kai": "I like order. I avoid arguments and never break rules.",
    "Sam": "When I fall for someone, I fall hard. I get jealous easily.",
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=None, help="provider:model; defaults to TWIN_MODEL, then Gemini Flash")
    p.add_argument("--men", type=int, default=5)
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    load_dotenv(".env")
    names = ["Mara", *list(PERSONAS)[1 : 1 + args.men]]
    lm = make_model(args.model)
    model = ConcordiaTwins(lm, {n: PERSONAS[n] for n in names})

    start = time.perf_counter()
    twins = tuple(Twin(n, "f" if n == "Mara" else "m") for n in names)
    result = run_world(WorldConfig(twins, max_days=args.days, seed=args.seed), model)
    wall = time.perf_counter() - start

    actions = len(result.events)
    stats = lm.stats.as_dict()
    per_action_calls = stats["text_calls"] / actions
    # Project from model time, not wall time: on a rate-limited key, wall time is mostly waiting.
    per_action_seconds = stats["model_seconds"] / actions
    demo_actions = len(names) * 10  # 10-day demo run
    report = {
        "model": args.model or "(TWIN_MODEL or default)",
        "twins": len(names),
        "days_run": result.day,
        "outcome": result.outcome.value,
        "pair": result.pair,
        "unrequited": len(result.unrequited),
        "actions": actions,
        **stats,
        "wall_seconds": round(wall, 1),
        "calls_per_action": round(per_action_calls, 2),
        "seconds_per_action": round(per_action_seconds, 1),
        "projected_10_day_run": {
            "calls": round(per_action_calls * demo_actions),
            "minutes_sequential": round(per_action_seconds * demo_actions / 60, 1),
            "minutes_if_twins_act_in_parallel_each_day": round(per_action_seconds * 10 / 60, 1),
        },
        "rungs": {r: sum(e.rung.value == r for e in result.events) for r in sorted({e.rung.value for e in result.events})},
        "sample_lines": [f"Day {e.day} {e.twin} -> {e.target}: {e.say}" for e in result.events if e.say][:6],
        "places": {pl: sum(e.place == pl for e in result.events) for pl in sorted({e.place for e in result.events})},
        "announcements": [f"Day {a.day}: {a.text}" for a in result.announcements][:8],
        "reflections": len(result.reflections),
        "reflections_with_ratings": sum(bool(r.ratings) for r in result.reflections),
        "sample_reflections": [f"Day {r.day} {r.twin}: {r.text} {r.ratings}" for r in result.reflections[-3:]],
        "longing_end": {k: {n: round(v, 1) for n, v in d.items() if v >= 0.5} for k, d in result.longing.items()},
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
