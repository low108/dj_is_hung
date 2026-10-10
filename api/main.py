"""HTTP API: start a simulation and read its result."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from garden import Twin, WorldConfig, run_world, scenario

from .store import SimulationStore, default_store

WOMAN, MAN = "Mara", "Ren"  # tracer-bullet twins; real twins arrive with D1/D4


class StartSimulation(BaseModel):
    scenario: Literal["breakout", "unrequited", "timeout"] = "breakout"
    max_days: int = 10
    seed: int = 0


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
        config = WorldConfig(twins=(Twin(WOMAN), Twin(MAN)), max_days=req.max_days, seed=req.seed)
        record = {
            "id": sim_id,
            "status": "running",
            "scenario": req.scenario,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        app.state.store.save(sim_id, record)
        # A1 runs locally and synchronously; A3 moves this into a Cloud Run Job.
        result = run_world(config, scenario(req.scenario, WOMAN, MAN))
        record |= {"status": "done", "result": serialize(result)}
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
