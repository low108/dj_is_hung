"use client";

import { onAuthStateChanged, type User } from "firebase/auth";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Progress } from "./garden/GardenMap";
import Timeline, { isWallCrossing } from "./garden/Timeline";
import TwinPanel, { type TwinState } from "./garden/TwinPanel";
import { API_URL, ApiError, authedFetch, firebaseAuth } from "./firebase";

// Phaser touches `window`, so the map only loads in the browser.
const GardenMap = dynamic(() => import("./garden/GardenMap"), { ssr: false });


type Scenario = "breakout" | "unrequited" | "timeout" | "excluded";

type SimEvent = { day: number; twin: string; rung: string; target: string | null; say: string };

type Price = "low" | "high";

const PRICE_LABEL: Record<Price, string> = {
  high: "Gave up a lot (high price)",
  low: "Only when it cost little (low price)",
};

type Ranked = {
  candidate: string;
  price: Price | null;
  breakouts: number;
  runs: number;
  ci_low: number;
  ci_high: number;
};

type FeedEvent = {
  seq: number;
  day: number;
  twin: string | null;
  place: string | null;
  rung: string | null;
  target: string | null;
  announcement_kind: string | null;
  emoji: string;
  say: string;
  line: string;
  announcement: string | null;
};

type CandidateHighlights = {
  candidate: string;
  pattern: string;
  highlights: {
    run_id: string;
    price: Price;
    day: number;
    kind: string;
    from_her: boolean;
    caption: string;
    label: string;
  }[];
  source: "model" | "template";
};

const TOAST_MS = 4000;
const MY_TWIN = "me"; // the Pool picker's value for the signed-in user's own twin
const SPEEDS = [1, 2, 4];
const START: Progress = { day: 0, seq: -1, caughtUp: false };

type Outcome = {
  outcome: "breakout" | "timeout" | "excluded";
  breach?: { day: number; twin: string; phrase: string } | null;
  day: number;
  pair: [string, string] | null;
  unrequited: { day: number; twin: string; target: string }[];
};

/** A saved run, as the run picker lists it (GET /replays). */
type ReplaySummary = {
  sim_id: string;
  run_id: string;
  model: string;
  price: Price;
  seed: number;
  scenario: Scenario | null;
  featured: boolean;
  outcome: Outcome["outcome"];
  day: number;
  created_at: string;
};

type Replay = ReplaySummary & Outcome & { twins: string[]; events: FeedEvent[]; twin_states: TwinState[] };

const replayKey = (r: { sim_id: string; run_id: string }) => `${r.sim_id}/${r.run_id}`;
const modelName = (model: string) => model.split(":")[1] ?? model;

/** The run picker's filters: model × price level × scenario ("" = any). */
type ReplayFilter = { model: string; price: string; scenario: string };
const ANY: ReplayFilter = { model: "", price: "", scenario: "" };
const scenarioOf = (r: ReplaySummary) => r.scenario ?? "live";
const matches = (r: ReplaySummary, f: ReplayFilter) =>
  (!f.model || r.model === f.model) && (!f.price || r.price === f.price) && (!f.scenario || scenarioOf(r) === f.scenario);
const distinct = (values: string[]) => [...new Set(values)].sort();

function replayLabel(r: ReplaySummary): string {
  const when = new Date(r.created_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
  const model = r.scenario ? `scripted (${r.scenario})` : modelName(r.model);
  const mark = r.outcome === "breakout" ? "★ breakout" : r.outcome;
  return `${when} · ${model} · ${r.price} price · seed ${r.seed} · ${mark} day ${r.day}`;
}

type Simulation = {
  id: string;
  status: "running" | "done" | "failed";
  error?: string;
  featured_run?: string;
  twins?: string[];
  runs?: { run_id: string; result: (Outcome & { events: SimEvent[] }) | null }[];
  wall_seconds?: number;
  ranking?: Ranked[];
  woman?: string;
  answer_key?: {
    matched: string[];
    matches_on_top: boolean;
    pairs_in_order: number;
  } | null;
  scored_runs?: number;
  highlights?: CandidateHighlights[];
  result?: Outcome & { events: SimEvent[] };
};

const pct = (x: number) => `${Math.round(x * 100)}%`;

const priceLabel = (r: Ranked): string => (r.price ? PRICE_LABEL[r.price] : "No breakout");

function headline(r: Outcome | undefined): string {
  if (!r) return "Running…";
  if (r.outcome === "excluded" && r.breach)
    return `Excluded: ${r.breach.twin} broke immersion on day ${r.breach.day} ("${r.breach.phrase}") — not scored`;
  if (r.outcome === "breakout") return `Breakout on day ${r.day}: ${r.pair?.join(" and ")} crossed the wall together`;
  if (r.unrequited.length > 0) {
    const a = r.unrequited[0];
    return `Unrequited: ${a.twin} headed for the wall on day ${a.day}, but ${a.target} didn't follow`;
  }
  return `Timeout: no one crossed the wall in ${r.day} days`;
}

export default function Home() {
  const [scenario, setScenario] = useState<Scenario>("breakout");
  const [poolIid, setPoolIid] = useState<string>("");
  const [model, setModel] = useState<string>("fake");
  const [pools, setPools] = useState<{ iid: number; matches: number; dates: number }[]>([]);

  // A signed-in user with a twin can put her twin in the Garden ("My twin" pool).
  const [user, setUser] = useState<User | null>(null);
  const [myTwin, setMyTwin] = useState<{ alias: string; reviewed: boolean } | null>(null);
  useEffect(() => onAuthStateChanged(firebaseAuth(), setUser), []);
  useEffect(() => {
    setMyTwin(null);
    if (!user) return;
    let stale = false;
    authedFetch<{ alias: string; reviewed: boolean }>(user, "/me/twin")
      .then((t) => !stale && setMyTwin(t))
      .catch((e) => !(e instanceof ApiError && e.status === 404) && console.warn("couldn't load your twin", e));
    return () => {
      stale = true;
    };
  }, [user]);

  // Signed out, or no reviewed twin: "My twin" can't stay selected.
  useEffect(() => {
    if (!myTwin?.reviewed) setPoolIid((p) => (p === MY_TWIN ? "" : p));
  }, [myTwin]);

  useEffect(() => {
    fetch(`${API_URL}/pools`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setPools)
      .catch(() => setPools([])); // no dataset downloaded: only the demo pool is offered
  }, []);
  const [sim, setSim] = useState<Simulation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedEvents, setFeedEvents] = useState<FeedEvent[]>([]);
  const [featuredRun, setFeaturedRun] = useState<string | null>(null);
  const [twinNames, setTwinNames] = useState<string[]>([]);
  const [simId, setSimId] = useState<string | null>(null);
  const [twinStates, setTwinStates] = useState<TwinState[]>([]); // every evening, for the panel
  const [selected, setSelected] = useState<string | null>(null);
  const [toasts, setToasts] = useState<{ seq: number; text: string }[]>([]);
  const [progress, setProgress] = useState<Progress>(START);
  const [replays, setReplays] = useState<ReplaySummary[]>([]);
  const [picked, setPicked] = useState("");
  const [filter, setFilter] = useState<ReplayFilter>(ANY);
  const replayRequest = useRef(0); // only the latest replay request may fill the view
  const [replaying, setReplaying] = useState<Replay | null>(null);
  // What the map is showing: a fresh map (React key) per simulation, replay or jump.
  const [view, setView] = useState({ source: "none", startAt: 0, nonce: 0 });
  const showView = (source: string, startAt = 0) => setView({ source, startAt, nonce: Date.now() });
  const [speed, setSpeed] = useState(1);
  const [paused, setPaused] = useState(false);
  const toastTimers = useRef<number[]>([]);

  async function loadReplays() {
    try {
      const res = await fetch(`${API_URL}/replays`);
      if (res.ok) setReplays(await res.json());
    } catch {
      setReplays([]);
    }
  }
  useEffect(() => {
    loadReplays();
  }, []);

  function clearToasts() {
    toastTimers.current.forEach((t) => window.clearTimeout(t));
    toastTimers.current = [];
    setToasts([]);
  }
  useEffect(() => clearToasts, []);

  function dismissLater(seq: number) {
    toastTimers.current.push(
      window.setTimeout(() => setToasts((old) => old.filter((t) => t.seq !== seq)), TOAST_MS / speed),
    );
  }

  function toast(event: { seq: number; announcement: string | null }) {
    if (!event.announcement) return;
    const item = { seq: event.seq, text: event.announcement };
    setToasts((old) => [...old, item].slice(-3));
    dismissLater(item.seq);
  }

  // Toasts wait while playback is paused, then get a fresh few seconds.
  function togglePause() {
    toastTimers.current.forEach((t) => window.clearTimeout(t));
    toastTimers.current = [];
    if (paused) toasts.forEach((t) => dismissLater(t.seq));
    setPaused(!paused);
  }

  // The panel follows the map, not the API: the last evening before the day the map is playing
  // (or the final evening once playback has caught up with a finished run).
  function panelState(twin: string): TwinState | undefined {
    const done = !busy && progress.caughtUp;
    return twinStates
      .filter((s) => s.twin === twin && (done ? s.day <= progress.day : s.day < progress.day))
      .sort((a, b) => b.day - a.day)[0];
  }

  async function follow(id: string) {
    // Poll the featured run's events and the simulation until it's done (Firestore listeners later).
    let after = -1;
    for (;;) {
      const [eventsRes, simRes, twinsRes] = await Promise.all([
        fetch(`${API_URL}/simulations/${id}/events?after=${after}`),
        fetch(`${API_URL}/simulations/${id}`),
        fetch(`${API_URL}/simulations/${id}/twins`),
      ]);
      const fresh: FeedEvent[] = eventsRes.ok ? await eventsRes.json() : [];
      if (fresh.length) {
        after = fresh[fresh.length - 1].seq;
        setFeedEvents((old) => [...old, ...fresh]);
      }
      if (twinsRes.ok) setTwinStates(await twinsRes.json());
      if (!simRes.ok) throw new Error(`API returned ${simRes.status} while following the simulation`);
      const current: Simulation = await simRes.json();
      if (current.status === "failed") throw new Error(current.error ?? "the simulation failed");
      if (current.status === "done") {
        setSim(current);
        return;
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
  }

  function resetView() {
    setError(null);
    setSim(null);
    setReplaying(null);
    setFeedEvents([]);
    setFeaturedRun(null);
    setTwinNames([]);
    setSimId(null);
    setTwinStates([]);
    setSelected(null);
    setProgress(START);
    setView({ source: "none", startAt: 0, nonce: 0 });
    setPaused(false);
    clearToasts();
  }

  /** Restart the map at an event, with everyone where they were just before it. */
  function jump(seq: number) {
    clearToasts();
    setProgress({ day: feedEvents.find((e) => e.seq === seq)?.day ?? 0, seq: seq - 1, caughtUp: false });
    setPaused(false);
    showView(view.source, seq);
  }

  /** Plays a saved run from its stored events: nothing is simulated and no model is called. */
  async function playReplay(key: string) {
    if (!key) return;
    const request = ++replayRequest.current;
    resetView();
    try {
      const res = await fetch(`${API_URL}/replays/${key}`);
      if (!res.ok) throw new Error(`API returned ${res.status} for replay ${key}`);
      const r: Replay = await res.json();
      if (request !== replayRequest.current) return; // a newer pick or a live run took over
      setReplaying(r);
      setFeaturedRun(r.run_id);
      setTwinNames(r.twins);
      setFeedEvents(r.events);
      setTwinStates(r.twin_states);
      showView(`replay:${key}`); // choosing the same run again restarts it
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function replayLast() {
    const newest = replays[0];
    if (!newest) return;
    const last = replays.find((r) => r.sim_id === newest.sim_id && r.featured) ?? newest;
    setPicked(replayKey(last));
    playReplay(replayKey(last));
  }

  async function start() {
    replayRequest.current++; // drop any replay still loading
    setBusy(true);
    resetView();
    try {
      const mine = poolIid === MY_TWIN;
      const auth: Record<string, string> = mine && user ? { Authorization: `Bearer ${await user.getIdToken()}` } : {};
      const res = await fetch(`${API_URL}/simulations`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({
          scenario,
          background: true,
          my_twin: mine,
          pool_iid: poolIid && !mine ? Number(poolIid) : null,
          ...(model === "fake" ? {} : { models: [model] }),
        }),
      });
      if (!res.ok) throw new Error(`API returned ${res.status}`);
      const started: Simulation = await res.json();
      setFeaturedRun(started.featured_run ?? null);
      setTwinNames(started.twins ?? []);
      setSimId(started.id);
      showView(`live:${started.id}`);
      await follow(started.id);
      await loadReplays();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const featuredResult = sim?.runs?.find((r) => r.run_id === featuredRun)?.result;
  const notable = featuredResult?.events.filter((e) => e.rung !== "talk") ?? [];
  const playedEvents = feedEvents.filter((e) => e.seq <= progress.seq); // the feed follows the map
  // Results wait for the map to finish playing (if there's no map, there's nothing to wait for).
  const playedOut = progress.caughtUp || twinNames.length === 0;
  const shown = replays.filter((r) => matches(r, filter));
  // How the run on the map ended (live: the featured run's own result, once the simulation is done).
  const shownOutcome: Outcome | null | undefined = replaying ?? featuredResult;
  const breakoutPair = shownOutcome?.outcome === "breakout" ? shownOutcome.pair : null;
  const lastDay = Math.max(shownOutcome?.day ?? 0, ...feedEvents.map((e) => e.day));

  function showBreakout() {
    if (!breakoutPair || !shownOutcome) return;
    // The final scene starts at the pair's first wall crossing on the day they broke out.
    const finalDay = feedEvents.filter((e) => e.day === shownOutcome.day);
    const crossing = finalDay.find((e) => e.twin && breakoutPair.includes(e.twin) && isWallCrossing(e));
    const at = crossing ?? finalDay[0];
    if (at) jump(at.seq);
  }

  return (
    <main className="page">
      <h1>The Garden</h1>
      <p className="lede">Twins live in the Garden. The men her twin will give up the most for come first.</p>
      <p className="meta">
        <Link href="/onboarding">Build your own twin →</Link>
      </p>

      <div className="controls">
        <label>
          Pool{" "}
          <select value={poolIid} onChange={(e) => setPoolIid(e.target.value)} aria-label="Pool">
            <option value="">Demo pool (Mara)</option>
            {myTwin && (
              <option value={MY_TWIN} disabled={!myTwin.reviewed}>
                My twin ({myTwin.alias}) with the demo men{myTwin.reviewed ? "" : " (review it first)"}
              </option>
            )}
            {pools.map((p) => (
              <option key={p.iid} value={p.iid}>
                Participant {p.iid}: {p.matches} matches of {p.dates} dates
              </option>
            ))}
          </select>
        </label>
        <label>
          Twins{" "}
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="fake">Scripted (instant)</option>
            <option value="ilmu:ilmu-mini-v3.3">ILMU (real, a few minutes)</option>
            <option value="gemini:gemini-3.5-flash">Gemini Flash (real)</option>
            <option value="gemma:gemma-4-26b-a4b-it">Gemma 4 (real)</option>
          </select>
        </label>
        <label>
          Fake-model scenario{" "}
          <select value={scenario} onChange={(e) => setScenario(e.target.value as Scenario)}>
            <option value="breakout">Breakout</option>
            <option value="unrequited">Unrequited</option>
            <option value="timeout">Timeout</option>
            <option value="excluded">Excluded (immersion broken)</option>
          </select>
        </label>
        <button onClick={start} disabled={busy}>
          {busy ? "Simulating…" : "Start simulation"}
        </button>
      </div>

      <div className="controls replays">
        {(
          [
            ["model", "Model", distinct(replays.map((r) => r.model)), modelName],
            ["price", "Price", distinct(replays.map((r) => r.price)), (v: string) => `${v} price`],
            ["scenario", "Scenario", distinct(replays.map(scenarioOf)), (v: string) => v],
          ] as const
        ).map(([key, label, options, show]) => (
          <label key={key}>
            {label}{" "}
            <select
              value={filter[key]}
              onChange={(e) => {
                setFilter({ ...filter, [key]: e.target.value });
                setPicked("");
              }}
              aria-label={`Filter by ${label.toLowerCase()}`}
            >
              <option value="">Any</option>
              {options.map((v) => (
                <option key={v} value={v}>
                  {show(v)}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label>
          Saved runs{" "}
          <select value={picked} onChange={(e) => setPicked(e.target.value)} aria-label="Saved runs" disabled={busy}>
            <option value="">{shown.length ? `Pick one of ${shown.length} runs` : "No saved runs yet"}</option>
            {shown.map((r) => (
              <option key={replayKey(r)} value={replayKey(r)}>
                {replayLabel(r)}
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => playReplay(picked)} disabled={busy || !picked}>
          Replay
        </button>
        <button onClick={replayLast} disabled={busy || !replays.length}>
          Replay last run
        </button>
      </div>

      {error && (
        <p className="error">
          Couldn&apos;t reach the API at {API_URL}: {error}
        </p>
      )}

      {twinNames.length > 0 && (
        <section className="result map">
          <div className="map-wrap">
            <GardenMap
              key={`${view.source}#${view.startAt}:${view.nonce}`}
              events={feedEvents}
              twins={twinNames}
              onSelect={setSelected}
              onAnnouncement={toast}
              onProgress={setProgress}
              speed={speed}
              paused={paused}
              catchUp={!replaying && view.startAt === 0} // after a jump the backlog is history to watch, not lag
              startAt={view.startAt}
              finale={breakoutPair}
            />
            <div className="toasts" aria-live="polite">
              {toasts.map((t) => (
                <div key={t.seq} className="toast">
                  📣 {t.text}
                </div>
              ))}
            </div>
          </div>
          <div className="playback" role="group" aria-label="Playback">
            <button onClick={togglePause} aria-pressed={paused}>
              {paused ? "▶ Play" : "⏸ Pause"}
            </button>
            {SPEEDS.map((x) => (
              <button key={x} onClick={() => setSpeed(x)} aria-pressed={speed === x} className={speed === x ? "on" : ""}>
                {x}×
              </button>
            ))}
            <span className="meta">Day {progress.day || 1}</span>
            {breakoutPair && (
              <button className="breakout" onClick={showBreakout}>
                Show me the breakout
              </button>
            )}
          </div>
          {feedEvents.length > 0 && (
            <Timeline events={feedEvents} days={lastDay} atSeq={progress.seq} atDay={progress.day} onJump={jump} />
          )}
          {selected ? (
            <TwinPanel twin={selected} state={panelState(selected)} onClose={() => setSelected(null)} />
          ) : (
            <p className="meta">Click a twin to see how they&apos;re doing.</p>
          )}
        </section>
      )}

      {playedEvents.length > 0 && (
        <section className="result feed" data-testid="feed">
          <h2>
            {replaying ? "Replay" : busy ? "Live" : "Finished"}: the Garden, run {featuredRun}
            {simId && ` (simulation ${simId})`}
          </h2>
          <ol>
            {playedEvents.map((e) => (
              <li key={e.seq} className={e.twin ? "" : "announcement"}>
                {e.emoji} {e.line}
                {e.say ? ` “${e.say}”` : ""}
              </li>
            ))}
          </ol>
        </section>
      )}

      {replaying && playedOut && (
        <section className="result" data-testid="result">
          <h2>{headline(replaying)}</h2>
          <p className="meta">
            Replay of run {replaying.run_id} from simulation {replaying.sim_id} ({replaying.model}, {replaying.price}{" "}
            price, seed {replaying.seed}). Played from stored events; nothing was simulated again.
          </p>
        </section>
      )}

      {sim && playedOut && (
        <section className="result" data-testid="result">
          <h2>{headline(shownOutcome ?? sim.result)}</h2>
          {notable.length > 0 && (
            <ol>
              {notable.map((e, i) => (
                <li key={i}>
                  Day {e.day}: {e.twin} · {e.rung.replaceAll("_", " ")}
                  {e.target ? ` → ${e.target}` : ""}
                  {e.say ? ` — “${e.say}”` : ""}
                </li>
              ))}
            </ol>
          )}
          <p className="meta">Simulation {sim.id}</p>
        </section>
      )}

      {sim?.ranking && (
        <section className="result ranking" data-testid="ranking">
          <h2>Ranking across {sim.scored_runs ?? 0} scored runs</h2>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Candidate</th>
                <th>Highest price she still broke out at</th>
                <th>Breakout rate at that price (95% range)</th>
              </tr>
            </thead>
            <tbody>
              {sim.ranking.map((r, i) => (
                <tr key={r.candidate}>
                  <td>{i + 1}</td>
                  <td>{r.candidate}</td>
                  <td>{priceLabel(r)}</td>
                  <td>
                    {r.breakouts}/{r.runs} ({pct(r.ci_low)}–{pct(r.ci_high)})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {sim.answer_key && (
            <p className={sim.answer_key.matches_on_top ? "verdict good" : "verdict"}>
              Answer key: {sim.woman}&apos;s real mutual matches were {sim.answer_key.matched.join(", ")}.{" "}
              {sim.answer_key.matches_on_top
                ? "All of them ranked above the men she didn't match with."
                : `They were ranked above the others in ${pct(sim.answer_key.pairs_in_order)} of comparisons (50% = chance).`}
            </p>
          )}
          {(sim.highlights?.length ?? 0) > 0 && (
            <div className="highlights" data-testid="highlights">
              <h3>Highlights from the Garden</h3>
              {sim.highlights!.map((c) => (
                <article key={c.candidate} className="highlight-card">
                  <h4>{c.candidate}&apos;s twin</h4>
                  <p className="pattern">{c.pattern}</p>
                  <ul>
                    {c.highlights.map((h, i) => (
                      <li key={i}>
                        <span>{h.caption}</span>
                        <span className="meta"> {h.label}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
              <p className="meta">These moments are between the twins in the simulation, not the real people.</p>
            </div>
          )}
          <p className="meta">
            Scored on her twin&apos;s willingness only. Excluded runs are not counted.
            {sim.wall_seconds !== undefined && ` ${sim.runs?.length ?? 0} runs in ${sim.wall_seconds}s.`}
          </p>
        </section>
      )}
    </main>
  );
}
