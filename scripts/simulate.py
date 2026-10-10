"""Run a full simulation (models x price levels x seeds, in parallel) on the demo pool and summarise it.

Usage: uv run python scripts/simulate.py [--models ilmu:ilmu-mini-v3.3] [--seeds 0 1] [--days 10]
"""
from __future__ import annotations

import argparse
import os
import time
from collections import Counter

from dotenv import load_dotenv

from garden import demo
from garden import pools as pool_lib
from garden import speed_dating as sd
from garden.batch import PriceLevel, plan, run_simulation
from garden.runlog import write_simulation
from garden.scoring import score


def main() -> None:
    load_dotenv(".env")
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", default=[os.environ.get("TWIN_MODEL", "ilmu:ilmu-mini-v3.3")])
    p.add_argument("--seeds", nargs="+", type=int, default=[0, 1])
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--parallelism", type=int, default=12)
    p.add_argument("--pool", type=int, default=None, help="a real woman's speed-dating iid")
    args = p.parse_args()

    specs = plan(args.models, list(PriceLevel), args.seeds)
    if args.pool is not None:
        pool = pool_lib.load_pool(sd.load(), args.pool)
        twins, personas, woman, men = pool.twins, pool.personas, pool.woman.alias, pool.men_aliases
        print(f"Pool {args.pool}: {woman} with {', '.join(men)} (real matches: {', '.join(sorted(pool.matched))})")
    else:
        pool, twins, personas, woman, men = None, demo.POOL, demo.PERSONAS, demo.WOMAN, demo.MEN
    sim = run_simulation(specs, twins, lambda spec: demo.make_twin_model(spec, personas),
                         parallelism=args.parallelism, max_days=args.days)

    print(f"{len(sim.records)} runs in {sim.wall_seconds:.0f}s wall ({sum(r.wall_seconds for r in sim.records):.0f}s of run time)")
    for r in sim.records:
        res = r.result
        if res is None:
            print(f"  {r.spec.run_id} {r.spec.model:24s} {r.spec.price.value:4s} seed {r.spec.seed}: ERROR {r.error}")
            continue
        outcome = f"{res.outcome.value} day {res.day}" + (f" {'+'.join(res.pair)}" if res.pair else "")
        if res.breach:
            outcome += f' — {res.breach.twin}: "{res.breach.phrase}" in "{res.breach.text[:120]}"'
        outcome += f" | gate permitted {sum(v.permitted for v in res.verdicts)}/{len(res.verdicts)} twin-days"
        print(f"  {r.spec.run_id} {r.spec.model:24s} {r.spec.price.value:4s} seed {r.spec.seed}: {outcome}")
    log_dir = write_simulation(f"sim-{int(time.time())}", sim, woman, men)
    print(f"logs: {log_dir}")
    pairs = Counter("+".join(r.result.pair) for r in sim.scorable if r.result.pair)
    print("breakouts:", dict(pairs) or "none", "| excluded:", sum(1 for r in sim.records if r.result and not r.result.scorable))
    ranking = score(list(sim.records), woman, men)
    for i, c in enumerate(ranking, 1):
        print(f"  {i}. {c.candidate:8s} {c.price.value if c.price else 'never':5s} {c.breakouts}/{c.runs} "
              f"({c.ci_low:.0%}-{c.ci_high:.0%})")
    if pool is not None:
        check = pool_lib.check_ranking(ranking, pool.matched)
        print(f"answer key: matches on top = {check.matches_on_top}, pairs in order = {check.pairs_in_order:.0%} (50% = chance)")


if __name__ == "__main__":
    main()
