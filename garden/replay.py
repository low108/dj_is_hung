"""Replay files: every finished run's feed events and evening snapshots, saved so the viewer can play
any run again without re-running the simulation (no model calls).

Two files per run, written the moment the run finishes: <dir>/<sim_id>/<run_id>.json (the whole replay)
and <run_id>.summary.json (identity and outcome only, so the run picker never parses whole replays).
A replay holds exactly what the live viewer received: FeedEvents and TwinStates.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from .batch import Observer, RunRecord, RunSpec
from .engine import RunResult
from .feed import FeedCursor
from .paths import DATA_DIR

DEFAULT_DIR = DATA_DIR / "replays"
SUMMARY_FIELDS = ("sim_id", "run_id", "model", "seed", "scenario", "featured", "outcome", "day",
                  "pair", "created_at")


def outcome_fields(res: RunResult) -> dict:
    """How a run ended, as JSON: shared by the API's run results and the replay files."""
    return {
        "outcome": res.outcome.value,
        "day": res.day,
        "pair": list(res.pair) if res.pair else None,
        "wall_opened": res.wall_opened,
        "unrequited": [{"day": a.day, "twin": a.twin, "target": a.target} for a in res.unrequited],
        "flagged": res.flagged,  # a twin kept slipping out of character: kept, but not scored (#64)
        "slips": len(res.slips),
        "line_redos": len(res.redos),  # lines asked again for being empty or an echo
        "breach": ({"day": res.breach.day, "twin": res.breach.twin, "phrase": res.breach.phrase,
                    "text": res.breach.text} if res.breach else None),
    }


@dataclass(frozen=True)
class ReplayId:
    sim_id: str
    run_id: str

    def path(self, out_dir: Path, suffix: str = ".json") -> Path:
        if not (self.sim_id.isalnum() and self.run_id.isalnum()):  # ids are hex / rNN: no path tricks
            raise KeyError(f"no replay {self}")
        return Path(out_dir) / self.sim_id / f"{self.run_id}{suffix}"

    def __str__(self) -> str:
        return f"{self.sim_id}/{self.run_id}"


class Recorder:
    """Collects one run's feed events and evening snapshots as it runs (each run has its own thread).
    `live` hears every event and evening as it's recorded: the featured run's stream to the viewer."""

    def __init__(self, spec: RunSpec, live: Callable[[list[dict], list[dict]], None] | None = None):
        self._cursor = FeedCursor(spec.run_id)
        self._live = live
        self.events: list[dict] = []
        self.twin_states: list[dict] = []

    def _feed(self, item, word) -> None:
        event = self._cursor(item, word).to_dict()
        self.events.append(event)
        if self._live:
            self._live([event], [])

    def _states(self, states) -> None:
        evening = [asdict(s) for s in states]
        self.twin_states += evening
        if self._live:
            self._live([], evening)

    @property
    def observer(self) -> Observer:
        return Observer(on_feed=self._feed, on_state=self._states)


@dataclass(frozen=True)
class SimulationInfo:
    """What every replay of one simulation shares."""

    sim_id: str
    twins: list[str]
    woman: str           # her twin: the viewer follows her days
    scenario: str | None  # the fake-model scenario; None for real models
    featured_run: str | None
    created_at: str      # the simulation's, so its runs sort together in the picker
    profiles: dict[str, list[dict]] | None = None  # each twin's persona, for the viewer's profile cards
    matched: list[str] | None = None  # her real matches (the answer key), when the pool has one


def replay_of(info: SimulationInfo, record: RunRecord, recorder: Recorder) -> dict | None:
    """The replay for one finished run, or None if the run errored (nothing to play)."""
    if record.result is None:
        return None
    spec = record.spec
    return {
        "sim_id": info.sim_id, "run_id": spec.run_id, "model": spec.model,
        "seed": spec.seed, "scenario": info.scenario, "featured": spec.run_id == info.featured_run,
        **outcome_fields(record.result), "created_at": info.created_at,
        "twins": info.twins, "woman": info.woman, "events": recorder.events, "twin_states": recorder.twin_states,
        "profiles": info.profiles or {}, "matched": info.matched,
    }


def _write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    os.replace(tmp, path)  # readers see the old file or the whole new one, never half of it


def save(replay: dict, out_dir: Path) -> Path:
    """Write the replay, then its summary (the picker only lists runs whose replay is complete)."""
    rid = ReplayId(replay["sim_id"], replay["run_id"])
    path = rid.path(out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, replay)
    _write_atomic(rid.path(out_dir, ".summary.json"), {k: replay[k] for k in SUMMARY_FIELDS})
    return path


def _plan_order(run_id: str) -> tuple[int, str]:
    return (len(run_id), run_id)  # r99 before r100


def list_replays(out_dir: Path) -> list[dict]:
    """Summaries for the run picker, newest simulation first, runs in plan order."""
    rows = []
    for path in Path(out_dir).glob("*/*.summary.json"):
        try:
            rows.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue  # a foreign or damaged file is not a replay
    rows.sort(key=lambda r: _plan_order(r["run_id"]))
    rows.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return rows


def load(rid: ReplayId, out_dir: Path) -> dict:
    """Raise KeyError if there is no such replay (or it can't be read)."""
    path = rid.path(out_dir)
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise KeyError(f"no replay {rid}") from e
