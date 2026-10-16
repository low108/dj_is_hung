"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { measure, step, type Pair, type SyncEvent } from "./sync";

const HER = "#e8a24a"; // her rhythm: amber
const HIM = "#5b9be0"; // his: blue
const THREADS = 64; // lines of the tube between the two rings
const STARS = 220;

type Star = { x: number; y: number; r: number; phase: number; speed: number };

/** Her and one man as two coupled rhythms (garden/sync.ts), drawn the way the "love as two oscillators"
 * explainer draws them: two glowing rings in space joined by a tube of threads. Each thread ties a
 * point on her ring to the point on his at the same angle plus their phase gap, so the tube's twist IS
 * the gap: locked, it holds still (φ); drifting, it keeps winding. A bright chord joins the two moving
 * points. The numbers are measured from the run up to the moment playing. */
export default function SyncPanel({ events, her, atSeq }: { events: SyncEvent[]; her: string; atSeq: number }) {
  const pairs = useMemo(() => measure(events, her, atSeq), [events, her, atSeq]);
  const [chosen, setChosen] = useState<string | null>(null);
  const pair: Pair | undefined = pairs.find((p) => p.man === chosen) ?? pairs[0];
  const pairRef = useRef(pair);
  pairRef.current = pair;
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const stars: Star[] = Array.from({ length: STARS }, (_, i) => {
      const r = (n: number) => ((Math.sin(i * 12.9898 + n * 78.233) * 43758.5453) % 1 + 1) % 1; // stable per star
      return { x: r(1), y: r(2), r: 0.3 + r(3) * 1.1, phase: r(4) * Math.PI * 2, speed: 0.4 + r(5) * 1.2 };
    });
    let w = 0;
    let h = 0;
    const fit = () => {
      const dpr = window.devicePixelRatio || 1;
      w = el.clientWidth;
      h = el.clientHeight;
      el.width = Math.round(w * dpr);
      el.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    fit();
    const resize = new ResizeObserver(fit);
    resize.observe(el);

    let t1 = 0;
    let t2 = Math.PI; // they start opposite, so you can watch them find each other
    let last = performance.now();
    let frame = 0;
    const draw = (now: number) => {
      const p = pairRef.current;
      const dt = Math.min(0.05, (now - last) / 1000);
      const time = now / 1000;
      last = now;
      if (p) [t1, t2] = step(t1, t2, p, dt);

      // Space: a deep gradient, two nebula glows, twinkling stars.
      ctx.globalCompositeOperation = "source-over";
      const bg = ctx.createLinearGradient(0, 0, 0, h);
      bg.addColorStop(0, "#0b0a16");
      bg.addColorStop(1, "#05050b");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);
      for (const [cx, cy, rad, color] of [
        [0.3, 0.45, 0.5, "rgba(88, 52, 140, 0.28)"],
        [0.72, 0.6, 0.45, "rgba(40, 70, 150, 0.22)"],
      ] as const) {
        const g = ctx.createRadialGradient(cx * w, cy * h, 0, cx * w, cy * h, rad * w);
        g.addColorStop(0, color);
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, w, h);
      }
      for (const s of stars) {
        ctx.globalAlpha = 0.25 + 0.55 * (0.5 + 0.5 * Math.sin(time * s.speed + s.phase));
        ctx.fillStyle = "#dfe6ff";
        ctx.beginPath();
        ctx.arc(s.x * w, s.y * h, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      if (!p) {
        frame = requestAnimationFrame(draw);
        return;
      }

      // The two rings, seen a little from the side so the tube between them has depth.
      // Layout: equations across the top (an overlay), rings in the middle, names under them, the
      // rhythm axis along the bottom. Sized so none of them overlap at any width.
      const axisY = h - 26;
      const cy = h * 0.52;
      const ry = Math.max(24, Math.min(h * 0.24, w * 0.16, axisY - 34 - cy));
      const rx = ry * 0.42;
      const left = { x: w * 0.3, y: cy };
      const right = { x: w * 0.7, y: cy };
      const on = (c: { x: number; y: number }, a: number) => ({ x: c.x + rx * Math.cos(a), y: c.y + ry * Math.sin(a) });
      const gap = t2 - t1;

      // The tube: thread k joins angle a on her ring to angle a + gap on his. Additive light, like the video.
      ctx.globalCompositeOperation = "lighter";
      ctx.lineWidth = 0.7;
      const locked = p.locked;
      for (let k = 0; k < THREADS; k++) {
        const a = (k / THREADS) * Math.PI * 2 + t1;
        const [from, to] = [on(left, a), on(right, a + gap)];
        const back = Math.sin(a) < 0; // threads behind the axis are fainter
        const grad = ctx.createLinearGradient(from.x, from.y, to.x, to.y);
        const alpha = (back ? 0.07 : 0.16) * (locked ? 1.25 : 0.9);
        grad.addColorStop(0, `rgba(232, 162, 74, ${alpha})`);
        grad.addColorStop(1, `rgba(91, 155, 224, ${alpha})`);
        ctx.strokeStyle = grad;
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        ctx.lineTo(to.x, to.y);
        ctx.stroke();
      }

      // Rings with a soft glow.
      for (const [c, color] of [
        [left, HER],
        [right, HIM],
      ] as const) {
        ctx.shadowColor = color;
        ctx.shadowBlur = 14;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.ellipse(c.x, c.y, rx, ry, 0, 0, Math.PI * 2);
        ctx.stroke();
      }

      // The two of them: a glowing point on each ring and the chord between.
      const [a, b] = [on(left, t1), on(right, t2)];
      ctx.shadowBlur = 0;
      const chord = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
      chord.addColorStop(0, "rgba(255, 214, 150, 0.95)");
      chord.addColorStop(1, "rgba(180, 215, 255, 0.95)");
      ctx.strokeStyle = chord;
      ctx.lineWidth = locked ? 1.6 : 1;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      for (const [pt, color] of [
        [a, "#ffd08a"],
        [b, "#b4d7ff"],
      ] as const) {
        const glow = ctx.createRadialGradient(pt.x, pt.y, 0, pt.x, pt.y, 16);
        glow.addColorStop(0, color);
        glow.addColorStop(0.25, color + "aa");
        glow.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 16, 0, Math.PI * 2);
        ctx.fill();
      }

      // The rhythm line: ω₁, ω₂ and (locked) Ω on one axis, as in the video.
      ctx.globalCompositeOperation = "source-over";
      const [x0, x1] = [w * 0.22, w * 0.78];
      const lo = Math.min(p.omegaHer, p.omegaHim) - 0.3;
      const hi = Math.max(p.omegaHer, p.omegaHim) + 0.3;
      const X = (v: number) => x0 + ((v - lo) / (hi - lo)) * (x1 - x0);
      ctx.strokeStyle = "rgba(220, 225, 255, 0.25)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x0, axisY);
      ctx.lineTo(x1, axisY);
      ctx.stroke();
      const tick = (v: number, color: string, label: string, up: boolean) => {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(X(v), axisY - 6);
        ctx.lineTo(X(v), axisY + 6);
        ctx.stroke();
        ctx.fillStyle = color;
        ctx.font = "italic 13px 'Iowan Old Style', Palatino, Georgia, serif";
        ctx.textAlign = "center";
        ctx.fillText(label, X(v), up ? axisY - 11 : axisY + 20);
      };
      tick(p.omegaHer, HER, "ω₁", false);
      tick(p.omegaHim, HIM, "ω₂", false);
      if (locked && p.common !== null) tick(p.common, "#f4f1ff", "Ω", true);

      // Names under the rings.
      ctx.fillStyle = "rgba(225, 228, 245, 0.8)";
      ctx.font = "12px 'Iowan Old Style', Palatino, Georgia, serif";
      ctx.textAlign = "center";
      ctx.fillText(her, left.x, cy + ry + 16);
      ctx.fillText(p.man, right.x, cy + ry + 16);

      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
    };
  }, [her]);

  if (!pair) return null;
  const f = (x: number) => x.toFixed(2);
  const caption = pair.locked
    ? `Two different rhythms, each willing to be pulled: locked, ${Math.abs(pair.gap!).toFixed(0)}° apart. Still two people.`
    : `Their rhythms are further apart than they pull on each other: they drift.`;
  return (
    <section className="sync" aria-label="In sync?">
      <div className="sync-stage">
        <canvas ref={canvas} className="sync-canvas" aria-label={`${her} and ${pair.man}: ${pair.locked ? "locked" : "drifting"}`} />
        <div className="sync-overlay top">
          <span className="sync-chapter">III — IN SYNC</span>
          <div className="sync-eq">
            <span>
              θ̇<sub>1</sub> = <i className="her">{f(pair.omegaHer)}</i> + <i className="her">{f(pair.kHer)}</i> sin(θ<sub>2</sub> − θ
              <sub>1</sub>)
            </span>
            <span>
              θ̇<sub>2</sub> = <i className="him">{f(pair.omegaHim)}</i> + <i className="him">{f(pair.kHim)}</i> sin(θ<sub>1</sub> − θ
              <sub>2</sub>)
            </span>
          </div>
        </div>
      </div>
      <div className="sync-subtitle">
        <p className={`sync-caption${pair.locked ? " locked" : ""}`}>{caption}</p>
        <p className="sync-cond">
          |ω₁ − ω₂| = {f(Math.abs(pair.omegaHer - pair.omegaHim))} {pair.locked ? "≤" : ">"} K₁ + K₂ = {f(pair.kHer + pair.kHim)}
          {pair.locked && pair.common !== null && <> · Ω = {f(pair.common)}</>}
        </p>
      </div>
      <div className="sync-men" role="tablist" aria-label="Choose a man">
        {pairs.map((p) => (
          <button
            key={p.man}
            role="tab"
            aria-selected={p.man === pair.man}
            className={`sync-man${p.man === pair.man ? " on" : ""}${p.locked ? " locked" : ""}`}
            onClick={() => setChosen(p.man)}
            title={`${her} approached ${p.man} ${p.approaches} time(s) when she could choose anyone`}
          >
            <span className="sync-dot" aria-hidden />
            {p.man}
            {p.approaches > 0 && <sub>{p.approaches}</sub>}
          </button>
        ))}
      </div>
      <p className="sync-note">
        ω: how often each reaches out by choice, per day so far · K₁: his share of the times {her} chose whom to approach (
        {pair.approaches}) · K₂: how often he turns toward her bids when he could walk away
      </p>
    </section>
  );
}
