# dj_is_hung

Breakout Matching prototype, inspired by Black Mirror's "Hang the DJ". AI twins live in a simulated Garden; a pair is a match only when both twins choose to cross the wall together. The full plan is in the spec issue (#1).

## Layout

| Folder | What it is |
| --- | --- |
| `garden/` | The simulation engine. Seam: `run_world(config, model) -> RunResult` |
| `api/` | FastAPI service: `POST /simulations`, `GET /simulations/{id}` |
| `web/` | Next.js web app |
| `tests/` | Pytest tests, driven by the scripted fake model |

## Run locally

Needs Node 20+, [uv](https://docs.astral.sh/uv/) and Java (for the Firestore emulator).

```bash
make install
```

Then, each in its own terminal:

```bash
make emulator   # Firestore emulator on :8080, UI on :4000
make api        # API on :8001
make web        # web app on :3000
```

Open the web app, pick a fake-model scenario and click **Start simulation**.

- Without the emulator, start the API with `uv run uvicorn api.main:app --port 8001`; it keeps records in memory instead.
- If the API runs elsewhere, set `NEXT_PUBLIC_API_URL` in `web/.env.local`.
- Ports can be changed with `make api API_PORT=…` and `cd web && npm run dev -- -p …`.

## Test

```bash
make test
```

## Real models (Gemini / Gemma)

Twins run as Concordia agents (`garden/concordia_twins.py`) on the Gemini API. Put your key in `.env` (git-ignored):

```
GEMINI_API_KEY=...
GEMINI_RPM=5   # only on the free tier: paces requests to 5 per minute per model
```

Measure one real run (calls, tokens, model time, and a projection for a 10-day run):

```bash
uv run python scripts/measure_run.py --model gemini-3.5-flash-lite --men 2 --days 2
```

The free tier allows about 5 requests per minute and 20 per day per model, which is enough for a small measurement but not for demo-sized simulations. Those need billing enabled on the key's Google Cloud project.
