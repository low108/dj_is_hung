# Event contract

Every twin action and every Coordinator announcement in the featured run becomes one **FeedEvent**, streamed the moment it happens. Defined in `garden/feed.py` (`FeedEvent`, `SCHEMA`, `validate`); this page is the human-readable copy for viewer work.

Read them with `GET /simulations/{id}/events?after=<last seq>`. In Firestore they live in `simulations/{id}/events`.

| Field | Type | Meaning |
| --- | --- | --- |
| `run_id` | string | The featured run (the first high-price run) |
| `seq` | int | 0, 1, 2… with no gaps: the cursor for polling |
| `day` | int | Simulated day, from 1 |
| `tick` | int | Order within the day |
| `twin` | string \| null | Who acted; `null` for an announcement |
| `place` | string \| null | `home`, `cafe`, `park`, `gathering_hall`, `coordinator_office`, `the_wall`; `null` for announcements |
| `rung` | string \| null | `talk`, `go_to`, `reflect`, `seek_out`, `check_device`, `propose_leaving`, `go_beyond_wall` |
| `target` | string \| null | Who the action was aimed at |
| `emoji` | string | Status emoji for the sprite (📣 for announcements) |
| `say` | string | The twin's line (empty if none, or if it broke immersion) |
| `standing` | string | The twin's Standing in words after the action; empty when Standing isn't in play |
| `announcement` | string \| null | The Coordinator's words |
| `announcement_kind` | string \| null | `paired`, `ended`, `shortened`, `changed`, `gathering`, `rumour`: timeline markers |
| `line` | string | Ready-made feed sentence, e.g. "Day 6: Mara sought out Ren at the gathering." |

**Ordering:** a day's start-of-day announcements come first, then each action in the order twins acted, each followed by any announcement it caused (e.g. "changed" after a device check). Private things never stream: wall decisions are only visible as actions, and reflections aren't streamed.
