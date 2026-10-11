"""Run logs: four tables as JSON lines (runs, events, reflections, scores), one directory per simulation.

The columns match the BigQuery tables planned in the spec, so A3 can load these files unchanged.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .batch import PriceLevel, Simulation
from .llm import CHOICE_RETRY_STEP, CHOICE_TEMPERATURE, TEXT_TEMPERATURE
from .paths import DATA_DIR
from .prompts import save_prompt_version
from .scoring import score

DEFAULT_DIR = DATA_DIR / "runs"
PROMPTS_DIR = DATA_DIR / "prompts"
RATINGS = ("longing", "trust", "standing_matters", "on_my_mind")


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_simulation(sim_id: str, sim: Simulation, woman: str, men: list[str], *,
                     out_dir: Path = DEFAULT_DIR, prompts_dir: Path = PROMPTS_DIR) -> Path:
    """Write the four tables for one simulation and return its directory.

    Columns are fixed (no nested or run-dependent keys) so A3 can load them into BigQuery with a
    fixed schema. A run that errored has only its runs row."""
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
            "seed": spec.seed, "prompt_version": version,
            # model ids are pinned (e.g. gemini-3.5-flash), so the id is the version
            "provider": spec.model.partition(":")[0], "model": spec.model.partition(":")[2] or spec.model,
            "temperature_text": TEXT_TEMPERATURE, "temperature_choice": CHOICE_TEMPERATURE,
            "temperature_choice_retry_step": CHOICE_RETRY_STEP, "price_level": spec.price.value,
            # outcome
            "outcome": res.outcome.value if res else "error", "breakout_pair": list(res.pair) if res and res.pair else None,
            "day_ended": res.day if res else None, "scorable": bool(res and res.scorable),
            "breach": res.breach.phrase if res and res.breach else None, "error": rec.error,
            "immersion_resamples": res.immersion_resamples if res else None,
            "immersion_break_phrases": [b.phrase for b in res.immersion_breaks] if res else [],
            "wall_seconds": round(rec.wall_seconds, 2),
        })
        if res is None:
            continue
        events += [{"sim_id": sim_id, "run_id": spec.run_id, "day": e.day, "twin": e.twin, "rung": e.rung.value,
                    "target": e.target, "say": e.say, "place": e.place,
                    "standing_before": e.standing_before, "standing_after": e.standing_after} for e in res.events]
        reflections += [{"sim_id": sim_id, "run_id": spec.run_id, "day": r.day, "twin": r.twin, "text": r.text,
                         **{f"rating_{k}": r.ratings.get(k) for k in RATINGS}} for r in res.reflections]

    scores = [{"sim_id": sim_id, "woman": woman, "candidate": c.candidate,
               "max_price_level": c.price.value if c.price else None,
               **_by_price_columns(c.breakouts_by_price), "ci_low": c.ci_low, "ci_high": c.ci_high}
              for c in score(list(sim.records), woman, men)]

    _write(directory / "runs.jsonl", runs)
    _write(directory / "events.jsonl", events)
    _write(directory / "reflections.jsonl", reflections)
    _write(directory / "scores.jsonl", scores)
    return directory


def _by_price_columns(by_price: dict[str, tuple[int, int]]) -> dict:
    """breakouts_low, runs_low, rate_low, breakouts_high, ... (fixed columns, one set per price level)."""
    out = {}
    for price in PriceLevel:
        k, n = by_price.get(price.value, (0, 0))
        out |= {f"breakouts_{price.value}": k, f"runs_{price.value}": n,
                f"rate_{price.value}": round(k / n, 3) if n else None}
    return out
