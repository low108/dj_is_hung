"""Replay files: every finished run's feed events and evening snapshots, saved so the viewer can play
any run again without re-running the simulation (no model calls).

One JSON file per run: <dir>/<sim_id>/<run_id>.json. A replay holds exactly what the live viewer
received (FeedEvents and TwinStates), plus the run's identity and outcome for the run picker.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path

from .batch import Observer, RunRecord, RunSpec
from .feed import FeedCursor
from .paths import DATA_DIR

DEFAULT_DIR = DATA_DIR / "replays"
SUMMARY_FIELDS = ("sim_id", "run_id", "model", "price", "seed", "scenario", "featured", "outcome", "day",
                  "pair", "created_at")


class Recorder:
    """Collects one run's feed events and evening snapshots while it runs."""

    def __init__(self, spec: RunSpec):
        self._cursor = FeedCursor(spec.run_id)
        self._lock = threading.Lock()
        self.events: list[dict] = []
        self.twin_states: list[dict] = []

    def _feed(self, item, word) -> None:
        with self._lock:
            self.events.append(self._cursor(item, word).to_dict())

    def _states(self, states) -> None:
        with self._lock:
            self.twin_states += [asdict(s) for s in states]

    @property
    def observer(self) -> Observer:
        return Observer(on_feed=self._feed, on_state=self._states)


def replay_of(sim_id: str, record: RunRecord, recorder: Recorder, twins: list[str], *, scenario: str | None,
              featured: bool, created_at: str) -> dict | None:
    """The replay for one finished run, or None if the run errored (nothing to play).
    `created_at` is the simulation's, so its runs sort together in the picker."""
    res = record.result
    if res is None:
        return None
    spec = record.spec
    return {
        "sim_id": sim_id, "run_id": spec.run_id, "model": spec.model, "price": spec.price.value,
        "seed": spec.seed, "scenario": scenario, "featured": featured,
        "outcome": res.outcome.value, "day": res.day, "pair": list(res.pair) if res.pair else None,
        "unrequited": [{"day": a.day, "twin": a.twin, "target": a.target} for a in res.unrequited],
        "breach": {"day": res.breach.day, "twin": res.breach.twin, "phrase": res.breach.phrase}
        if res.breach else None,
        "created_at": created_at,
        "twins": twins, "events": recorder.events, "twin_states": recorder.twin_states,
    }


def save(replay: dict, out_dir: Path = DEFAULT_DIR) -> Path:
    path = Path(out_dir) / replay["sim_id"] / f"{replay['run_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(replay, ensure_ascii=False))
    return path


def list_replays(out_dir: Path = DEFAULT_DIR) -> list[dict]:
    """Summaries for the run picker, newest simulation first, runs in plan order."""
    rows = []
    for path in Path(out_dir).glob("*/*.json"):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue  # a half-written or foreign file is not a replay
        rows.append({k: data.get(k) for k in SUMMARY_FIELDS})
    rows.sort(key=lambda r: r["run_id"])
    rows.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return rows


def load(sim_id: str, run_id: str, out_dir: Path = DEFAULT_DIR) -> dict:
    """Raise KeyError if there is no such replay."""
    if not (_safe(sim_id) and _safe(run_id)):
        raise KeyError(f"no replay {sim_id}/{run_id}")
    path = Path(out_dir) / sim_id / f"{run_id}.json"
    if not path.is_file():
        raise KeyError(f"no replay {sim_id}/{run_id}")
    return json.loads(path.read_text())


def _safe(part: str) -> bool:
    return part.isalnum()
