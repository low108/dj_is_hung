"""Add each twin's persona profile (and the answer key) to a replay saved before replays carried them.

    uv run python scripts/add_profiles.py data/replays/<sim_id>/r00.json --pool 1 [--non-matches 3]

The pool must be the one the run used (Columbia participant iid and how many men she didn't match with).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from garden import pools  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("replay", type=Path)
ap.add_argument("--pool", type=int, required=True)
ap.add_argument("--non-matches", type=int, default=3)
args = ap.parse_args()
replay = json.loads(args.replay.read_text())
pool = pools.resolve(args.pool, non_matches=args.non_matches)
if sorted(t.alias for t in pool.twins) != sorted(replay["twins"]):
    sys.exit(f"pool {args.pool} has {sorted(t.alias for t in pool.twins)}, the replay has {sorted(replay['twins'])}")
replay["profiles"] = pool.profiles_or_personas()
replay["matched"] = sorted(pool.matched) if pool.matched else None
args.replay.write_text(json.dumps(replay, ensure_ascii=False))
print(f"added profiles for {len(replay['profiles'])} twins; real matches: {replay['matched']}")
