"use client";

import { useState } from "react";

/** GET /me/about and PUT /me/about/{part} (garden/about_me.py). */
export type About = {
  form?: { interests: Record<string, string>; qualities: Record<string, string>; statements: { id: string; text: string }[] };
  about: {
    profile?: { age: number; work: string; city: string; loves: string[]; dislikes: string[] };
    personality?: { answers: Record<string, number> };
    preferences?: { points: Record<string, number> };
  };
  status: { profile: boolean; personality: boolean; preferences: boolean };
  facts: { text: string; about: string }[];
};

type Part = "profile" | "personality" | "preferences";
const SCALE = ["Very inaccurate", "Inaccurate", "Neither", "Accurate", "Very accurate"];

/** Three short forms beside the questions: the facts, personality and priorities a twin needs so it
 * doesn't have to invent them. Each saves on its own and shows the sentences the twin will know. */
export default function AboutYou({
  about,
  busy,
  onSave,
}: {
  about: About;
  busy: boolean;
  onSave: (part: Part, body: unknown) => void;
}) {
  const form = about.form!;
  const saved = about.about;
  const [open, setOpen] = useState<Part | null>(
    !about.status.profile ? "profile" : !about.status.personality ? "personality" : !about.status.preferences ? "preferences" : null,
  );
  const [profile, setProfile] = useState(
    saved.profile ?? { age: 0, work: "", city: "", loves: [] as string[], dislikes: [] as string[] },
  );
  const [answers, setAnswers] = useState<Record<string, number>>(saved.personality?.answers ?? {});
  const [points, setPoints] = useState<Record<string, number>>(
    saved.preferences?.points ?? Object.fromEntries(Object.keys(form.qualities).map((q) => [q, 0])),
  );
  const total = Object.values(points).reduce((a, b) => a + b, 0);

  const cycle = (key: string) =>
    setProfile((p) => {
      const loves = p.loves.includes(key) ? p.loves.filter((k) => k !== key) : p.dislikes.includes(key) ? p.loves : [...p.loves, key];
      const dislikes = p.loves.includes(key) ? [...p.dislikes, key] : p.dislikes.filter((k) => k !== key);
      return { ...p, loves: loves.slice(0, 6), dislikes: dislikes.slice(0, 4) };
    });

  const head = (part: Part, title: string, hint: string) => (
    <button className="about-head" onClick={() => setOpen(open === part ? null : part)} aria-expanded={open === part}>
      <span className={`about-check${about.status[part] ? " done" : ""}`}>{about.status[part] ? "✓" : ""}</span>
      <span>
        <b>{title}</b>
        <span className="meta"> · {hint}</span>
      </span>
    </button>
  );

  return (
    <section className="result about" data-testid="about-you">
      <h2>About you</h2>
      <p className="meta">Three short forms. Your twin only knows what you tell it, so it never has to make things up.</p>

      <div className="about-part">
        {head("profile", "Your profile", "age, work, city, what you love")}
        {open === "profile" && (
          <div className="about-body">
            <div className="about-row">
              <label>
                Age
                <input type="number" min={18} max={99} value={profile.age || ""} onChange={(e) => setProfile({ ...profile, age: Number(e.target.value) })} />
              </label>
              <label>
                Work or studies
                <input value={profile.work} maxLength={80} onChange={(e) => setProfile({ ...profile, work: e.target.value })} />
              </label>
              <label>
                City
                <input value={profile.city} maxLength={80} onChange={(e) => setProfile({ ...profile, city: e.target.value })} />
              </label>
            </div>
            <p className="meta">Tap once for ❤️ love (up to 6), twice for 🙅 not for me (up to 4), again to clear.</p>
            <div className="interest-chips">
              {Object.entries(form.interests).map(([key, label]) => {
                const state = profile.loves.includes(key) ? "love" : profile.dislikes.includes(key) ? "dislike" : "";
                return (
                  <button key={key} className={`interest ${state}`} onClick={() => cycle(key)} aria-pressed={!!state}>
                    {state === "love" ? "❤️ " : state === "dislike" ? "🙅 " : ""}
                    {label}
                  </button>
                );
              })}
            </div>
            <button disabled={busy || !profile.age || !profile.work.trim() || !profile.city.trim()} onClick={() => onSave("profile", profile)}>
              Save profile
            </button>
          </div>
        )}
      </div>

      <div className="about-part">
        {head("personality", "Your personality", "20 quick statements (Mini-IPIP)")}
        {open === "personality" && (
          <div className="about-body">
            <p className="meta">How accurately does each describe you, as you generally are?</p>
            <ol className="ipip">
              {form.statements.map((s) => (
                <li key={s.id}>
                  <span className="ipip-text">I {s.text.charAt(0).toLowerCase() + s.text.slice(1)}</span>
                  <span className="ipip-scale" role="radiogroup" aria-label={s.text}>
                    {SCALE.map((label, i) => (
                      <button
                        key={label}
                        role="radio"
                        aria-checked={answers[s.id] === i + 1}
                        title={label}
                        className={answers[s.id] === i + 1 ? "on" : ""}
                        onClick={() => setAnswers({ ...answers, [s.id]: i + 1 })}
                      >
                        {i + 1}
                      </button>
                    ))}
                  </span>
                </li>
              ))}
            </ol>
            <p className="meta">1 = very inaccurate · 5 = very accurate</p>
            <button disabled={busy || Object.keys(answers).length < form.statements.length} onClick={() => onSave("personality", { answers })}>
              Save personality ({Object.keys(answers).length}/{form.statements.length})
            </button>
          </div>
        )}
      </div>

      <div className="about-part">
        {head("preferences", "What matters in a partner", "share 100 points")}
        {open === "preferences" && (
          <div className="about-body">
            {Object.entries(form.qualities).map(([key, label]) => (
              <label key={key} className="points">
                <span>{label}</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={points[key]}
                  onChange={(e) => setPoints({ ...points, [key]: Number(e.target.value) })}
                />
                <b>{points[key]}</b>
              </label>
            ))}
            <p className={total === 100 ? "meta" : "error"}>Total: {total} / 100</p>
            <button disabled={busy || total !== 100} onClick={() => onSave("preferences", { points })}>
              Save priorities
            </button>
          </div>
        )}
      </div>

      {about.facts.length > 0 && (
        <details className="about-facts">
          <summary>What your twin will know from these ({about.facts.length})</summary>
          <ul>
            {about.facts.map((f) => (
              <li key={f.text}>{f.text}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
