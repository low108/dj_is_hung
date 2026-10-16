"use client";

import { ProfileList, type ProfileLine } from "./Profiles";

/** What the viewer knows about a twin at its latest evening (GET /simulations/{id}/twins). */
export type TwinState = {
  day: number;
  twin: string;
  partner: string | null;
  days_left: number | null;
  standing: string;
  longing_hearts: Record<string, number>;
  reflection: string;
};

function timeLeft(daysLeft: number | null): string {
  if (daysLeft === null) return "";
  if (daysLeft <= 0) return "their time together ends tonight";
  return daysLeft === 1 ? "one more day" : `${daysLeft} more days`;
}

export default function TwinPanel({
  twin,
  state,
  profile = [],
  onClose,
}: {
  twin: string;
  state: TwinState | undefined;
  profile?: ProfileLine[];
  onClose: () => void;
}) {
  const persona = profile.length > 0 && (
    <details className="twin-persona" open>
      <summary>Who {twin} is</summary>
      <ProfileList lines={profile} />
    </details>
  );
  if (!state)
    return (
      <aside className="twin-panel" data-testid="twin-panel">
        <header>
          <h3>{twin}</h3>
          <button className="link" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        {persona}
        <p className="meta">Nothing to report until the first evening.</p>
      </aside>
    );
  const hearts = Object.entries(state.longing_hearts).sort((a, b) => b[1] - a[1]);
  return (
    <aside className="twin-panel" data-testid="twin-panel">
      <header>
        <h3>{state.twin}</h3>
        <button className="link" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </header>
      {persona}
      <p className="meta">As of the evening of day {state.day}</p>
      <dl>
        <dt>Partner</dt>
        <dd>
          {state.partner ? `${state.partner}, ${timeLeft(state.days_left)}` : "Between assignments"}
        </dd>
        {state.standing && (
          <>
            <dt>Standing</dt>
            <dd>{state.standing}</dd>
          </>
        )}
        <dt>Longing</dt>
        <dd>
          {hearts.length
            ? hearts.map(([who, n]) => (
                <span key={who} className="hearts">
                  {who} {"♥".repeat(n)}
                  {"♡".repeat(3 - n)}
                </span>
              ))
            : "No one yet"}
        </dd>
        {state.reflection && (
          <>
            <dt>Tonight&apos;s reflection</dt>
            <dd className="reflection">“{state.reflection}”</dd>
          </>
        )}
      </dl>
      <p className="meta">Viewer only: twins never see hearts or numbers.</p>
    </aside>
  );
}
