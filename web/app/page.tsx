"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import type { Progress } from "./garden/GardenMap";
import TwinPanel, { type TwinState } from "./garden/TwinPanel";

// Phaser touches `window`, so the map only loads in the browser.
const GardenMap = dynamic(() => import("./garden/GardenMap"), { ssr: false });

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

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
  emoji: string;
  say: string;
  line: string;
  announcement: string | null;
};

const TOAST_MS = 4000;
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

function replayLabel(r: ReplaySummary): string {
  const when = new Date(r.created_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
  const model = r.model.startsWith("fake:") ? `scripted (${r.scenario ?? "?"})` : r.model.split(":")[1] ?? r.model;
  const mark = r.outcome === "breakout" ? "★ breakout" : r.outcome;
  return `${when} · ${model} · ${r.price} price · seed ${r.seed} · ${mark} day ${r.day}`;
}

type Simulation = {
  id: string;
  status: "running" | "done" | "failed";
  error?: string;
  featured_run?: string;
  twins?: string[];
  runs?: { run_id: string }[];
  wall_seconds?: number;
  ranking?: Ranked[];
  woman?: string;
  answer_key?: {
    matched: string[];
    matches_on_top: boolean;
    pairs_in_order: number;
  } | null;
  scored_runs?: number;
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
  const [replaying, setReplaying] = useState<Replay | null>(null);
  const [viewKey, setViewKey] = useState("none"); // a fresh map per simulation or replay
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

  function toast(event: { seq: number; announcement: string | null }) {
    if (!event.announcement) return;
    const item = { seq: event.seq, text: event.announcement };
    setToasts((old) => [...old, item].slice(-3));
    toastTimers.current.push(
      window.setTimeout(() => setToasts((old) => old.filter((t) => t.seq !== item.seq)), TOAST_MS / speed),
    );
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
    setPaused(false);
    clearToasts();
  }

  /** Plays a saved run from its stored events: nothing is simulated and no model is called. */
  async function playReplay(key: string) {
    if (!key) return;
    resetView();
    try {
      const res = await fetch(`${API_URL}/replays/${key}`);
      if (!res.ok) throw new Error(`API returned ${res.status} for replay ${key}`);
      const r: Replay = await res.json();
      setReplaying(r);
      setFeaturedRun(r.run_id);
      setTwinNames(r.twins);
      setFeedEvents(r.events);
      setTwinStates(r.twin_states);
      setViewKey(`replay:${key}:${Date.now()}`); // choosing the same run again restarts it
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
    setBusy(true);
    resetView();
    try {
      const res = await fetch(`${API_URL}/simulations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario,
          background: true,
          pool_iid: poolIid ? Number(poolIid) : null,
          ...(model === "fake" ? {} : { models: [model] }),
        }),
      });
      if (!res.ok) throw new Error(`API returned ${res.status}`);
      const started: Simulation = await res.json();
      setFeaturedRun(started.featured_run ?? null);
      setTwinNames(started.twins ?? []);
      setSimId(started.id);
      setViewKey(`live:${started.id}`);
      await follow(started.id);
      await loadReplays();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const notable = sim?.result?.events.filter((e) => e.rung !== "talk") ?? [];
  const played = feedEvents.filter((e) => e.seq <= progress.seq); // the feed follows the map

  return (
    <main className="page">
      <h1>The Garden</h1>
      <p className="lede">Twins live in the Garden. The men her twin will give up the most for come first.</p>

      <div className="controls">
        <label>
          Pool{" "}
          <select value={poolIid} onChange={(e) => setPoolIid(e.target.value)} aria-label="Pool">
            <option value="">Demo pool (Mara)</option>
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
        <label>
          Saved runs{" "}
          <select value={picked} onChange={(e) => setPicked(e.target.value)} aria-label="Saved runs" disabled={busy}>
            <option value="">{replays.length ? "Pick a run to replay" : "No saved runs yet"}</option>
            {replays.map((r) => (
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
              key={viewKey}
              events={feedEvents}
              twins={twinNames}
              onSelect={setSelected}
              onAnnouncement={toast}
              onProgress={setProgress}
              speed={speed}
              paused={paused}
              catchUp={!replaying}
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
            <button onClick={() => setPaused((p) => !p)} aria-pressed={paused}>
              {paused ? "▶ Play" : "⏸ Pause"}
            </button>
            {SPEEDS.map((x) => (
              <button key={x} onClick={() => setSpeed(x)} aria-pressed={speed === x} className={speed === x ? "on" : ""}>
                {x}×
              </button>
            ))}
            <span className="meta">Day {progress.day || 1}</span>
          </div>
          {selected ? (
            <TwinPanel twin={selected} state={panelState(selected)} onClose={() => setSelected(null)} />
          ) : (
            <p className="meta">Click a twin to see how they&apos;re doing.</p>
          )}
        </section>
      )}

      {played.length > 0 && (
        <section className="result feed" data-testid="feed">
          <h2>
            {replaying ? "Replay" : busy ? "Live" : "Finished"}: the Garden, run {featuredRun}
            {simId && ` (simulation ${simId})`}
          </h2>
          <ol>
            {played.map((e) => (
              <li key={e.seq} className={e.twin ? "" : "announcement"}>
                {e.emoji} {e.line}
                {e.say ? ` “${e.say}”` : ""}
              </li>
            ))}
          </ol>
        </section>
      )}

      {replaying && progress.caughtUp && (
        <section className="result" data-testid="result">
          <h2>{headline(replaying)}</h2>
          <p className="meta">
            Replay of run {replaying.run_id} from simulation {replaying.sim_id} ({replaying.model}, {replaying.price}{" "}
            price, seed {replaying.seed}). Played from stored events; nothing was simulated again.
          </p>
        </section>
      )}

      {sim && progress.caughtUp && (
        <section className="result" data-testid="result">
          <h2>{headline(sim.result)}</h2>
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
          <p className="meta">
            Scored on her twin&apos;s willingness only. Excluded runs are not counted.
            {sim.wall_seconds !== undefined && ` ${sim.runs?.length ?? 0} runs in ${sim.wall_seconds}s.`}
          </p>
        </section>
      )}
    </main>
  );
}
