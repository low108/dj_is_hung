"""Run the ablation ladder and print breakout rates per step.

Usage: uv run python scripts/ablation.py [--pool IID] [--model ilmu:ilmu-mini-v3.3] [--seeds 0 1 2] [--days 10]
"""
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict

from dotenv import load_dotenv

from garden import demo
from garden import pools as pool_lib
from garden import speed_dating as sd
from garden.ablation import run_ladder
from garden.paths import DATA_DIR
from garden.runlog import write_simulation


def main() -> None:
    load_dotenv(".env")
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=os.environ.get("TWIN_MODEL", "ilmu:ilmu-mini-v3.3"))
    p.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--pool", type=int, default=None)
    args = p.parse_args()

    if args.pool is not None:
        pool = pool_lib.load_pool(sd.load(), args.pool)
        twins, personas, woman, men = pool.twins, pool.personas, pool.woman.alias, pool.men_aliases
    else:
        twins, personas, woman, men = demo.POOL, demo.PERSONAS, demo.WOMAN, demo.MEN

    tag = f"ablation-{int(time.time())}"
    start = time.perf_counter()
    rows = []
    for summary, sim in run_ladder(twins, lambda spec: demo.make_twin_model(spec, personas), args.model,
                                   args.seeds, max_days=args.days):
        write_simulation(f"{tag}-step{summary.step[0]}", sim, woman, men)
        rows.append(asdict(summary) | {"breakout_rate": round(summary.breakout_rate, 3)})
        print(f"{summary.step:26s} runs {summary.runs:2d}  breakouts {summary.breakouts}/{summary.scorable} "
              f"({summary.breakout_rate:.0%})  unrequited {summary.unrequited:2d}  gated actions {summary.gated_actions:3d}  "
              f"gate permitted {summary.gate_permitted:.0%}  excluded {summary.excluded}  errors {summary.errors}",
              flush=True)
    out = DATA_DIR / "ablations" / f"{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": args.model, "pool": args.pool, "seeds": args.seeds, "days": args.days,
                               "steps": rows}, indent=2))
    print(f"{time.perf_counter() - start:.0f}s; summary: {out}")


if __name__ == "__main__":
    main()
