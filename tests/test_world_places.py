"""The viewer's place list must match the engine's (web/app/garden/world.ts vs garden/coordinator.py)."""
import re
from pathlib import Path

from garden.coordinator import PLACES

WORLD_TS = Path(__file__).resolve().parent.parent / "web" / "app" / "garden" / "world.ts"


def test_the_map_has_exactly_the_engines_places():
    source = WORLD_TS.read_text()
    listed = re.search(r"export const PLACES = \[(.*?)\] as const", source, re.S).group(1)
    assert tuple(re.findall(r'"(\w+)"', listed)) == PLACES
    for place in PLACES:
        assert re.search(rf"\b{place}: \{{", source), f"no zone for {place}"
