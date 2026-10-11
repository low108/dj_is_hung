"use client";

import { useState } from "react";

/** GET /me/twin: the twin in its own words, section by section, plus what it was read as. */
export type TwinSummary = {
  alias: string;
  sections: { id: string; title: string; text: string; edited: boolean }[];
  attachment_style: string;
  values: string[];
  dealbreakers: string[];
  rebelliousness: number;
  rebelliousness_because: string[];
  memory_count: number;
};

function rebelWords(x: number): string {
  if (x >= 0.67) return "breaks rules readily, especially for love";
  if (x >= 0.34) return "bends rules when it matters";
  return "keeps to the rules, even for love";
}

/** Review and rewrite the twin. Saving a section replaces that section's memories with your words. */
export default function TwinReview({
  twin,
  onSave,
  busy,
}: {
  twin: TwinSummary;
  onSave: (section: string, text: string) => Promise<boolean>;
  busy: boolean;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  return (
    <section className="result twin-review" data-testid="twin-review">
      <h2>Meet your twin, {twin.alias}</h2>
      <p className="meta">
        Others only ever see the alias {twin.alias}. Rewrite anything that doesn&apos;t sound like you: your words
        replace what was drawn from your answers.
      </p>
      {twin.sections.map((s) => (
        <div key={s.id} className="twin-section">
          <h3>
            {s.title}
            {s.edited && <span className="meta"> · in your words</span>}
          </h3>
          {editing === s.id ? (
            <>
              <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={5} aria-label={s.title} />
              <button
                disabled={busy}
                onClick={async () => {
                  if (await onSave(s.id, draft)) setEditing(null);
                }}
              >
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
      <dl className="twin-traits">
        <dt>Attachment</dt>
        <dd>{twin.attachment_style}</dd>
        <dt>Values</dt>
        <dd>{twin.values.join(", ")}</dd>
        <dt>Dealbreakers</dt>
        <dd>{twin.dealbreakers.join(", ")}</dd>
        <dt>Rules</dt>
        <dd>
          {rebelWords(twin.rebelliousness)}
          {twin.rebelliousness_because.length > 0 && (
            <span className="meta"> (from: {twin.rebelliousness_because.join(" / ")})</span>
          )}
        </dd>
      </dl>
    </section>
  );
}
