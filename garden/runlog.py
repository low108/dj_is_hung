"""Run logs: four tables as JSON lines (runs, events, reflections, scores), one directory per simulation.

The columns match the BigQuery tables planned in the spec, so A3 can load these files unchanged.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .batch import Simulation
from .llm import CHOICE_TEMPERATURE, TEXT_TEMPERATURE
from .prompts import save_prompt_version
from .scoring import score

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "data" / "prompts"


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_simulation(sim_id: str, sim: Simulation, woman: str, men: list[str], *,
                     out_dir: Path = DEFAULT_DIR, prompts_dir: Path = PROMPTS_DIR) -> Path:
    """Write the four tables for one simulation and return its directory."""
    directory = Path(out_dir) / sim_id
    directory.mkdir(parents=True, exist_ok=True)
    version = save_prompt_version(prompts_dir)
    logged_at = datetime.now(timezone.utc).isoformat()

    runs, events, reflections = [], [], []
    for rec in sim.records:
        spec, res = rec.spec, rec.result
        runs.append({
            "sim_id": sim_id, "run_id": spec.run_id, "logged_at": logged_at,
            # reproducibility
            "seed": spec.seed, "prompt_version": version, "model": spec.model,
            "temperature": {"choice": CHOICE_TEMPERATURE, "text": TEXT_TEMPERATURE}, "price_level": spec.price.value,
            # outcome
            "outcome": res.outcome.value if res else "error", "breakout_pair": list(res.pair) if res and res.pair else None,
            "day_ended": res.day if res else None, "scorable": bool(res and res.scorable),
            "breach": res.breach.phrase if res and res.breach else None, "error": rec.error,
            "wall_seconds": round(rec.wall_seconds, 2),
        })
        if res is None:
            continue
        events += [{"sim_id": sim_id, "run_id": spec.run_id, "day": e.day, "twin": e.twin, "rung": e.rung.value,
                    "target": e.target, "say": e.say, "place": e.place,
                    "standing_before": e.standing_before, "standing_after": e.standing_after} for e in res.events]
        reflections += [{"sim_id": sim_id, "run_id": spec.run_id, "day": r.day, "twin": r.twin, "text": r.text,
                         **{f"rating_{k}": v for k, v in r.ratings.items()}} for r in res.reflections]

    scores = [{"sim_id": sim_id, "woman": woman, "candidate": c.candidate,
               "max_price_level": c.price.value if c.price else None,
               "breakout_rate_by_price": {p: {"breakouts": k, "runs": n} for p, (k, n) in c.breakouts_by_price.items()},
               "ci_low": c.ci_low, "ci_high": c.ci_high} for c in score(list(sim.records), woman, men)]

    _write(directory / "runs.jsonl", runs)
    _write(directory / "events.jsonl", events)
    _write(directory / "reflections.jsonl", reflections)
    _write(directory / "scores.jsonl", scores)
    return directory
