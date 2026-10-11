"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

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
};

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
  result?: {
    outcome: "breakout" | "timeout" | "excluded";
    breach?: { day: number; twin: string; phrase: string } | null;
    day: number;
    pair: [string, string] | null;
    unrequited: { day: number; twin: string; target: string }[];
    events: SimEvent[];
  };
};

const pct = (x: number) => `${Math.round(x * 100)}%`;

const priceLabel = (r: Ranked): string => (r.price ? PRICE_LABEL[r.price] : "No breakout");

function headline(sim: Simulation): string {
  const r = sim.result;
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

  async function follow(id: string) {
    // Poll the featured run's events and the simulation until it's done (Firestore listeners later).
    let after = -1;
    for (;;) {
      const [eventsRes, simRes] = await Promise.all([
        fetch(`${API_URL}/simulations/${id}/events?after=${after}`),
        fetch(`${API_URL}/simulations/${id}`),
      ]);
      const fresh: FeedEvent[] = eventsRes.ok ? await eventsRes.json() : [];
      if (fresh.length) {
        after = fresh[fresh.length - 1].seq;
        setFeedEvents((old) => [...old, ...fresh]);
      }
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

  async function start() {
    setBusy(true);
    setError(null);
    setSim(null);
    setFeedEvents([]);
    setFeaturedRun(null);
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
      await follow(started.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const notable = sim?.result?.events.filter((e) => e.rung !== "talk") ?? [];

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

      {error && (
        <p className="error">
          Couldn&apos;t reach the API at {API_URL}: {error}
        </p>
      )}

      {twinNames.length > 0 && (
        <section className="result map">
          <GardenMap events={feedEvents} twins={twinNames} />
        </section>
      )}

      {feedEvents.length > 0 && (
        <section className="result feed" data-testid="feed">
          <h2>
            {busy ? "Live" : "Finished"}: the Garden, run {featuredRun}
          </h2>
          <ol>
            {feedEvents.map((e) => (
              <li key={e.seq} className={e.twin ? "" : "announcement"}>
                {e.emoji} {e.line}
                {e.say ? ` “${e.say}”` : ""}
              </li>
            ))}
          </ol>
        </section>
      )}

      {sim && (
        <section className="result" data-testid="result">
          <h2>{headline(sim)}</h2>
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
