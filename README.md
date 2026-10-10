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
