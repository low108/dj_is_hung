"""HTTP API: start a simulation and read its result."""
from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Literal, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from garden import agreement, couples, demo, highlights, llm, replay
from garden import twin_builder as tb
from garden import pools as pool_lib
from garden import speed_dating as sd
from garden.batch import Simulation, featured_spec, plan, run_simulation
from garden.runlog import write_simulation
from garden.scoring import score

from . import onboarding, twin
from .auth import TokenVerifier, current_user, firebase_verifier
from .store import Store, default_store

log = logging.getLogger(__name__)


class TextModel(Protocol):
    def sample_text(self, prompt: str, **kwargs) -> str: ...


class StartSimulation(BaseModel):
    """models x seeds runs. 'fake:*' models are scripted (no API calls)."""

    scenario: Literal["breakout", "unrequited", "timeout", "flagged"] = "breakout"  # for fake models
    models: list[str] = demo.FAKE_MODELS  # scripted stand-ins; [demo.ENSEMBLE_ALIAS] = the real ensemble
    seeds: list[int] = [0, 1]
    max_days: int | None = None  # a safety cap; a run ends when every man has had his dates (or a breakout)
    pool_iid: int | None = None  # a real speed-dating woman (see GET /pools); None = placeholder demo pool
    pool_non_matches: int = Field(3, ge=1, le=10)  # men in her pool she didn't match with (chance = matches / men)
    couple_id: int | None = None  # a real couple (garden/couples.py): her twin, her partner's, 6 men from other couples
    my_twin: bool = False  # the signed-in user's own twin as the woman, with the demo pool's men (D4)
    background: bool = False  # True: return at once and stream the featured run's events (the web app)


def serialize(result) -> dict:
    return {
        **replay.outcome_fields(result),
        "scorable": result.scorable,
        "standing": result.standing,
        "longing": {who: {n: round(v, 2) for n, v in d.items()} for who, d in result.longing.items()},
        "announcements": [{"day": a.day, "text": a.text} for a in result.announcements],
        "reflections": [{"day": r.day, "twin": r.twin, "text": r.text, "ratings": r.ratings}
                        for r in result.reflections],
        "events": [
            {"day": e.day, "twin": e.twin, "rung": e.rung.value, "target": e.target, "say": e.say,
             "standing_before": e.standing_before, "standing_after": e.standing_after, "place": e.place}
            for e in result.events
        ],
    }


def serialize_simulation(sim: Simulation, pool: pool_lib.PoolSetup, highlight_model=None) -> dict:
    """`highlight_model` captions the top candidates' highlights (None: template captions)."""
    woman, men, matched = pool.woman, pool.men, pool.matched
    scores = score(list(sim.records), woman, men)
    picked = highlights.for_simulation(list(sim.records), scores, woman, pool.personas, highlight_model)
    runs = [{"run_id": r.spec.run_id, "model": r.spec.model, "seed": r.spec.seed,
             "wall_seconds": round(r.wall_seconds, 2), "error": r.error,
             "result": serialize(r.result) if r.result else None} for r in sim.records]
    ranking = [{"candidate": c.candidate, "chosen": c.chosen, "breakouts": c.breakouts, "runs": c.runs,
                "rate": round(c.rate, 3),
                "ci_low": c.ci_low, "ci_high": c.ci_high} for c in scores]
    answer_key = None
    if matched is not None:
        check = pool_lib.check_ranking(scores, matched)
        answer_key = {"matched": sorted(matched), "matched_ranks": check.matched_ranks,
                      "other_ranks": check.other_ranks, "matches_on_top": check.matches_on_top,
                      "pairs_in_order": check.pairs_in_order}
    return {"wall_seconds": round(sim.wall_seconds, 2), "runs": runs, "ranking": ranking,
            "scored_runs": len(sim.scorable), "woman": woman, "answer_key": answer_key,
            "highlights": [h.to_dict() for h in picked],
            "models": sorted({r.spec.model for r in sim.records}),
            "agreement": [a.to_dict() for a in agreement.agreement(list(sim.records), scores, woman, men)],
            "result": runs[0]["result"] if runs else None}  # first run kept for the single-result page


class LiveLimits:
    """Guards a public deployment's API credits. Scripted models are always allowed. From the environment:
    ALLOWED_MODELS (comma list of real models; unset = any), MAX_REAL_SIMS (real simulations running at
    once; unset = no limit), MAX_REAL_RUNS (runs in one real simulation; unset = no limit)."""

    def __init__(self, allowed: set[str] | None = None, max_sims: int | None = None, max_runs: int | None = None):
        self.allowed, self.max_sims, self.max_runs = allowed, max_sims, max_runs
        self._running: list[str] = []
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "LiveLimits":
        num = lambda k: int(os.environ[k]) if os.environ.get(k) else None  # noqa: E731
        allowed = os.environ.get("ALLOWED_MODELS")
        return cls({m.strip() for m in allowed.split(",") if m.strip()} if allowed else None,
                   num("MAX_REAL_SIMS"), num("MAX_REAL_RUNS"))

    def admit(self, models: list[str], runs: int, sim_id: str) -> None:
        if all(demo.is_fake(m) for m in models):
            return
        if self.allowed is not None:
            refused = [m for m in models if not demo.is_fake(m) and m not in self.allowed]
            if refused:
                raise HTTPException(403, f"this server doesn't run {', '.join(refused)}")
        if self.max_runs is not None and runs > self.max_runs:
            raise HTTPException(400, f"at most {self.max_runs} run(s) per live simulation here")
        with self._lock:
            if self.max_sims is not None and len(self._running) >= self.max_sims:
                raise HTTPException(429, f"a live simulation is already running: open ?sim={self._running[0]} "
                                         "to watch it, or try the scripted model")
            self._running.append(sim_id)

    def release(self, sim_id: str) -> None:
        with self._lock:
            if sim_id in self._running:
                self._running.remove(sim_id)


def create_app(store: Store | None = None, log_runs: bool = False,
               replay_dir: Path | None = None, verify_token: TokenVerifier | None = None,
               followup_model: Callable[[], TextModel | None] | None = None,
               extraction_model: Callable[[], tb.ExtractionModel | None] | None = None) -> FastAPI:
    """`replay_dir`: where finished runs are saved for replay (None: not saved, and no replays listed).
    `verify_token` turns a sign-in token into a user id (default: Firebase Auth). `followup_model()` gives
    the model that asks onboarding follow-ups (default: Gemini Flash when a key is set; None: templates).
    `extraction_model()` gives (name, model) for building twins (default: Gemini Pro; None: unavailable)."""
    app = FastAPI(title="dj_is_hung API")
    app.state.verify_token = verify_token or (lambda token: firebase_verifier()(token))
    app.state.followup_model = followup_model or demo.make_followup_model
    app.state.extraction_model = extraction_model or demo.make_extraction_model
    app.include_router(onboarding.router)
    app.include_router(twin.router)
    app.state.log_runs = log_runs
    app.state.replay_dir = replay_dir
    app.state.store = store or default_store()
    origins = os.environ.get("CORS_ORIGINS")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins.split(",") if origins else [],
        # Local dev: any localhost port (the web app may not get :3000)
        allow_origin_regex=None if origins else r"http://(localhost|127\.0\.0\.1):\d+",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.dates = None
    limits = LiveLimits.from_env()

    def dates():
        if app.state.dates is None:
            try:
                app.state.dates = sd.load()
            except FileNotFoundError as e:
                raise HTTPException(503, str(e)) from e
        return app.state.dates

    @app.get("/pools")
    def list_pools() -> list[dict]:
        """Real women eligible for a demo pool (at least 2 mutual matches and 3 non-matches)."""
        return pool_lib.eligible_women(dates())

    @app.post("/simulations", status_code=201)
    def start_simulation(req: StartSimulation, request: Request) -> dict:
        sim_id = uuid.uuid4().hex[:12]
        models = list(llm.ENSEMBLE) if req.models == [demo.ENSEMBLE_ALIAS] else req.models
        specs = plan(models, req.seeds)
        real = not all(demo.is_fake(m) for m in models)
        couple = None
        if req.my_twin:
            pool = demo.with_her_twin(*tb.garden_inputs(twin.reviewed_twin(request, current_user(request))))
        elif req.couple_id is not None:
            try:
                pool, couple = couples.setup(req.couple_id)
            except (KeyError, FileNotFoundError) as e:
                raise HTTPException(404, str(e)) from e
        else:
            try:
                pool = pool_lib.resolve(req.pool_iid, dates, req.pool_non_matches)
            except KeyError as e:
                raise HTTPException(404, str(e)) from e
        twins, personas, woman, men = pool.twins, pool.personas, pool.woman, pool.men
        record = {
            "id": sim_id,
            "status": "running",
            "scenario": req.scenario,
            "runs_planned": len(specs),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        featured = featured_spec(specs)
        record["featured_run"] = featured.run_id if featured else None
        record["twins"] = [t.alias for t in twins]  # the viewer places sprites before any event arrives
        record["woman"] = woman  # whose days the viewer follows
        record["profiles"] = pool.profiles_or_personas()  # each twin's persona, for the profile cards
        if pool.matched is not None:
            record["matched"] = sorted(pool.matched)
        if couple is not None:  # the couples answer key: her real partner, and how happy they are
            record["couple"] = {"id": req.couple_id, "partner": couple.partner,
                                "satisfaction": {"her": couple.satisfaction[0], "him": couple.satisfaction[1]}}
        if real:  # taken last, so nothing above can fail and leave the slot taken
            limits.admit(models, len(specs), sim_id)
        app.state.store.save(sim_id, record)
        store = app.state.store

        info = replay.SimulationInfo(sim_id, record["twins"], woman,
                                     scenario=req.scenario if all(demo.is_fake(m) for m in models) else None,
                                     featured_run=record["featured_run"], created_at=record["created_at"],
                                     profiles=record["profiles"], matched=record.get("matched"))

        def stream(events: list[dict], states: list[dict]) -> None:
            if events:
                store.add_events(sim_id, events)
            if states:
                store.save_twin_states(sim_id, states)

        recorders = {spec.run_id: replay.Recorder(spec, live=stream if spec.run_id == info.featured_run else None)
                     for spec in specs}

        def save_replay(rec) -> None:
            if app.state.replay_dir is None:
                return
            saved = replay.replay_of(info, rec, recorders[rec.spec.run_id])
            if saved is None:
                return
            try:
                replay.save(saved, app.state.replay_dir)
            except OSError as e:  # a replay that can't be written must not sink the simulation
                log.warning("could not save replay %s/%s: %s", sim_id, rec.spec.run_id, e)

        def run() -> dict:
            try:
                return finish()
            except Exception as e:  # a background failure must not leave the record "running" forever
                failed = record | {"status": "failed", "error": f"{type(e).__name__}: {e}"}
                store.save(sim_id, failed)
                if not req.background:
                    raise
                return failed
            finally:
                if real:
                    limits.release(sim_id)

        def highlight_model():
            try:
                return demo.make_highlight_model(models)
            except (KeyError, ValueError) as e:  # e.g. no API key: template captions instead of no results
                log.warning("highlights use template captions: %s", e)
                return None

        def finish() -> dict:
            # Runs fan out on local threads for now; A3 moves the same RunSpecs to Cloud Run Job tasks.
            sim = run_simulation(specs, twins,
                                 lambda spec: demo.make_twin_model(spec, personas, fake_scenario=req.scenario, woman=woman),
                                 observe=lambda spec: recorders[spec.run_id].observer,
                                 on_finished=save_replay,
                                 **({"max_days": req.max_days} if req.max_days else {}))
            done = record | {"status": "done", "pool_iid": req.pool_iid, "my_twin": req.my_twin,
                             **serialize_simulation(sim, pool, highlight_model())}
            if app.state.log_runs:
                done["log_dir"] = str(write_simulation(sim_id, sim, woman, men))
            store.save(sim_id, done)
            return done

        if req.background:
            threading.Thread(target=run, name=f"sim-{sim_id}", daemon=True).start()
            return record
        return run()

    @app.get("/simulations/{sim_id}/events")
    def get_events(sim_id: str, after: int = -1) -> list[dict]:
        """The featured run's feed events with seq > after (poll with the last seq you saw)."""
        if app.state.store.get(sim_id) is None:
            raise HTTPException(404, "simulation not found")
        return app.state.store.events(sim_id, after)

    @app.get("/simulations/{sim_id}/twins")
    def get_twins(sim_id: str) -> list[dict]:
        """Every evening's snapshot of every twin in the featured run (partner, time left, Standing in words,
        longing as hearts, that evening's reflection), so the side panel can show the evening the map has
        reached rather than the latest one. For the viewer only."""
        if app.state.store.get(sim_id) is None:
            raise HTTPException(404, "simulation not found")
        return app.state.store.twin_states(sim_id)

    @app.get("/replays")
    def list_replays() -> list[dict]:
        """Every saved run, newest simulation first: the run picker. Reads files only."""
        return replay.list_replays(app.state.replay_dir) if app.state.replay_dir else []

    @app.get("/replays/{sim_id}/{run_id}")
    def get_replay(sim_id: str, run_id: str) -> dict:
        """One run's stored feed events and evening snapshots. Never re-runs anything."""
        if app.state.replay_dir is None:
            raise HTTPException(404, "replays are not saved by this server")
        try:
            return replay.load(replay.ReplayId(sim_id, run_id), app.state.replay_dir)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/simulations/{sim_id}")
    def get_simulation(sim_id: str) -> dict:
        record = app.state.store.get(sim_id)
        if record is None:
            raise HTTPException(404, "simulation not found")
        return record

    return app


app = create_app(log_runs=True, replay_dir=replay.DEFAULT_DIR)  # the served app logs and saves replays; tests don't
