# Event contract

Every twin action and every Coordinator announcement in a run becomes one **FeedEvent**. The featured run's events stream the moment they happen; every run's events are also saved for replay when it finishes. Defined in `garden/feed.py` (`FeedEvent`, `SCHEMA`, `validate`); this page is the human-readable copy for viewer work.

- **Live** (featured run): `GET /simulations/{id}/events?after=<last seq>`. In Firestore they live in `simulations/{id}/events`.
- **Replay** (any finished run): `GET /replays` lists saved runs (newest simulation first); `GET /replays/{sim_id}/{run_id}` returns the run's `events` (this contract), its evening snapshots (`twin_states`, as `GET /simulations/{id}/twins`), and its outcome. Replays are files under `data/replays/` and never re-run anything.

| Field | Type | Meaning |
| --- | --- | --- |
| `run_id` | string | The run (live: the featured run, the first one) |
| `seq` | int | 0, 1, 2… with no gaps: the cursor for polling |
| `day` | int | Simulated day, from 1 |
| `tick` | int | Order within the day |
| `twin` | string \| null | Who acted; `null` for an announcement |
| `place` | string \| null | `home`, `cafe`, `park`, `gathering_hall`, `coordinator_office`, `the_wall`; `null` for announcements |
| `rung` | string \| null | `talk`, `go_to`, `reflect`, `seek_out`, `check_device`, `propose_leaving`, `go_beyond_wall` |
| `target` | string \| null | Who the action was aimed at |
| `emoji` | string | Status emoji for the sprite (📣 for announcements) |
| `say` | string | The twin's line (empty if none; a line out of character is never streamed: that turn is `reflect`) |
| `standing` | string | The twin's Standing in words after the action; empty when Standing isn't in play |
| `announcement` | string \| null | The Coordinator's words |
| `announcement_kind` | string \| null | `paired`, `ended`, `shortened`, `changed`, `gathering`, `rumour`, `wall_open` (everyone has had a date; leaving is offered from now on): timeline markers |
| `line` | string | Ready-made feed sentence, e.g. "Day 6: Mara sought out Ren at the gathering." |

**Ordering:** a day's start-of-day announcements come first, then each action in the order twins acted, each followed by any announcement it caused (e.g. "changed" after a device check). Private things never stream: wall decisions are only visible as actions, and reflections aren't streamed.
