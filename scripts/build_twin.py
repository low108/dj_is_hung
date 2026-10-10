"""Show the twin built from one speed-dating participant.

Usage: uv run python scripts/build_twin.py 7 [--llm]   (--llm rewrites memories with TWIN_MODEL)
"""
from __future__ import annotations

import argparse

from dotenv import load_dotenv

from garden import speed_dating as sd
from garden.llm import make_model


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("iid", type=int)
    p.add_argument("--llm", action="store_true", help="rewrite memories naturally with TWIN_MODEL")
    args = p.parse_args()

    load_dotenv(".env")
    model = make_model() if args.llm else None
    twin = sd.build_twin(sd.load(), args.iid, model)
    print(f"{twin.alias} (iid {twin.iid}, {twin.gender}), rebel threshold {twin.rebel_threshold}")
    for m in twin.memories:
        print(f"  [{m.source}] {m.text}")


if __name__ == "__main__":
    main()
