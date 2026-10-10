"""HTTP API: start a simulation and read its result."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from garden import demo
from garden.batch import PriceLevel, Simulation, plan, run_simulation

from .store import SimulationStore, default_store


class StartSimulation(BaseModel):
    """models x price levels x seeds runs. 'fake:*' models are scripted (no API calls)."""

    scenario: Literal["breakout", "unrequited", "timeout", "excluded"] = "breakout"  # for fake models
    models: list[str] = demo.FAKE_MODELS
    prices: list[PriceLevel] = list(PriceLevel)
    seeds: list[int] = [0, 1]
    max_days: int = 10


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


def serialize_simulation(sim: Simulation) -> dict:
    runs = [{"run_id": r.spec.run_id, "model": r.spec.model, "price": r.spec.price.value, "seed": r.spec.seed,
             "wall_seconds": round(r.wall_seconds, 2), "error": r.error,
             "result": serialize(r.result) if r.result else None} for r in sim.records]
    return {"wall_seconds": round(sim.wall_seconds, 2), "runs": runs,
            "result": runs[0]["result"] if runs else None}  # first run kept for the single-result page


def create_app(store: SimulationStore | None = None) -> FastAPI:
    app = FastAPI(title="dj_is_hung API")
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

    @app.post("/simulations", status_code=201)
    def start_simulation(req: StartSimulation) -> dict:
        sim_id = uuid.uuid4().hex[:12]
        specs = plan(req.models, req.prices, req.seeds)
        record = {
            "id": sim_id,
            "status": "running",
            "scenario": req.scenario,
            "runs_planned": len(specs),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        app.state.store.save(sim_id, record)
        # Runs fan out on local threads for now; A3 moves the same RunSpecs to Cloud Run Job tasks.
        sim = run_simulation(specs, demo.POOL, lambda spec: demo.make_twin_model(spec, fake_scenario=req.scenario),
                             max_days=req.max_days)
        record |= {"status": "done", **serialize_simulation(sim)}
        app.state.store.save(sim_id, record)
        return record

    @app.get("/simulations/{sim_id}")
    def get_simulation(sim_id: str) -> dict:
        record = app.state.store.get(sim_id)
        if record is None:
            raise HTTPException(404, "simulation not found")
        return record

    return app


app = create_app()
