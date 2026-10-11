"""HTTP API: start a simulation and read its result."""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from garden import demo, feed
from garden import pools as pool_lib
from garden import speed_dating as sd
from garden.batch import PriceLevel, RunSpec, Simulation, featured_spec, plan, run_simulation
from garden.runlog import write_simulation
from garden.scoring import score

from .store import SimulationStore, default_store


class StartSimulation(BaseModel):
    """models x price levels x seeds runs. 'fake:*' models are scripted (no API calls)."""

    scenario: Literal["breakout", "unrequited", "timeout", "excluded"] = "breakout"  # for fake models
    models: list[str] = demo.FAKE_MODELS
    prices: list[PriceLevel] = list(PriceLevel)
    seeds: list[int] = [0, 1]
    max_days: int = 10
    pool_iid: int | None = None  # a real speed-dating woman (see GET /pools); None = placeholder demo pool
    background: bool = False  # True: return at once and stream the featured run's events (the web app)


def serialize(result) -> dict:
    return {
        "outcome": result.outcome.value,
        "day": result.day,
        "pair": list(result.pair) if result.pair else None,
        "unrequited": [{"day": a.day, "twin": a.twin, "target": a.target} for a in result.unrequited],
        "scorable": result.scorable,
        "breach": ({"day": result.breach.day, "twin": result.breach.twin, "phrase": result.breach.phrase,
                    "text": result.breach.text} if result.breach else None),
        "standing": result.standing,
        "longing": {who: {n: round(v, 2) for n, v in d.items()} for who, d in result.longing.items()},
        "announcements": [{"day": a.day, "text": a.text} for a in result.announcements],
        "verdicts": [{"day": v.day, "twin": v.twin, "score": v.score, "threshold": v.threshold,
                      "permitted": v.permitted} for v in result.verdicts],
        "reflections": [{"day": r.day, "twin": r.twin, "text": r.text, "ratings": r.ratings}
                        for r in result.reflections],
        "events": [
            {"day": e.day, "twin": e.twin, "rung": e.rung.value, "target": e.target, "say": e.say,
             "standing_before": e.standing_before, "standing_after": e.standing_after, "place": e.place}
            for e in result.events
        ],
    }


def serialize_simulation(sim: Simulation, woman: str = demo.WOMAN, men: list[str] | None = None,
                         matched: frozenset[str] | None = None) -> dict:
    men = demo.MEN if men is None else men
    scores = score(list(sim.records), woman, men)
    runs = [{"run_id": r.spec.run_id, "model": r.spec.model, "price": r.spec.price.value, "seed": r.spec.seed,
             "wall_seconds": round(r.wall_seconds, 2), "error": r.error,
             "result": serialize(r.result) if r.result else None} for r in sim.records]
    ranking = [{"candidate": c.candidate, "price": c.price.value if c.price else None, "breakouts": c.breakouts,
                "runs": c.runs, "ci_low": c.ci_low, "ci_high": c.ci_high,
                "by_price": {p: list(v) for p, v in c.breakouts_by_price.items()}}
               for c in scores]
    answer_key = None
    if matched is not None:
        check = pool_lib.check_ranking(scores, matched)
        answer_key = {"matched": sorted(matched), "matched_ranks": check.matched_ranks,
                      "other_ranks": check.other_ranks, "matches_on_top": check.matches_on_top,
                      "pairs_in_order": check.pairs_in_order}
    return {"wall_seconds": round(sim.wall_seconds, 2), "runs": runs, "ranking": ranking,
            "scored_runs": len(sim.scorable), "woman": woman, "answer_key": answer_key,
            "result": runs[0]["result"] if runs else None}  # first run kept for the single-result page


def create_app(store: SimulationStore | None = None, log_runs: bool = False) -> FastAPI:
    app = FastAPI(title="dj_is_hung API")
    app.state.log_runs = log_runs
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
    def start_simulation(req: StartSimulation) -> dict:
        sim_id = uuid.uuid4().hex[:12]
        specs = plan(req.models, req.prices, req.seeds)
        try:
            pool = pool_lib.resolve(req.pool_iid, dates)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        twins, personas, woman, men, matched = pool.twins, pool.personas, pool.woman, pool.men, pool.matched
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
        app.state.store.save(sim_id, record)
        store = app.state.store

        def stream(spec: RunSpec):
            cursor = feed.FeedCursor(spec.run_id)
            return lambda item, word: store.add_events(sim_id, [cursor(item, word).to_dict()])

        def run() -> dict:
            try:
                return finish()
            except Exception as e:  # a background failure must not leave the record "running" forever
                failed = record | {"status": "failed", "error": f"{type(e).__name__}: {e}"}
                store.save(sim_id, failed)
                if not req.background:
                    raise
                return failed

        def finish() -> dict:
            # Runs fan out on local threads for now; A3 moves the same RunSpecs to Cloud Run Job tasks.
            sim = run_simulation(specs, twins,
                                 lambda spec: demo.make_twin_model(spec, personas, fake_scenario=req.scenario),
                                 featured=stream, max_days=req.max_days)
            done = record | {"status": "done", "pool_iid": req.pool_iid,
                             **serialize_simulation(sim, woman, men, matched)}
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

    @app.get("/simulations/{sim_id}")
    def get_simulation(sim_id: str) -> dict:
        record = app.state.store.get(sim_id)
        if record is None:
            raise HTTPException(404, "simulation not found")
        return record

    return app


app = create_app(log_runs=True)  # the served app logs every simulation; tests don't
