"""Annotate a recorded run for the demo map: a venue for each date day and up to three gist emoji per line.

    uv run python scripts/annotate_scenes.py data/replays/<sim_id>/r00.json

Writes the events back with 'venue' and 'gist' added (the original is kept as r00.raw.json). Uses the
MediaPipe Decision Maker on Gemma 4 E4B (data/models/), on this machine: no API calls.
"""
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from garden import scenes  # noqa: E402

path = Path(sys.argv[1])
raw = path.with_name(path.stem + ".raw.json")
if not raw.exists():
    shutil.copy(path, raw)
replay = json.loads(raw.read_text())
start = time.time()
scene = scenes.annotate(replay["events"])
replay["events"] = scenes.apply(replay["events"], scene)
path.write_text(json.dumps(replay, ensure_ascii=False))
dates = sorted({(e["day"], e["twin"], e["target"], e["venue"]) for e in replay["events"] if "venue" in e and e["twin"] == replay["woman"]})
print(f"{len(scene.gist)} lines, {len(set(scene.venue.values()))} venues, {time.time() - start:.0f}s")
print("her dates:", [(d, man, v) for d, _, man, v in dates])
print("emoji used:", Counter(g for gs in scene.gist.values() for g in gs).most_common(15))
