"use client";

import { useState } from "react";

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

type Simulation = {
  id: string;
  status: "running" | "done";
  runs?: { run_id: string }[];
  wall_seconds?: number;
  ranking?: Ranked[];
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
  const [sim, setSim] = useState<Simulation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true);
    setError(null);
    setSim(null);
    try {
      const res = await fetch(`${API_URL}/simulations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario }),
      });
      if (!res.ok) throw new Error(`API returned ${res.status}`);
      setSim(await res.json());
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
      <p className="lede">Two twins, Mara and Ren, live in the Garden. Will they cross the wall together?</p>

      <div className="controls">
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
          <p className="meta">
            Scored on her twin&apos;s willingness only. Excluded runs are not counted.
            {sim.wall_seconds !== undefined && ` ${sim.runs?.length ?? 0} runs in ${sim.wall_seconds}s.`}
          </p>
        </section>
      )}
    </main>
  );
}
