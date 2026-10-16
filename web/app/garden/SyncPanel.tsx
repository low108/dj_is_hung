"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { measure, step, type Pair, type SyncEvent } from "./sync";

const W = 520;
const H = 190;
const R = 58;
const HER = { x: 150, y: 96 };
const HIM = { x: 370, y: 96 };

const at = (c: { x: number; y: number }, theta: number) => ({ x: c.x + R * Math.cos(theta), y: c.y + R * Math.sin(theta) });

/** Her and one man as two coupled rhythms (garden/sync.ts): two circles, a point turning on each at its
 * own speed and pulled by the other. Locked, the points travel together a fixed gap apart; not locked,
 * they drift. The numbers are measured from the run up to the moment playing. */
export default function SyncPanel({ events, her, atSeq }: { events: SyncEvent[]; her: string; atSeq: number }) {
  const pairs = useMemo(() => measure(events, her, atSeq), [events, her, atSeq]);
  const [chosen, setChosen] = useState<string | null>(null);
  const pair: Pair | undefined = pairs.find((p) => p.man === chosen) ?? pairs[0];
  const pairRef = useRef(pair);
  pairRef.current = pair;
  const dots = useRef<{ her: SVGCircleElement | null; him: SVGCircleElement | null; tie: SVGLineElement | null }>({
    her: null,
    him: null,
    tie: null,
  });

  useEffect(() => {
    let t1 = 0;
    let t2 = Math.PI; // start opposite, so you can watch them find each other
    let last = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const p = pairRef.current;
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (p) [t1, t2] = step(t1, t2, p, dt);
      const [a, b] = [at(HER, t1), at(HIM, t2)];
      const d = dots.current;
      d.her?.setAttribute("cx", `${a.x}`);
      d.her?.setAttribute("cy", `${a.y}`);
      d.him?.setAttribute("cx", `${b.x}`);
      d.him?.setAttribute("cy", `${b.y}`);
      d.tie?.setAttribute("x1", `${a.x}`);
      d.tie?.setAttribute("y1", `${a.y}`);
      d.tie?.setAttribute("x2", `${b.x}`);
      d.tie?.setAttribute("y2", `${b.y}`);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [pair?.man]);

  if (!pair) return null;
  const f = (x: number) => x.toFixed(2);
  return (
    <section className="sync" aria-label="In sync?">
      <div className="sync-head">
        <h3>In sync?</h3>
        <span className="meta">two rhythms, each pulled by the other (the Kuramoto model)</span>
      </div>
      <div className="sync-men" role="tablist" aria-label="Choose a man">
        {pairs.map((p) => (
          <button
            key={p.man}
            role="tab"
            aria-selected={p.man === pair.man}
            className={`sync-man${p.man === pair.man ? " on" : ""}`}
            onClick={() => setChosen(p.man)}
            title={`${her} approached ${p.man} ${p.approaches} time(s) when she could choose anyone`}
          >
            {p.locked ? "🔗" : "〰️"} {p.man}
            {p.approaches > 0 && <sub>{p.approaches}</sub>}
          </button>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="sync-svg" role="img" aria-label={`${her} and ${pair.man}: ${pair.locked ? "locked" : "drifting"}`}>
        <defs>
          <linearGradient id="sync-band" x1="0" x2="1">
            <stop offset="0" stopColor="#e8a24a" stopOpacity="0.35" />
            <stop offset="1" stopColor="#5b9be0" stopOpacity="0.35" />
          </linearGradient>
        </defs>
        <rect x={HER.x} y={HER.y - R} width={HIM.x - HER.x} height={R * 2} fill="url(#sync-band)" opacity={pair.locked ? 0.5 : 0.18} />
        <circle cx={HER.x} cy={HER.y} r={R} className="ring her" />
        <circle cx={HIM.x} cy={HIM.y} r={R} className="ring him" />
        <line ref={(el) => void (dots.current.tie = el)} className={`tie${pair.locked ? " locked" : ""}`} />
        <circle ref={(el) => void (dots.current.her = el)} r={6} className="dot her" />
        <circle ref={(el) => void (dots.current.him = el)} r={6} className="dot him" />
        <text x={HER.x} y={H - 8} textAnchor="middle" className="who">
          {her}
        </text>
        <text x={HIM.x} y={H - 8} textAnchor="middle" className="who">
          {pair.man}
        </text>
      </svg>
      <div className="sync-math">
        <code>
          θ̇₁ = {f(pair.omegaHer)} + {f(pair.kHer)}·sin(θ₂ − θ₁)
        </code>
        <code>
          θ̇₂ = {f(pair.omegaHim)} + {f(pair.kHim)}·sin(θ₁ − θ₂)
        </code>
        <p className={`sync-verdict${pair.locked ? " locked" : ""}`}>
          {pair.locked ? (
            <>
              🔗 Locked: |ω₁ − ω₂| = {f(Math.abs(pair.omegaHer - pair.omegaHim))} ≤ K₁ + K₂ = {f(pair.kHer + pair.kHim)}. They move
              together at Ω = {f(pair.common!)}, {Math.abs(pair.gap!).toFixed(0)}° apart: still two people.
            </>
          ) : (
            <>
              〰️ Drifting: |ω₁ − ω₂| = {f(Math.abs(pair.omegaHer - pair.omegaHim))} &gt; K₁ + K₂ = {f(pair.kHer + pair.kHim)}. Their
              rhythms are too far apart for how little they pull on each other.
            </>
          )}
        </p>
        <p className="meta">
          ω: how often each reaches out by choice, per day so far. K₁: his share of the times {her} chose whom to
          approach ({pair.approaches}). K₂: how often he turns toward her bids when he could walk away.
        </p>
      </div>
    </section>
  );
}
