"use client";

import { useState } from "react";

/** GET /me/twin: the twin in its own words, section by section, plus the traits it was read as. */
export type TwinSummary = {
  alias: string;
  version: number;
  reviewed: boolean;
  sections: { id: string; title: string; text: string; edited: boolean }[];
  attachment_style: string;
  values: string[];
  dealbreakers: string[];
  rebelliousness: number;
  traits_edited: string[];
  rebelliousness_because: { question: string; answer: string }[];
  rebel_memory: string; // how her twin sees rules, in its own words ("" in the middle of the scale)
  memory_count: number;
  about?: { text: string; about: string }[]; // facts from the About-you forms, as the twin knows them
};

export type TraitEdit = Partial<Pick<TwinSummary, "attachment_style" | "values" | "dealbreakers" | "rebelliousness">>;

const ATTACHMENT = ["secure", "anxious", "avoidant", "fearful-avoidant"];
// Three plain choices instead of a raw score (the API takes 0–1).
const REBEL = [
  { value: 0.15, label: "Keeps to the rules, even for love" },
  { value: 0.5, label: "Bends rules when it matters" },
  { value: 0.85, label: "Breaks rules readily, especially for love" },
];
const rebelChoice = (x: number) => REBEL.reduce((a, b) => (Math.abs(b.value - x) < Math.abs(a.value - x) ? b : a));
const asList = (text: string) =>
  text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

/** Review and change the twin; your words and choices replace what was drawn from your answers.
 * The parent remounts it (key = version) whenever the twin changes, so no edit outlives its twin. */
export default function TwinReview({
  twin,
  onSave,
  onTraits,
  onConfirm,
  busy,
}: {
  twin: TwinSummary;
  onSave: (section: string, text: string) => Promise<boolean>;
  onTraits: (traits: TraitEdit) => Promise<boolean>;
  onConfirm: () => Promise<boolean>;
  busy: boolean;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [values, setValues] = useState(twin.values.join(", "));
  const [dealbreakers, setDealbreakers] = useState(twin.dealbreakers.join(", "));
  const edited = (trait: string) => twin.traits_edited.includes(trait) && <span className="meta"> · yours</span>;

  return (
    <section className="result twin-review" data-testid="twin-review">
      <h2>Meet your twin, {twin.alias}</h2>
      <p className="meta">
        Others only ever see the alias {twin.alias}. Change anything that doesn&apos;t sound like you: your words
        and choices replace what was drawn from your answers.
      </p>
      {twin.about && twin.about.length > 0 && (
        <div className="twin-section">
          <h3>From your About-you forms</h3>
          <p className="meta">Change these in the forms above, then rebuild.</p>
          <ul className="about-list">
            {twin.about.map((f) => (
              <li key={f.text}>{f.text}</li>
            ))}
          </ul>
        </div>
      )}
      {twin.sections.map((s) => (
        <div key={s.id} className="twin-section">
          <h3>
            {s.title}
            {s.edited && <span className="meta"> · in your words</span>}
          </h3>
          {editing === s.id ? (
            <>
              <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={5} aria-label={s.title} />
              <button disabled={busy} onClick={() => onSave(s.id, draft)}>
                Save
              </button>{" "}
              <button className="link" onClick={() => setEditing(null)}>
                Cancel
              </button>
            </>
          ) : (
            <>
              <p>{s.text || <span className="meta">Nothing yet.</span>}</p>
              <button
                className="link"
                onClick={() => {
                  setEditing(s.id);
                  setDraft(s.text);
                }}
              >
                Rewrite
              </button>
              {s.edited && (
                <>
                  {" · "}
                  <button className="link" disabled={busy} onClick={() => onSave(s.id, "")}>
                    Use the original
                  </button>
                </>
              )}
            </>
          )}
        </div>
      ))}

      <div className="twin-traits">
        <label>
          Attachment{edited("attachment_style")}
          <select
            value={twin.attachment_style}
            disabled={busy}
            onChange={(e) => onTraits({ attachment_style: e.target.value })}
          >
            {ATTACHMENT.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </label>
        <label>
          Rules{edited("rebelliousness")}
          <select
            value={rebelChoice(twin.rebelliousness).value}
            disabled={busy}
            onChange={(e) => onTraits({ rebelliousness: Number(e.target.value) })}
          >
            {REBEL.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        {twin.rebel_memory && (
          <p className="meta">
            Your twin remembers: <q>{twin.rebel_memory}</q>
          </p>
        )}
        {twin.rebelliousness_because.length > 0 && (
          <div className="meta because">
            Read from what you said:
            <ul>
              {twin.rebelliousness_because.map((b) => (
                <li key={b.question}>
                  {b.question} <q>{b.answer}</q>
                </li>
              ))}
            </ul>
          </div>
        )}
        <label>
          Values (comma separated){edited("values")}
          <input
            value={values}
            onChange={(e) => setValues(e.target.value)}
            onBlur={() => values !== twin.values.join(", ") && onTraits({ values: asList(values) })}
          />
        </label>
        <label>
          Dealbreakers (comma separated){edited("dealbreakers")}
          <input
            value={dealbreakers}
            onChange={(e) => setDealbreakers(e.target.value)}
            onBlur={() =>
              dealbreakers !== twin.dealbreakers.join(", ") && onTraits({ dealbreakers: asList(dealbreakers) })
            }
          />
        </label>
      </div>

      {twin.reviewed ? (
        <p className="verdict good">You confirmed this twin. It can date in the Garden.</p>
      ) : (
        <button disabled={busy} onClick={onConfirm}>
          This is me: let my twin date
        </button>
      )}
    </section>
  );
}
