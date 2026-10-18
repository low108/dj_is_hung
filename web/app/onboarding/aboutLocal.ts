// The About you forms with no API (the static demo): the same fixed templates as garden/about_me.py,
// read from demo/about.json (written from that module by scripts/deploy.sh), so the wording has one source.
// Nothing is saved; the facts are shown so a visitor sees what their twin would know.
import type { About } from "./AboutYou";

export type AboutRules = {
  form: NonNullable<About["form"]>;
  items: Record<string, { trait: string; reverse: boolean }>;
  says: Record<string, [string, string]>;
  high: number;
  low: number;
};

const list = (w: string[]) => (w.length === 1 ? w[0] : `${w.slice(0, -1).join(", ")} and ${w[w.length - 1]}`);
const clean = (s: string) => s.trim().replace(/\.+$/, "");

/** about_me.memories(): the twin's facts from the forms filled in so far. */
export function facts(about: About["about"], r: AboutRules): About["facts"] {
  const out: About["facts"] = [];
  const add = (text: string, kind: string) => out.push({ text, about: kind });
  const { interests, qualities } = r.form;
  const p = about.profile;
  if (p) {
    add(`I am ${p.age} years old.`, "age");
    add(`My work: ${clean(p.work)}.`, "career");
    add(`I live in ${clean(p.city)}.`, "home");
    if (p.loves.length) add(`I love ${list(p.loves.map((i) => interests[i]))}.`, "loves");
    if (p.dislikes.length) add(`I don't care much for ${list(p.dislikes.map((i) => interests[i]))}.`, "not for me");
  }
  if (about.personality) {
    const byTrait: Record<string, number[]> = {};
    for (const [id, answer] of Object.entries(about.personality.answers)) {
      const { trait, reverse } = r.items[id];
      (byTrait[trait] ??= []).push(reverse ? 6 - answer : answer);
    }
    for (const [trait, scores] of Object.entries(byTrait)) {
      const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
      if (mean >= r.high) add(r.says[trait][0], "personality");
      else if (mean <= r.low) add(r.says[trait][1], "personality");
    }
  }
  if (about.preferences) {
    const pts = about.preferences.points;
    const top = Object.keys(pts).sort((a, b) => pts[b] - pts[a]).slice(0, 2);
    add(`In a partner, what matters most to me is that they are ${qualities[top[0]]}, then ${qualities[top[1]]}.`,
        "wants in a partner");
    const low = Object.keys(pts).reduce((a, b) => (pts[b] < pts[a] ? b : a));
    if (pts[low] < 12) add(`Whether a partner is ${qualities[low]} matters less to me.`, "wants in a partner");
  }
  return out;
}
