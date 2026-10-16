// Two twins as coupled oscillators (the Kuramoto model): θ̇₁ = ω₁ + K₁ sin(θ₂ − θ₁), θ̇₂ = ω₂ + K₂ sin(θ₁ − θ₂).
// ω is a twin's own rhythm and K how much it lets the other pull it. They lock (move at one speed,
// Ω = (K₂ω₁ + K₁ω₂)/(K₁ + K₂), a gap φ apart with sin φ = (ω₂ − ω₁)/(K₁ + K₂)) once |ω₁ − ω₂| ≤ K₁ + K₂.
//
// Both are measured from the run so far, from voluntary moments only: a bid made at a gathering or by
// seeking someone out, proposing or going to the wall, where the twin could have done something else. A
// date's conversation doesn't count: on a date both must speak and talk runs until both stop, so nearly
// every pair "turns toward" 70-90% of the time and the rate says nothing (tested on 10 runs).
//   ω  — how often a twin reaches out by choice, per day so far (relative to the most outgoing twin)
//   K₁ — how much she lets him pull her: his share of her free approaches (she can choose any man)
//   K₂ — how much he lets her pull him: how often he turns toward her voluntary bids (Gottman's
//        "bids"), smoothed (yes+1)/(n+2). (He has one woman to approach, so a share says nothing.)
// On 10 saved runs, whom she approached most at gatherings before the wall opened was the man she
// broke out with in 7 (chance ~1.4); turning toward alone picked him in 4. With this lock rule, at the
// day the wall opened about 2 of 7 men were locked, her eventual partner among them in 6 of 10 runs
// (chance ~3), and the strongest lock was her partner in 4 (chance ~1.4): a picture, not a predictor.

export type SyncEvent = { seq: number; day: number; twin: string | null; target: string | null; rung: string | null; place: string | null };

const BIDS = new Set(["talk", "seek_out", "propose_leaving", "go_beyond_wall"]);
const voluntary = (e: SyncEvent) =>
  e.place === "gathering_hall" || e.rung === "seek_out" || e.rung === "propose_leaving" || e.rung === "go_beyond_wall";
const isBid = (e: SyncEvent) => !!e.twin && !!e.target && BIDS.has(e.rung ?? "");

export type Pair = {
  man: string;
  approaches: number; // her voluntary bids to him
  omegaHer: number;
  omegaHim: number;
  kHer: number; // how much she lets him pull her
  kHim: number;
  locked: boolean;
  common: number | null; // Ω when locked
  gap: number | null; // φ in degrees when locked
};

// Display scale: rhythms between 0.6 and 1.8 rad/s, pulls up to 1.2, so the animation is easy to follow.
const OMEGA_MIN = 0.6;
const OMEGA_SPAN = 1.2;
const K_MAX = 1.2;

export function measure(events: SyncEvent[], her: string, uptoSeq: number): Pair[] {
  const seen = events.filter((e) => e.seq <= uptoSeq);
  const days = Math.max(1, ...seen.map((e) => e.day));
  const reachOut = new Map<string, number>(); // voluntary bids made, per twin
  const approaches = new Map<string, number>();
  const toward = new Map<string, [number, number]>(); // key `${from}>${to}`: [turned toward, bids received]
  seen.forEach((e, i) => {
    if (!isBid(e) || !voluntary(e)) return;
    reachOut.set(e.twin!, (reachOut.get(e.twin!) ?? 0) + 1);
    if (e.twin === her) approaches.set(e.target!, (approaches.get(e.target!) ?? 0) + 1);
    const reply = seen.slice(i + 1).find((x) => x.day === e.day && x.twin === e.target);
    const key = `${e.target}>${e.twin}`; // the receiver's response to the bidder
    const [yes, n] = toward.get(key) ?? [0, 0];
    toward.set(key, [yes + (reply && isBid(reply) && reply.target === e.twin ? 1 : 0), n + 1]);
  });
  const rate = (who: string) => (reachOut.get(who) ?? 0) / days;
  const most = Math.max(1e-9, ...[...reachOut.keys()].map(rate));
  const omega = (who: string) => OMEGA_MIN + OMEGA_SPAN * (rate(who) / most);
  const pull = (from: string, to: string) => {
    const [yes, n] = toward.get(`${from}>${to}`) ?? [0, 0];
    return K_MAX * ((yes + 1) / (n + 2));
  };
  const men = new Set<string>();
  for (const e of seen) for (const who of [e.twin, e.target]) if (who && who !== her) men.add(who);
  return [...men]
    .map((man) => {
      const share = (approaches.get(man) ?? 0) / Math.max(1, reachOut.get(her) ?? 0);
      const [w1, w2, k1, k2] = [omega(her), omega(man), K_MAX * share, pull(man, her)];
      const locked = Math.abs(w1 - w2) <= k1 + k2;
      return {
        man,
        approaches: approaches.get(man) ?? 0,
        omegaHer: w1,
        omegaHim: w2,
        kHer: k1,
        kHim: k2,
        locked,
        common: locked ? (k2 * w1 + k1 * w2) / (k1 + k2) : null,
        gap: locked ? (Math.asin(Math.max(-1, Math.min(1, (w2 - w1) / (k1 + k2)))) * 180) / Math.PI : null,
      };
    })
    .sort((a, b) => b.approaches - a.approaches || b.kHer + b.kHim - (a.kHer + a.kHim) || a.man.localeCompare(b.man));
}

/** One step of the two equations (Euler), for the animation. */
export function step(t1: number, t2: number, p: Pair, dt: number): [number, number] {
  return [t1 + dt * (p.omegaHer + p.kHer * Math.sin(t2 - t1)), t2 + dt * (p.omegaHim + p.kHim * Math.sin(t1 - t2))];
}
